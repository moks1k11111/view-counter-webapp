"""
Email Password Encryption Module
Шифрование паролей почты с использованием Fernet (AES-128)
"""

import os
import logging
from cryptography.fernet import Fernet, InvalidToken

logger = logging.getLogger(__name__)


class EmailEncryption:
    """Encryption manager for email passwords using Fernet"""

    def __init__(self, encryption_key: str = None):
        """
        Initialize encryption with key

        Args:
            encryption_key: Base64-encoded Fernet key from environment variable
        """
        if not encryption_key:
            encryption_key = os.getenv('DB_ENCRYPTION_KEY')

        if not encryption_key:
            raise ValueError(
                "❌ DB_ENCRYPTION_KEY not found in environment variables. "
                "Generate key with: python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'"
            )

        try:
            # Ensure key is bytes
            if isinstance(encryption_key, str):
                encryption_key = encryption_key.encode()

            self.fernet = Fernet(encryption_key)
            logger.info("✅ Email encryption initialized")

        except Exception as e:
            raise ValueError(f"❌ Invalid encryption key: {e}")

    def encrypt(self, plain_password: str) -> str:
        """
        Encrypt email password

        Args:
            plain_password: Plain text password

        Returns:
            Encrypted password as base64 string
        """
        try:
            encrypted = self.fernet.encrypt(plain_password.encode())
            return encrypted.decode('utf-8')
        except Exception as e:
            logger.error(f"❌ Encryption error: {e}")
            raise

    def decrypt(self, encrypted_password: str) -> str:
        """
        Decrypt email password

        Args:
            encrypted_password: Encrypted password (base64 string)

        Returns:
            Plain text password
        """
        try:
            # Ensure encrypted password is bytes
            if isinstance(encrypted_password, str):
                encrypted_password = encrypted_password.encode()

            decrypted = self.fernet.decrypt(encrypted_password)
            return decrypted.decode('utf-8')

        except InvalidToken:
            logger.error("❌ Invalid encryption token - password cannot be decrypted")
            raise ValueError("Password decryption failed - invalid key or corrupted data")
        except Exception as e:
            logger.error(f"❌ Decryption error: {e}")
            raise

    @staticmethod
    def generate_key() -> str:
        """
        Generate new Fernet encryption key

        Returns:
            Base64-encoded key as string
        """
        key = Fernet.generate_key()
        return key.decode('utf-8')


# Singleton instance for easy access
_encryption_instance = None


def get_encryption() -> EmailEncryption:
    """Get or create encryption singleton instance"""
    global _encryption_instance
    if _encryption_instance is None:
        _encryption_instance = EmailEncryption()
    return _encryption_instance


if __name__ == "__main__":
    # Test encryption
    print("🔑 Generating new encryption key:")
    new_key = EmailEncryption.generate_key()
    print(f"Key (save to .env as DB_ENCRYPTION_KEY):\n{new_key}\n")

    # Test encrypt/decrypt
    print("🧪 Testing encryption:")
    test_password = "MySecurePassword123!"

    # Use the generated key for testing
    os.environ['DB_ENCRYPTION_KEY'] = new_key
    enc = EmailEncryption()

    encrypted = enc.encrypt(test_password)
    print(f"Plain: {test_password}")
    print(f"Encrypted: {encrypted}")

    decrypted = enc.decrypt(encrypted)
    print(f"Decrypted: {decrypted}")

    if test_password == decrypted:
        print("✅ Encryption test passed!")
    else:
        print("❌ Encryption test failed!")
