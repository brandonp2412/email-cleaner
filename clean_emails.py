#!/usr/bin/env python3
import imaplib
import email
import json
import os
import subprocess
import requests
import re
import smtplib
import shutil
from datetime import datetime, timedelta
from email.header import decode_header
from env import ACCOUNTS, WHITELIST

os.chdir(os.path.dirname(os.path.abspath(__file__)))


# ---------------------------------------------------------------------------
# Account configuration — add/remove accounts here
# ---------------------------------------------------------------------------
DAYS_BACK = 1       # How many days of email to scan
CLAUDE_BIN = shutil.which("claude") or "/home/fdroid/.nvm/versions/node/v24.14.1/bin/claude"
DRY_RUN = False      # Set False when you're happy with classifications
CHUNK_SIZE = 50     # Emails per Claude classification call

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def decode_str(s):
    if not s:
        return ""
    parts = decode_header(s)
    result = []
    for p, enc in parts:
        if isinstance(p, bytes):
            result.append(p.decode(enc or "utf-8", errors="replace"))
        else:
            result.append(p)
    return "".join(result)


# ---------------------------------------------------------------------------
# IMAP fetch
# ---------------------------------------------------------------------------

def fetch_emails(account):
    """Fetch email metadata from a single account via IMAP."""
    mail = imaplib.IMAP4_SSL(account["imap_host"], account["imap_port"])
    mail.login(account["username"], account["password"])
    mail.select("INBOX")

    since = (datetime.now() - timedelta(days=DAYS_BACK)).strftime("%d-%b-%Y")
    _, data = mail.uid("search", None, f'(SINCE "{since}")')
    msg_ids = data[0].split()
    print(f"[{account['name']}] {len(msg_ids)} emails in last {DAYS_BACK} days")

    emails = []
    for uid in msg_ids:
        try:
            _, msg_data = mail.uid("fetch", uid, "(RFC822.HEADER)")
            msg = email.message_from_bytes(msg_data[0][1])
            emails.append({
                "uid": uid.decode(),
                "account": account["name"],
                "from": decode_str(msg.get("From", "")),
                "subject": decode_str(msg.get("Subject", "")),
                "list_unsubscribe": msg.get("List-Unsubscribe", ""),
            })
        except Exception as e:
            print(f"  Warning: could not fetch uid {uid}: {e}")

    mail.logout()
    return emails


def fetch_full_body(account, uid):
    """Fetch the full HTML body of a specific email (for agentic unsubscribe)."""
    mail = imaplib.IMAP4_SSL(account["imap_host"], account["imap_port"])
    mail.login(account["username"], account["password"])
    mail.select("INBOX")

    _, msg_data = mail.uid("fetch", uid, "(RFC822)")
    msg = email.message_from_bytes(msg_data[0][1])

    body = ""
    if msg.is_multipart():
        for part in msg.walk():
            ct = part.get_content_type()
            if ct == "text/html":
                body = part.get_payload(decode=True).decode("utf-8", errors="ignore")
                break
            if ct == "text/plain" and not body:
                body = part.get_payload(decode=True).decode("utf-8", errors="ignore")
    else:
        body = msg.get_payload(decode=True).decode("utf-8", errors="ignore")

    mail.logout()
    return body


# ---------------------------------------------------------------------------
# Classification via Claude Code headless
# ---------------------------------------------------------------------------

def classify_with_claude(emails):
    """
    Send a batch of email metadata to Claude (headless subprocess) for classification.
    Returns a list of dicts: {uid, account, category}
    """
    prompt = f"""Classify each email as exactly one of: spam, marketing, or keep.

Definitions:
- spam: unsolicited, no prior relationship, scammy, phishing, or suspicious
- marketing: newsletters, promotions, deals from legitimate companies you may have signed up for
- keep: personal messages, work email, transactional (receipts, shipping notices, account alerts, bank statements)

When in doubt between spam and keep, prefer keep.
When in doubt between marketing and keep, prefer marketing.

Return ONLY a JSON array with no explanation, markdown, or extra text:
[{{"uid": "1", "account": "gmail_1", "category": "spam"}}, ...]

Emails to classify:
{json.dumps(emails, indent=2)}"""

    result = subprocess.run(
        [CLAUDE_BIN, "-p", prompt, "--output-format", "json"],
        capture_output=True,
        text=True,
        timeout=180,
    )

    if result.returncode != 0:
        raise RuntimeError(f"Claude exited with code {result.returncode}: {result.stderr[:200]}")

    response = json.loads(result.stdout)
    text = response.get("result", "").strip()
    # Strip markdown fences if present
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    return json.loads(text)


