import sys
import types
import unittest
from unittest.mock import Mock, patch

fake_env = types.ModuleType("env")
fake_env.ACCOUNTS = []
fake_env.WHITELIST = []
sys.modules.setdefault("env", fake_env)

import clean_emails


class SafetyDefaultsTests(unittest.TestCase):
    def test_first_run_is_dry_by_default(self):
        self.assertTrue(clean_emails.DRY_RUN)
        self.assertEqual(clean_emails.DAYS_BACK, 14)

    @patch("clean_emails.requests.get")
    def test_unsubscribe_http_errors_are_not_reported_as_success(self, get):
        response = Mock()
        response.raise_for_status.side_effect = RuntimeError("500 Server Error")
        get.return_value = response

        with self.assertRaises(RuntimeError):
            clean_emails.visit_unsubscribe_url("https://example.test/unsubscribe")

        response.raise_for_status.assert_called_once_with()

    @patch("clean_emails.smtplib.SMTP")
    def test_mailto_unsubscribe_decodes_query_values(self, smtp_class):
        smtp = smtp_class.return_value.__enter__.return_value
        account = {
            "username": "user@example.test",
            "password": "secret",
            "smtp_host": "smtp.example.test",
            "smtp_port": 587,
        }
        email_data = {
            "uid": "42",
            "from": "Sender <sender@example.test>",
            "subject": "Sale",
            "list_unsubscribe": (
                "<mailto:unsubscribe@example.test?SUBJECT=Remove+Me"
                "&body=Please+unsubscribe+me%21>"
            ),
        }

        self.assertTrue(clean_emails.do_unsubscribe(account, email_data))

        smtp.sendmail.assert_called_once()
        sent_message = smtp.sendmail.call_args.args[2]
        self.assertIn("Subject: Remove Me", sent_message)
        self.assertIn("Please unsubscribe me!", sent_message)

    @patch("clean_emails.unsubscribe_via_claude", return_value=False)
    @patch("clean_emails.fetch_full_body", return_value="")
    @patch("clean_emails.visit_unsubscribe_url", side_effect=RuntimeError("failed"))
    def test_failed_unsubscribe_returns_false(self, _visit, _body, _claude):
        account = {
            "username": "user@example.test",
            "password": "secret",
            "smtp_host": "smtp.example.test",
            "smtp_port": 587,
        }
        email_data = {
            "uid": "42",
            "from": "Sender <sender@example.test>",
            "subject": "Sale",
            "list_unsubscribe": "<https://example.test/unsubscribe>",
        }

        self.assertFalse(clean_emails.do_unsubscribe(account, email_data))


class ClassificationSafetyTests(unittest.TestCase):
    def setUp(self):
        self.original_dry_run = clean_emails.DRY_RUN
        clean_emails.DRY_RUN = True

    def tearDown(self):
        clean_emails.DRY_RUN = self.original_dry_run

    @patch("clean_emails.classify_with_claude")
    def test_duplicate_classification_is_processed_once(self, classify):
        email = {
            "uid": "1",
            "account": "test",
            "from": "sender@example.test",
            "subject": "message",
        }
        classification = {"uid": "1", "account": "test", "category": "spam"}
        classify.return_value = [classification, classification.copy()]
        stats = {"spam": 0, "marketing": 0, "keep": 0, "error": 0}

        clean_emails.process_chunk([email], {"test": {"name": "test"}}, stats)

        self.assertEqual(stats["spam"], 1)
        self.assertEqual(stats["error"], 1)

    @patch("clean_emails.classify_with_claude", return_value=[])
    def test_omitted_classification_is_counted_and_left_untouched(self, _classify):
        email = {
            "uid": "1",
            "account": "test",
            "from": "sender@example.test",
            "subject": "message",
        }
        stats = {"spam": 0, "marketing": 0, "keep": 0, "error": 0}

        clean_emails.process_chunk([email], {"test": {"name": "test"}}, stats)

        self.assertEqual(stats, {"spam": 0, "marketing": 0, "keep": 0, "error": 1})

    def test_unknown_category_fails_safe_to_keep(self):
        email = {"from": "sender@example.test", "subject": "message"}
        self.assertEqual(
            clean_emails.resolve_category({"category": "delete-everything"}, email),
            "keep",
        )

    def test_non_list_classifier_output_is_rejected(self):
        email = {
            "uid": "1",
            "account": "test",
            "from": "sender@example.test",
            "subject": "message",
        }
        stats = {"spam": 0, "marketing": 0, "keep": 0, "error": 0}
        with patch("clean_emails.classify_with_claude", return_value={"uid": "1"}):
            clean_emails.process_chunk([email], {"test": {"name": "test"}}, stats)
        self.assertEqual(stats["error"], 1)

    def test_whitelist_matches_sender_domain_not_subject(self):
        email = {
            "from": "Attacker <evil@example.test>",
            "subject": "trusted.example invoice",
        }
        with patch.object(clean_emails, "WHITELIST", ["trusted.example"]):
            self.assertEqual(clean_emails.resolve_category({"category": "spam"}, email), "spam")

    def test_whitelist_accepts_sender_subdomains(self):
        email = {
            "from": "Alerts <news@mail.trusted.example>",
            "subject": "hello",
        }
        with patch.object(clean_emails, "WHITELIST", ["trusted.example"]):
            self.assertEqual(clean_emails.resolve_category({"category": "spam"}, email), "keep")


if __name__ == "__main__":
    unittest.main()
