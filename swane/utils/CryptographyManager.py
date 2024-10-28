import uuid
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
import base64


class CryptographyManager:
    """
    Criptography manager service

    Attributes
    ----------
    cryptography_key : str
        The key to use for the encryption/decryption processes.

    """

    password = str(uuid.getnode()).encode()
    salt = b'\x84mt\xec\xcc\xd1\n\xe5\xe8\x86`\xce\xe3\x9aa\xcd'
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=390000,
    )
    cryptography_key = base64.urlsafe_b64encode(kdf.derive(password))


    @staticmethod
    def encrypt(string: str) -> str:
        fernet = Fernet(CryptographyManager.cryptography_key)
        encMessage = fernet.encrypt(string.encode())
        return encMessage.decode()

    @staticmethod
    def decrypt(string: str) -> str:
        fernet = Fernet(CryptographyManager.cryptography_key)
        decMessage = fernet.decrypt(string.encode()).decode()
        return str(decMessage)

