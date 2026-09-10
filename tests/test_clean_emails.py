import sys
import types

import requests

fake_env = types.ModuleType("env")
fake_env.ACCOUNTS = []
fake_env.WHITELIST = []
sys.modules.setdefault("env", fake_env)

import clean_emails


def account():
    return {
        "name": "test",
        "username": "person@example.test",
        "password": "secret",
        "imap_host": "imap.example.test",
        "imap_port": 993,
        "smtp_host": "smtp.example.test",
        "smtp_port": 587,
    }


def email_data():
    return {
        "uid": "42",
        "account": "test",
        "from": "News <news@example.test>",
        "subject": "Weekly news",
        "list_unsubscribe": "<https://example.test/unsubscribe>",
    }


def stats():
    return {"spam": 0, "marketing": 0, "keep": 0, "error": 0}


def test_destructive_actions_are_disabled_by_default():
    assert clean_emails.DRY_RUN is True


def test_unsubscribe_http_error_falls_back_instead_of_reporting_success(monkeypatch):
    response = requests.Response()
    response.status_code = 500
    monkeypatch.setattr(clean_emails.requests, "get", lambda *args, **kwargs: response)
    monkeypatch.setattr(clean_emails, "fetch_full_body", lambda *args, **kwargs: "")

    fallbacks = []
    monkeypatch.setattr(
        clean_emails,
        "unsubscribe_via_claude",
        lambda *args, **kwargs: fallbacks.append(True) or False,
    )

    clean_emails.do_unsubscribe(account(), email_data())

    assert fallbacks == [True]


def test_process_chunk_rejects_non_list_classifier_output_without_crashing(monkeypatch):
    chunk = [email_data()]
    result_stats = stats()
    monkeypatch.setattr(clean_emails, "classify_with_claude", lambda _: {"uid": "42"})

    clean_emails.process_chunk(chunk, {"test": account()}, result_stats)

    assert result_stats["error"] == 1


def test_process_chunk_skips_malformed_rows_and_continues(monkeypatch):
    chunk = [email_data()]
    result_stats = stats()
    monkeypatch.setattr(
        clean_emails,
        "classify_with_claude",
        lambda _: [
            {"uid": "42", "category": "keep"},
            {"uid": "42", "account": "test", "category": "keep"},
        ],
    )

    clean_emails.process_chunk(chunk, {"test": account()}, result_stats)

    assert result_stats == {"spam": 0, "marketing": 0, "keep": 1, "error": 1}


def test_unknown_classifier_category_fails_safe_to_keep():
    assert (
        clean_emails.resolve_category(
            {"category": "destroy"},
            {"from": "sender@example.test", "subject": "hello"},
        )
        == "keep"
    )


def test_whitelist_matches_sender_domain_not_subject(monkeypatch):
    monkeypatch.setattr(clean_emails, "WHITELIST", ["trusted.example"])

    category = clean_emails.resolve_category(
        {"category": "spam"},
        {"from": "Attacker <evil@example.test>", "subject": "trusted.example invoice"},
    )

    assert category == "spam"


def test_whitelist_accepts_subdomains_of_sender_domain(monkeypatch):
    monkeypatch.setattr(clean_emails, "WHITELIST", ["trusted.example"])

    category = clean_emails.resolve_category(
        {"category": "spam"},
        {"from": "Alerts <news@mail.trusted.example>", "subject": "hello"},
    )

    assert category == "keep"


def test_process_chunk_does_not_process_duplicate_classifier_rows(monkeypatch):
    chunk = [email_data()]
    result_stats = stats()
    monkeypatch.setattr(
        clean_emails,
        "classify_with_claude",
        lambda _: [
            {"uid": "42", "account": "test", "category": "keep"},
            {"uid": "42", "account": "test", "category": "spam"},
        ],
    )

    clean_emails.process_chunk(chunk, {"test": account()}, result_stats)

    assert result_stats == {"spam": 0, "marketing": 0, "keep": 1, "error": 1}


def test_process_chunk_counts_missing_classifier_rows_as_errors(monkeypatch):
    second = {**email_data(), "uid": "43", "subject": "Another message"}
    chunk = [email_data(), second]
    result_stats = stats()
    monkeypatch.setattr(
        clean_emails,
        "classify_with_claude",
        lambda _: [{"uid": "42", "account": "test", "category": "keep"}],
    )

    clean_emails.process_chunk(chunk, {"test": account()}, result_stats)

    assert result_stats == {"spam": 0, "marketing": 0, "keep": 1, "error": 1}
