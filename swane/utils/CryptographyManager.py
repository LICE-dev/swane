import uuid
import base64
from functools import cache


class CryptographyManager:
    """
    Criptography manager service

    Attributes
    ----------
    password : bytes
        The secret the encryption key is derived from.
    salt : bytes
        The salt used for the key derivation.

    """

    password = str(uuid.getnode()).encode()
    salt = b"\x84mt\xec\xcc\xd1\n\xe5\xe8\x86`\xce\xe3\x9aa\xcd"

    @staticmethod
    @cache
    def cryptography_key() -> bytes:
        """
        Derives the encryption key on first use. cryptography is imported and
        the (slow) key derivation runs here, not at module import, to keep them
        off GUI startup.
        """
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=CryptographyManager.salt,
            iterations=390000,
        )
        return base64.urlsafe_b64encode(kdf.derive(CryptographyManager.password))

    @staticmethod
    def encrypt(string: str) -> str:
        from cryptography.fernet import Fernet

        fernet = Fernet(CryptographyManager.cryptography_key())
        encMessage = fernet.encrypt(string.encode())
        return encMessage.decode()

    @staticmethod
    def decrypt(string: str) -> str:
        from cryptography.fernet import Fernet

        fernet = Fernet(CryptographyManager.cryptography_key())
        decMessage = fernet.decrypt(string.encode()).decode()
        return str(decMessage)
