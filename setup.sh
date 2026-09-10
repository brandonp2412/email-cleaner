#!/usr/bin/env bash
set -euo pipefail

echo "Installing Python dependencies..."
python3 -m pip install requests playwright

echo "Installing Playwright browser (for agentic unsubscribe)..."
python3 -m playwright install chromium

echo ""
echo "Setup complete. Next steps:"
echo ""
echo "1. Copy the Python config template and fill in your account details:"
echo "   cp env.example.py env.py"
echo ""
echo "2. Edit env.py and configure ACCOUNTS and WHITELIST."
echo ""
echo "3. Run a dry run first to check classifications:"
echo "   python3 clean_emails.py"
echo "   (DRY_RUN=True by default — nothing gets deleted)"
echo ""
echo "4. When happy, set DRY_RUN = False in clean_emails.py and run again."
echo ""
echo "5. Optional weekly cron:"
echo "   0 9 * * 0 cd $(pwd) && python3 clean_emails.py >> logs/cleanup.log 2>&1"
echo ""
echo "For Gmail accounts:"
echo "  - Enable IMAP in Gmail settings if required by your account."
echo "  - Create an App Password instead of storing your normal account password."
