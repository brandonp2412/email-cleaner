#!/usr/bin/env bash
# One-time setup for email-cleaner
set -e

echo "Installing Python dependencies..."
pip install requests python-dotenv playwright

echo "Installing Playwright browser (for agentic unsubscribe)..."
playwright install chromium

echo ""
echo "Setup complete. Next steps:"
echo ""
echo "1. Copy .env.example to .env and fill in your passwords"
echo "   cp .env.example .env"
echo ""
echo "2. Edit clean_emails.py — uncomment and configure your accounts in the ACCOUNTS list"
echo ""
echo "3. Run a dry run first to check classifications:"
echo "   python3 clean_emails.py"
echo "   (DRY_RUN=True by default — nothing gets deleted)"
echo ""
echo "4. When happy, set DRY_RUN = False in clean_emails.py and run again"
echo ""
echo "5. Set up the weekly cron (edit crontab -e):"
echo "   0 9 * * 0 cd $(pwd) && set -a && source .env && set +a && python3 clean_emails.py >> logs/cleanup.log 2>&1"
echo ""
echo "For Gmail accounts:"
echo "  - Enable IMAP: Gmail Settings → See all settings → Forwarding and POP/IMAP → Enable IMAP"
echo "  - Create an App Password: Google Account → Security → 2-Step Verification → App Passwords"
