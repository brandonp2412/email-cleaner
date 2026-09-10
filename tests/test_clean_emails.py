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

        clean_emails.process_chunk([email], {"test": {}}, stats)

        self.assertEqual(stats["spam"], 1)
        self.assertEqual(stats["error"], 0)

    @patch("clean_emails.classify_with_claude", return_value=[])
    def test_omitted_classification_is_counted_and_left_untouched(self, _classify):
        email = {
            "uid": "1",
            "account": "test",
            "from": "sender@example.test",
            "subject": "message",
        }
        stats = {"spam": 0, "marketing": 0, "keep": 0, "error": 0}

        clean_emails.process_chunk([email], {"test": {}}, stats)

        self.assertEqual(stats, {"spam": 0, "marketing": 0, "keep": 0, "error": 1})

    def test_unknown_category_fails_safe_to_keep(self):
        email = {"from": "sender@example.test", "subject": "message"}
        self.assertEqual(
            clean_emails.resolve_category({"category": "delete-everything"}, email),
            "keep",
        )


if __name__ == "__main__":
    unittest.main()