# ---------------------------------------------------------------------------
# Unsubscribe helpers
# ---------------------------------------------------------------------------

def get_unsubscribe_url(header):
    if not header:
        return None
    match = re.search(r"<(https?://[^>]+)>", header)
    return match.group(1) if match else None


def get_unsubscribe_mailto(header):
    if not header:
        return None
    match = re.search(r"<mailto:([^>]+)>", header)
    return match.group(1) if match else None


def find_unsubscribe_in_body(html):
    """Extract the most likely unsubscribe URL from an HTML email body."""
    # Find all <a href="...">...</a> tags
    anchors = re.findall(r'<a\s[^>]*href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', html, re.IGNORECASE | re.DOTALL)
    keywords = ("unsubscribe", "opt out", "opt-out", "manage preferences", "email preferences")
    for href, text in anchors:
        combined = (href + " " + re.sub(r"<[^>]+>", "", text)).lower()
        if any(k in combined for k in keywords):
            return href
    # Fallback: bare URL containing "unsub" in the text
    bare = re.findall(r'https?://[^\s"\'<>]+unsub[^\s"\'<>]*', html, re.IGNORECASE)
    return bare[0] if bare else None


def unsubscribe_via_claude(account, email_data, full_body=""):
    """
    Agentic fallback: hand the email body to Claude Code with Bash tool access
    so it can find and click the unsubscribe link in the body.
    """
    prompt = f"""You are helping unsubscribe from a marketing email. Use the Bash tool to complete this task.

Sender: {email_data['from']}
Subject: {email_data['subject']}
Account: {account['username']}

Email body (HTML/text, may be truncated):
{full_body[:8000]}

Instructions:
1. Find the unsubscribe link in the email body (look for text like "unsubscribe", "opt out", "manage preferences")
2. If it is a simple URL, use curl to GET it (e.g. curl -sL "<url>")
3. If the page requires clicking a button or filling a form, use Playwright via Python:
   python3 -c "
   from playwright.sync_api import sync_playwright
   with sync_playwright() as p:
       browser = p.chromium.launch()
       page = browser.new_page()
       page.goto('<url>')
       # find and click unsubscribe button
       page.get_by_text('unsubscribe', exact=False).first.click()
       page.wait_for_timeout(2000)
       browser.close()
   "
4. If a page asks for your email address to confirm, use: {account['username']}
5. Report what you did in one sentence.
6. If you cannot find an unsubscribe link or the page requires a login, respond with exactly: SKIP

Do not browse to any URL other than the unsubscribe URL found in the email body."""

    result = subprocess.run(
        [
            CLAUDE_BIN, "-p", prompt,
            "--allowedTools", "Bash",
            "--permission-mode", "auto",
            "--output-format", "json",
        ],
        capture_output=True,
        text=True,
        timeout=180,
    )

    response = json.loads(result.stdout) if result.stdout.strip() else {}
    output = response.get("result", "")
    print(f"  ↳ Claude: {output[:200]}")
    return "SKIP" not in output.upper()


