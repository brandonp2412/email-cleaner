<img src="banner.svg" alt="email-cleaner banner" width="100%"/>

# email-cleaner

> Automatically classify and clean your inbox using Claude AI — delete spam, unsubscribe from marketing, and keep what matters.

---

## What it does

email-cleaner connects to your email accounts over IMAP, feeds recent message metadata to Claude for classification, then acts on the results:

| Category | Action |
|---|---|
| **Spam** | Moved to spam where supported, then removed from the inbox |
| **Marketing** | Unsubscribed (multi-layer) then deleted only after unsubscribe success is confirmed |
| **Keep** | Left untouched in your inbox |

A **whitelist** lets you protect sender/domain text from destructive actions regardless of the AI classification.

---

## How unsubscribing works

The tool tries four layers before giving up:

1. Follows the `List-Unsubscribe` header URL and requires a successful HTTP response
2. Sends an unsubscribe email via `List-Unsubscribe` mailto
3. Extracts and visits an unsubscribe link from the email body
4. Hands off to Claude with Playwright/browser automation for interactive forms

If every unsubscribe method fails, the marketing email is left untouched rather than being deleted while the subscription remains active.

---

## Setup

**Requirements:** Python 3 and [Claude Code CLI](https://claude.ai/code) installed and logged in.

```bash
# 1. Clone
git clone https://github.com/brandonp2412/email-cleaner.git
cd email-cleaner

# 2. Install dependencies
./setup.sh

# 3. Configure your accounts
cp env.example.py env.py
# Edit env.py with your account details
```

### env.py format

```python
ACCOUNTS = [
    {
        "name": "gmail_1",
        "imap_host": "imap.gmail.com",
        "imap_port": 993,
        "smtp_host": "smtp.gmail.com",
        "smtp_port": 587,
        "username": "you@gmail.com",
        "password": "your-app-password",
    }
]

WHITELIST = ["mybank.com", "github.com"]
```

For Gmail, use an App Password where required instead of your normal account password.

---

## Usage

```bash
# Dry run (default) — classifies emails but takes no destructive action
python3 clean_emails.py

# Enable cleanup only after reviewing dry-run output:
#   DRY_RUN = False
python3 clean_emails.py
```

You can tune these constants at the top of `clean_emails.py`:

| Constant | Default | Description |
|---|---:|---|
| `DAYS_BACK` | `14` | How many days of email to scan |
| `DRY_RUN` | `True` | Preview mode — no emails deleted |
| `CHUNK_SIZE` | `50` | Emails sent per Claude classification call |

### Automate with cron

```bash
# Run every Sunday at 9am, log results
0 9 * * 0 cd /path/to/email-cleaner && python3 clean_emails.py >> logs/cleanup.log 2>&1
```

---

## Privacy and security

- `env.py` is git-ignored so credentials are not committed by default.
- Email metadata used for classification is passed to the configured Claude Code service; interactive unsubscribe fallback can also include up to 8,000 characters of the selected message body.
- Unsubscribe URLs are visited over the network and mailto unsubscribe requests may be sent through the configured SMTP account.
- Destructive email actions are disabled by default with `DRY_RUN=True`.

---

## Project structure

```
email-cleaner/
├── clean_emails.py     # Core logic
├── env.example.py      # Credentials/config template
├── env.py              # Local configuration (git-ignored)
├── setup.sh            # Dependency installer
└── tests/              # Safety regression tests
```

---

## License

MIT
