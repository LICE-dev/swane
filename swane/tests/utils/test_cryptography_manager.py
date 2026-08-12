"""Unit tests for :class:`swane.utils.CryptographyManager.CryptographyManager`."""

import pytest

from swane.utils.CryptographyManager import CryptographyManager


def test_encrypt_decrypt_round_trip():
    secret = "my-mail-password:42"
    token = CryptographyManager.encrypt(secret)
    assert token != secret
    assert CryptographyManager.decrypt(token) == secret


def test_encrypt_is_non_deterministic_but_reversible():
    # Fernet embeds a random IV, so two encryptions differ yet both decrypt back.
    token1 = CryptographyManager.encrypt("same")
    token2 = CryptographyManager.encrypt("same")
    assert token1 != token2
    assert CryptographyManager.decrypt(token1) == "same"
    assert CryptographyManager.decrypt(token2) == "same"


def test_decrypt_rejects_tampered_token():
    from cryptography.fernet import InvalidToken

    token = CryptographyManager.encrypt("data")
    tampered = token[:-2] + ("aa" if not token.endswith("aa") else "bb")
    with pytest.raises(InvalidToken):
        CryptographyManager.decrypt(tampered)
