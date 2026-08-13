"""Unit tests for :class:`swane.utils.MailManager.MailManager` (SMTP mocked)."""

import smtplib

import pytest

from swane.utils.MailManager import MailManager


class FakeSMTP:
    """Records the SMTP interaction without touching the network."""

    instances = []

    def __init__(self, address, port, timeout=None):
        self.address = address
        self.port = port
        self.timeout = timeout
        self.events = []
        self.sent = []
        FakeSMTP.instances.append(self)

    def ehlo(self):
        self.events.append("ehlo")

    def starttls(self):
        self.events.append("starttls")

    def login(self, username, password):
        self.events.append(("login", username, password))

    def send_message(self, message):
        self.sent.append(message)

    def quit(self):
        self.events.append("quit")


@pytest.fixture(autouse=True)
def _reset_instances():
    FakeSMTP.instances = []
    yield
    FakeSMTP.instances = []


def test_send_mail_uses_ssl_and_builds_message(monkeypatch):
    monkeypatch.setattr(smtplib, "SMTP_SSL", FakeSMTP)

    mgr = MailManager("smtp.example.com", 465, "me@example.com", "pw", use_ssl=True)
    mgr.send_mail("me@example.com", "you@example.com", "Subj", "<b>hi</b>")

    assert len(FakeSMTP.instances) == 1
    server = FakeSMTP.instances[0]
    assert ("login", "me@example.com", "pw") in server.events
    assert "quit" in server.events
    assert len(server.sent) == 1
    message = server.sent[0]
    assert message["From"] == "me@example.com"
    assert message["To"] == "you@example.com"
    assert message["Subject"] == "Subj"


def test_connect_plain_uses_tls_handshake(monkeypatch):
    monkeypatch.setattr(smtplib, "SMTP", FakeSMTP)

    mgr = MailManager(
        "smtp.example.com", 587, "me@example.com", "pw", use_ssl=False, use_tls=True
    )
    mgr.connect()

    server = FakeSMTP.instances[0]
    assert server.events.count("ehlo") == 2
    assert "starttls" in server.events


def test_connect_failure_is_wrapped(monkeypatch):
    class BoomSMTP(FakeSMTP):
        def login(self, username, password):
            raise OSError("connection refused")

    monkeypatch.setattr(smtplib, "SMTP_SSL", BoomSMTP)
    mgr = MailManager("smtp.example.com", 465, "me@example.com", "pw")
    with pytest.raises(Exception, match="Check your Mail Configuration"):
        mgr.connect()


def test_send_report_subject_and_addresses(monkeypatch):
    monkeypatch.setattr(smtplib, "SMTP_SSL", FakeSMTP)

    mgr = MailManager("smtp.example.com", 465, "me@example.com", "pw")
    mgr.send_report("<p>report</p>")

    message = FakeSMTP.instances[0].sent[0]
    assert message["From"] == "me@example.com"
    assert message["To"] == "me@example.com"
    assert message["Subject"].startswith("SWANe - ")