def do_unsubscribe(account, email_data):
    """Try List-Unsubscribe header, then body link extraction, then Claude agentic."""
    header = email_data.get("list_unsubscribe", "")
    url = get_unsubscribe_url(header)
    mailto = get_unsubscribe_mailto(header)

    if url:
        try:
            requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
            print("  ↳ Unsubscribed via List-Unsubscribe URL")
            return
        except Exception as e:
            print(f"  ↳ Header URL failed ({e}), falling back to Claude")

    elif mailto:
        try:
            addr, _, params = mailto.partition("?")
            subject = "Unsubscribe"
            body_text = "Unsubscribe"
            for part in params.split("&"):
                if part.startswith("subject="):
                    subject = requests.utils.unquote(part[8:])
                if part.startswith("body="):
                    body_text = requests.utils.unquote(part[5:])
            with smtplib.SMTP(account["smtp_host"], account["smtp_port"]) as smtp:
                smtp.starttls()
                smtp.login(account["username"], account["password"])
                msg_text = (
                    f"From: {account['username']}\r\n"
                    f"To: {addr}\r\n"
                    f"Subject: {subject}\r\n\r\n"
                    f"{body_text}"
                )
                smtp.sendmail(account["username"], addr, msg_text)
            print(f"  ↳ Unsubscribed via mailto: {addr}")
            return
        except Exception as e:
            print(f"  ↳ mailto failed ({e}), falling back to Claude")

    # No header or header failed — try extracting link from body
    try:
        full_body = fetch_full_body(account, email_data["uid"])
        body_url = find_unsubscribe_in_body(full_body)
    except Exception as e:
        print(f"  ↳ Could not fetch body: {e}")
        body_url = None
        full_body = ""

    if body_url:
        try:
            requests.get(body_url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
            print("  ↳ Unsubscribed via body link")
            return
        except Exception as e:
            print(f"  ↳ Body link failed ({e}), falling back to Claude")

    # Last resort — Claude with Bash to handle interactive unsubscribe pages
    print("  ↳ Handing off to Claude for interactive unsubscribe...")
    unsubscribe_via_claude(account, email_data, full_body)


# ---------------------------------------------------------------------------
# IMAP actions
# ---------------------------------------------------------------------------

def delete_email(account, uid):
    mail = imaplib.IMAP4_SSL(account["imap_host"], account["imap_port"])
    mail.login(account["username"], account["password"])
    mail.select("INBOX")
    mail.uid("store", uid, "+FLAGS", "\\Deleted")
    mail.expunge()
    mail.logout()


def mark_spam_and_delete(account, uid):
    """For Gmail: move to [Gmail]/Spam. For others: just delete."""
    mail = imaplib.IMAP4_SSL(account["imap_host"], account["imap_port"])
    mail.login(account["username"], account["password"])

    # Try Gmail spam folder, fall back to plain delete
    if "gmail.com" in account["imap_host"]:
        mail.select("INBOX")
        mail.uid("copy", uid, "[Gmail]/Spam")

    mail.select("INBOX")
    mail.uid("store", uid, "+FLAGS", "\\Deleted")
    mail.expunge()
    mail.logout()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def resolve_category(item, email_data):
    category = item.get("category", "keep")
    combined = (email_data["from"] + " " + email_data["subject"]).lower()
    if any(w.lower() in combined for w in WHITELIST):
        category = "keep"
    return category


def process_item(item, email_map, account_map, stats):
    email_data = email_map.get((item["uid"], item["account"]))
    if not email_data:
        return

    account = account_map.get(item["account"])
    if not account:
        return

    category = resolve_category(item, email_data)
    print(f"[{category.upper()}] {email_data['from'][:45]} — {email_data['subject'][:50]}")

    if DRY_RUN:
        stats[category] = stats.get(category, 0) + 1
        return

    try:
        if category == "spam":
            mark_spam_and_delete(account, email_data["uid"])
            stats["spam"] += 1
        elif category == "marketing":
            do_unsubscribe(account, email_data)
            delete_email(account, email_data["uid"])
            stats["marketing"] += 1
        else:
            stats["keep"] += 1
    except Exception as e:
        print(f"  Error processing {email_data['uid']}: {e}")
        stats["error"] += 1


def process_chunk(chunk, account_map, stats):
    try:
        classifications = classify_with_claude(chunk)
    except Exception as e:
        print(f"  Classification failed: {e}")
        stats["error"] += len(chunk)
        return

    email_map = {(e["uid"], e["account"]): e for e in chunk}
    for item in classifications:
        process_item(item, email_map, account_map, stats)


def main():
    if not ACCOUNTS:
        print("No accounts configured. Edit the ACCOUNTS list in clean_emails.py.")
        return

    all_emails = []
    for account in ACCOUNTS:
        try:
            all_emails.extend(fetch_emails(account))
        except Exception as e:
            print(f"Error connecting to {account['name']}: {e}")

    print(f"\nTotal emails to classify: {len(all_emails)}")
    if not all_emails:
        print("Nothing to do.")
        return

    account_map = {a["name"]: a for a in ACCOUNTS}
    stats = {"spam": 0, "marketing": 0, "keep": 0, "error": 0}

    for i in range(0, len(all_emails), CHUNK_SIZE):
        chunk = all_emails[i : i + CHUNK_SIZE]
        print(f"\nClassifying emails {i + 1}–{i + len(chunk)}...")
        process_chunk(chunk, account_map, stats)

    print(f"\n{'DRY RUN — ' if DRY_RUN else ''}Done.")
    print(f"  Spam deleted:       {stats['spam']}")
    print(f"  Marketing removed:  {stats['marketing']}")
    print(f"  Kept:               {stats['keep']}")
    if stats["error"]:
        print(f"  Errors:             {stats['error']}")


if __name__ == "__main__":
    main()
