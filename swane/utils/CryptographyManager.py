import platform
import subprocess
import hashlib
import os


class CryptographyManager:
    """
    Criptography manager service

    Attributes
    ----------
    cryptography_key : str
        The key to use for the encryption/decryption processes.

    """

    cryptography_key: str = ""

    def __init__(self):
        """
        The CryptographyManager initializer.

        """

        # Reading the system uuid and setting it as cryptography_key
        self.get_system_uuid()

    def get_system_uuid(self):
        """
        Reads the system uuid and setting it as cryptography_key

        """

        try:
            system = platform.system()
            if system == "Darwin" or platform.mac_ver()[0]:
                # macOS
                self.cryptography_key = (
                    subprocess.check_output(
                        "ioreg -rd1 -c IOPlatformExpertDevice | awk '/IOPlatformUUID/ { print $3; }'",
                        shell=True,
                    )
                    .decode()
                    .strip()
                    .strip('"')
                )
            elif system == "Linux":
                # Linux
                self.cryptography_key = (
                    subprocess.check_output(
                        "cat /sys/class/dmi/id/product_uuid", shell=True
                    )
                    .decode()
                    .strip()
                )
            else:
                raise Exception("OS not supported")

        except Exception:
            raise

    def get_hashed_key(self):
        """
        Uses the SHA-256 to obtain a 32 byte (256 bit) key from the CryptographyManager cryptography_key
        
        Returns
        ----------
        str
            The cryptography hashed key.
        
        """

        return hashlib.sha256(self.cryptography_key.encode()).digest()

    def xor_encrypt_decrypt(self, data: str):
        """
        Uses XOR to encrypt and decript a string of char or bytes.
        
        Parameters
        ----------
        data : str
            The string representing the chars or the bytes to encrypt/decript.
            
        Returns
        ----------
        str
            The encrypted/decrypted data.

        """
        
        # Cifratura e decifratura con XOR
        key_len = len(self.cryptography_key)
        return bytes(
            [data[i] ^ self.cryptography_key[i % key_len] for i in range(len(data))]
        )

    def encrypt(self, string: str):
        """
        Encrypts the string with the CryptograpyManager key.
        
        Parameters
        ----------
        string : str
            The string to encrypt.
            
        Returns
        ----------
        str
            The encrypted string.

        """

        try:
            # Hash l'UUID per ottenere una chiave
            key = self.get_hashed_key()

            # Test di cifratura e decifratura
            string_bytes = string.encode()

            # Cifrare la stringa
            encrypted_bytes = self.xor_encrypt_decrypt(string_bytes, key)

            return encrypted_bytes

        except Exception:
            raise

    def decrypt(self, string: str):
        """
        Decrypts the string with the CryptograpyManager key.
        
        Parameters
        ----------
        string : str
            The string to decrypt.
            
        Returns
        ----------
        str
            The decrypted string.

        """

        try:
            decrypted_bytes = self.xor_encrypt_decrypt(string)
            decrypted_text = decrypted_bytes.decode()

            return decrypted_text
        except Exception:
            raise
