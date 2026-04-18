<img src="banner.svg" alt="email-cleaner banner" width="100%"/>

# email-cleaner

> Automatically classify and clean your inbox using Claude AI — delete spam, unsubscribe from marketing, and keep what matters.

---

## What it does

email-cleaner connects to your email accounts over IMAP, feeds your recent messages to Claude AI for classification, then acts on the results:

| Category | Action |
|---|---|
| **Spam** | Moved to spam folder and deleted |
| **Marketing** | Unsubscribed (multi-layer) then deleted |
| **Keep** | Left untouched in your inbox |

A **whitelist** lets you protect any sender domain from ever being deleted, no matter what the AI decides.

---

## How unsubscribing works

The tool tries four layers before giving up:

1. Follows the `List-Unsubscribe` header URL
2. Sends an unsubscribe email via `List-Unsubscribe` mailto
3. Extracts and visits an unsubscribe link from the email body
4. Hands off to Claude with Playwright browser automation for interactive forms

---

## Setup

**Requirements:** Python 3, [Claude Code CLI](https://claude.ai/code) installed and logged in.

```bash
# 1. Clone
git clone https://github.com/yourusername/email-cleaner.git
cd email-cleaner

# 2. Install dependencies
./setup.sh

# 3. Configure your accounts
cp env.example.py env.py
# Edit env.py with your credentials
```

### env.py format

```python
ACCOUNTS = [
    {
        "imap_host": "imap.gmail.com",
        "imap_port": 993,
        "smtp_host": "smtp.gmail.com",
        "smtp_port": 587,
        "email": "you@gmail.com",
        "password": "your-app-password",   # Gmail: use an App Password
    }
]

WHITELIST = ["mybank.com", "github.com"]  # always keep emails from these domains
```

> **Gmail users:** Enable IMAP in settings and generate an [App Password](https://myaccount.google.com/apppasswords) — do not use your regular password.

---

## Usage

```bash
# Dry run (default) — classifies emails but takes no action
python3 clean_emails.py

# Enable deletion — edit the top of clean_emails.py:
#   DRY_RUN = False
python3 clean_emails.py
```

You can also tune these constants at the top of `clean_emails.py`:

| Constant | Default | Description |
|---|---|---|
| `DAYS_BACK` | `14` | How many days of email to scan |
| `DRY_RUN` | `True` | Preview mode — no emails deleted |
| `CHUNK_SIZE` | `50` | Emails sent per Claude API call |

### Automate with cron

```bash
# Run every Sunday at 9am, log results
0 9 * * 0 cd /path/to/email-cleaner && python3 clean_emails.py >> logs/cleanup.log 2>&1
```

---

## Security

- `env.py` is git-ignored — your credentials never leave your machine
- All processing is local; no email data is sent to any third-party service
- Claude AI runs via the local Claude Code CLI, not the cloud API

---

## Project structure

```
email-cleaner/
├── clean_emails.py     # Core logic
├── env.example.py      # Credentials template
├── env.py              # Your credentials (git-ignored)
├── setup.sh            # Dependency installer
└── logs/               # Run logs (git-ignored)
```

---

## License

MIT
