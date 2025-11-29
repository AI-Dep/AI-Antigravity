"""
Fixed Asset AI - Data Encryption Module

Provides encryption utilities for sensitive data at rest and in transit.

Features:
- AES-256-GCM encryption for field-level encryption
- Key derivation using PBKDF2
- Secure key management with environment variables
- Column-level encryption for sensitive database fields
- Transparent encryption/decryption for application use

Security Considerations:
- Never store encryption keys in code or version control
- Use environment variables or secure key management (AWS KMS, HashiCorp Vault)
- Rotate keys periodically
- Keep encrypted data and keys in separate locations

Author: Fixed Asset AI Team
"""

from __future__ import annotations

import os
import base64
import hashlib
import secrets
import logging
from typing import Optional, Union, Any
from functools import lru_cache

# Cryptography library for AES encryption
# NOTE: Import is deferred to avoid crashes on systems with broken cryptography
# installations (e.g., missing Rust bindings). Crypto will be initialized
# on first use if available.
CRYPTO_AVAILABLE = False
AESGCM = None
PBKDF2HMAC = None
_hashes = None
_default_backend = None
_crypto_init_attempted = False


def _try_import_crypto():
    """
    Attempt to import cryptography library safely.

    Returns True if successful, False otherwise.
    Call this before using any crypto functions.
    """
    global CRYPTO_AVAILABLE, AESGCM, PBKDF2HMAC, _hashes, _default_backend, _crypto_init_attempted

    if _crypto_init_attempted:
        return CRYPTO_AVAILABLE

    _crypto_init_attempted = True

    # Skip if explicitly disabled via environment variable
    if os.environ.get("FA_DISABLE_CRYPTO", "").lower() in ("1", "true", "yes"):
        return False

    try:
        # Import in a subprocess-safe way
        import importlib
        crypto_ciphers = importlib.import_module("cryptography.hazmat.primitives.ciphers.aead")
        crypto_kdf = importlib.import_module("cryptography.hazmat.primitives.kdf.pbkdf2")
        crypto_hashes = importlib.import_module("cryptography.hazmat.primitives.hashes")
        crypto_backend = importlib.import_module("cryptography.hazmat.backends")

        AESGCM = crypto_ciphers.AESGCM
        PBKDF2HMAC = crypto_kdf.PBKDF2HMAC
        _hashes = crypto_hashes
        _default_backend = crypto_backend.default_backend
        CRYPTO_AVAILABLE = True
        return True
    except Exception as e:
        logging.getLogger(__name__).debug(f"Cryptography import failed: {e}")
        return False


logger = logging.getLogger(__name__)


# ====================================================================================
# CONFIGURATION
# ====================================================================================

# Environment variable names for encryption keys
ENV_ENCRYPTION_KEY = "FA_ENCRYPTION_KEY"
ENV_ENCRYPTION_SALT = "FA_ENCRYPTION_SALT"

# Default encryption parameters
KEY_LENGTH = 32  # 256 bits for AES-256
NONCE_LENGTH = 12  # 96 bits for GCM
SALT_LENGTH = 16  # 128 bits
PBKDF2_ITERATIONS = 100000  # OWASP recommended minimum

# Sensitive field identifiers for automatic encryption
SENSITIVE_FIELDS = {
    "api_key",
    "password",
    "secret",
    "token",
    "credential",
    "ssn",
    "tax_id",
    "ein",
    "bank_account",
    "routing_number",
    "credit_card",
}


# ====================================================================================
# KEY MANAGEMENT
# ====================================================================================

class EncryptionKeyManager:
    """
    Manages encryption keys with secure derivation and storage.

    Keys are derived from a master key stored in environment variables.
    Never stores keys in memory longer than necessary.
    """

    def __init__(self, master_key: Optional[str] = None, salt: Optional[bytes] = None):
        """
        Initialize key manager.

        Args:
            master_key: Master encryption key (defaults to env var)
            salt: Salt for key derivation (defaults to env var or generates new)
        """
        if not CRYPTO_AVAILABLE:
            raise ImportError(
                "Encryption requires the 'cryptography' package. "
                "Install with: pip install cryptography"
            )

        self._master_key = master_key or os.environ.get(ENV_ENCRYPTION_KEY)

        if not self._master_key:
            logger.warning(
                f"No encryption key found in {ENV_ENCRYPTION_KEY}. "
                "Encryption will fail. Set the environment variable or generate a key."
            )

        # Get or generate salt
        salt_env = os.environ.get(ENV_ENCRYPTION_SALT)
        if salt:
            self._salt = salt
        elif salt_env:
            self._salt = base64.b64decode(salt_env)
        else:
            self._salt = secrets.token_bytes(SALT_LENGTH)
            logger.info(
                f"Generated new encryption salt. Save this in {ENV_ENCRYPTION_SALT}: "
                f"{base64.b64encode(self._salt).decode()}"
            )

    @property
    def salt_b64(self) -> str:
        """Get salt as base64 string for storage."""
        return base64.b64encode(self._salt).decode()

    def derive_key(self, purpose: str = "default") -> bytes:
        """
        Derive an encryption key for a specific purpose.

        Args:
            purpose: Purpose identifier (e.g., "database", "api", "export")
                    Different purposes get different derived keys

        Returns:
            32-byte derived key
        """
        if not self._master_key:
            raise ValueError(
                f"No master key available. Set {ENV_ENCRYPTION_KEY} environment variable."
            )

        # Combine master key with purpose for key separation
        key_material = f"{self._master_key}:{purpose}".encode()

        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=KEY_LENGTH,
            salt=self._salt,
            iterations=PBKDF2_ITERATIONS,
            backend=default_backend()
        )

        return kdf.derive(key_material)

    @staticmethod
    def generate_master_key() -> str:
        """
        Generate a new random master key.

        Returns:
            Base64-encoded 256-bit key
        """
        key = secrets.token_bytes(KEY_LENGTH)
        return base64.b64encode(key).decode()

    @staticmethod
    def generate_salt() -> str:
        """
        Generate a new random salt.

        Returns:
            Base64-encoded salt
        """
        salt = secrets.token_bytes(SALT_LENGTH)
        return base64.b64encode(salt).decode()


# ====================================================================================
# ENCRYPTION ENGINE
# ====================================================================================

class FieldEncryptor:
    """
    Encrypts and decrypts individual field values using AES-256-GCM.

    Uses authenticated encryption (AEAD) which provides both
    confidentiality and integrity protection.
    """

    def __init__(self, key_manager: Optional[EncryptionKeyManager] = None, purpose: str = "database"):
        """
        Initialize field encryptor.

        Args:
            key_manager: Key manager instance (creates default if None)
            purpose: Purpose for key derivation
        """
        if not CRYPTO_AVAILABLE:
            raise ImportError(
                "Encryption requires the 'cryptography' package. "
                "Install with: pip install cryptography"
            )

        self._key_manager = key_manager or EncryptionKeyManager()
        self._purpose = purpose
        self._key = None  # Lazy initialization

    def _get_key(self) -> bytes:
        """Get or derive the encryption key."""
        if self._key is None:
            self._key = self._key_manager.derive_key(self._purpose)
        return self._key

    def encrypt(self, plaintext: Union[str, bytes], associated_data: Optional[bytes] = None) -> str:
        """
        Encrypt a value.

        Args:
            plaintext: Value to encrypt (string or bytes)
            associated_data: Optional additional authenticated data (AAD)
                           Not encrypted but authenticated

        Returns:
            Base64-encoded encrypted value with format: nonce||ciphertext||tag
        """
        if plaintext is None:
            return None

        # Convert string to bytes
        if isinstance(plaintext, str):
            plaintext = plaintext.encode('utf-8')

        # Generate random nonce
        nonce = secrets.token_bytes(NONCE_LENGTH)

        # Encrypt
        aesgcm = AESGCM(self._get_key())
        ciphertext = aesgcm.encrypt(nonce, plaintext, associated_data)

        # Combine nonce + ciphertext and encode
        encrypted = nonce + ciphertext
        return base64.b64encode(encrypted).decode('utf-8')

    def decrypt(self, ciphertext_b64: str, associated_data: Optional[bytes] = None) -> str:
        """
        Decrypt a value.

        Args:
            ciphertext_b64: Base64-encoded encrypted value
            associated_data: Optional additional authenticated data (must match encryption)

        Returns:
            Decrypted string value

        Raises:
            ValueError: If decryption fails (wrong key, tampered data, etc.)
        """
        if ciphertext_b64 is None:
            return None

        try:
            # Decode base64
            encrypted = base64.b64decode(ciphertext_b64)

            # Extract nonce and ciphertext
            nonce = encrypted[:NONCE_LENGTH]
            ciphertext = encrypted[NONCE_LENGTH:]

            # Decrypt
            aesgcm = AESGCM(self._get_key())
            plaintext = aesgcm.decrypt(nonce, ciphertext, associated_data)

            return plaintext.decode('utf-8')

        except Exception as e:
            logger.error(f"Decryption failed: {e}")
            raise ValueError(f"Decryption failed: {e}")

    def is_encrypted(self, value: str) -> bool:
        """
        Check if a value appears to be encrypted.

        Args:
            value: String to check

        Returns:
            True if value looks like encrypted data
        """
        if not value or not isinstance(value, str):
            return False

        try:
            decoded = base64.b64decode(value)
            # Encrypted data should be at least nonce + tag (12 + 16 = 28 bytes)
            return len(decoded) >= 28
        except Exception:
            return False


# ====================================================================================
# DATABASE ENCRYPTION HELPERS
# ====================================================================================

class DatabaseEncryptionMixin:
    """
    Mixin class for adding encryption to database operations.

    Add to DatabaseManager to enable transparent field encryption.
    """

    _encryptor: Optional[FieldEncryptor] = None
    _encrypted_columns: dict = {}  # table_name -> set of column names

    @classmethod
    def configure_encryption(
        cls,
        encrypted_columns: dict,
        master_key: Optional[str] = None
    ):
        """
        Configure which columns should be encrypted.

        Args:
            encrypted_columns: Dict mapping table names to sets of column names
                              e.g., {"clients": {"contact_email", "phone"}}
            master_key: Optional master key (defaults to env var)

        Example:
            DatabaseEncryptionMixin.configure_encryption({
                "clients": {"contact_email", "phone", "notes"},
                "assets": {"custom_data"},
            })
        """
        if CRYPTO_AVAILABLE:
            key_manager = EncryptionKeyManager(master_key=master_key)
            cls._encryptor = FieldEncryptor(key_manager, purpose="database")
            cls._encrypted_columns = encrypted_columns
            logger.info(f"Database encryption configured for {len(encrypted_columns)} tables")
        else:
            logger.warning("Encryption not available - cryptography package not installed")

    def _encrypt_row(self, table_name: str, row_data: dict) -> dict:
        """
        Encrypt sensitive columns in a row before insert/update.

        Args:
            table_name: Name of the table
            row_data: Dict of column values

        Returns:
            Dict with encrypted values for sensitive columns
        """
        if not self._encryptor or table_name not in self._encrypted_columns:
            return row_data

        encrypted_cols = self._encrypted_columns[table_name]
        result = dict(row_data)

        for col_name, value in row_data.items():
            if col_name in encrypted_cols and value is not None:
                # Use row identifier as associated data if available
                aad = str(row_data.get('id', '')).encode() if 'id' in row_data else None
                result[col_name] = self._encryptor.encrypt(str(value), aad)

        return result

    def _decrypt_row(self, table_name: str, row_data: dict) -> dict:
        """
        Decrypt sensitive columns in a row after select.

        Args:
            table_name: Name of the table
            row_data: Dict of column values from database

        Returns:
            Dict with decrypted values for sensitive columns
        """
        if not self._encryptor or table_name not in self._encrypted_columns:
            return row_data

        encrypted_cols = self._encrypted_columns[table_name]
        result = dict(row_data)

        for col_name, value in row_data.items():
            if col_name in encrypted_cols and value is not None:
                try:
                    aad = str(row_data.get('id', '')).encode() if 'id' in row_data else None
                    result[col_name] = self._encryptor.decrypt(value, aad)
                except ValueError:
                    # Value might not be encrypted (legacy data)
                    logger.debug(f"Could not decrypt {col_name} - may be unencrypted legacy data")
                    result[col_name] = value

        return result


# ====================================================================================
# UTILITY FUNCTIONS
# ====================================================================================

def generate_encryption_config() -> dict:
    """
    Generate a new encryption configuration.

    Returns:
        Dict with encryption key and salt for environment variables
    """
    return {
        ENV_ENCRYPTION_KEY: EncryptionKeyManager.generate_master_key(),
        ENV_ENCRYPTION_SALT: EncryptionKeyManager.generate_salt(),
    }


def mask_sensitive_value(value: str, show_chars: int = 4) -> str:
    """
    Mask a sensitive value for display (e.g., API keys).

    Args:
        value: Value to mask
        show_chars: Number of characters to show at end

    Returns:
        Masked string like "****abcd"
    """
    if not value:
        return ""

    if len(value) <= show_chars:
        return "*" * len(value)

    return "*" * (len(value) - show_chars) + value[-show_chars:]


def hash_for_lookup(value: str, salt: Optional[str] = None) -> str:
    """
    Create a deterministic hash for encrypted field lookups.

    Since encrypted values are non-deterministic (random nonce),
    use this to create a searchable hash for lookups.

    Args:
        value: Value to hash
        salt: Optional salt (uses env var if not provided)

    Returns:
        Base64-encoded SHA-256 hash
    """
    if not value:
        return ""

    salt_bytes = (salt or os.environ.get(ENV_ENCRYPTION_SALT, "")).encode()
    combined = salt_bytes + value.encode()

    hash_bytes = hashlib.sha256(combined).digest()
    return base64.b64encode(hash_bytes).decode()


def is_sensitive_field(field_name: str) -> bool:
    """
    Check if a field name suggests sensitive data.

    Args:
        field_name: Column/field name to check

    Returns:
        True if field name suggests sensitive data
    """
    field_lower = field_name.lower()
    return any(sensitive in field_lower for sensitive in SENSITIVE_FIELDS)


# ====================================================================================
# SINGLETON ACCESS
# ====================================================================================

_default_encryptor: Optional[FieldEncryptor] = None


def get_encryptor() -> Optional[FieldEncryptor]:
    """
    Get the default field encryptor (singleton).

    Returns:
        FieldEncryptor instance or None if encryption not configured
    """
    global _default_encryptor

    if _default_encryptor is None and CRYPTO_AVAILABLE:
        try:
            _default_encryptor = FieldEncryptor()
        except Exception as e:
            logger.warning(f"Could not initialize encryptor: {e}")

    return _default_encryptor


def encrypt_value(value: str) -> Optional[str]:
    """
    Convenience function to encrypt a single value.

    Args:
        value: Value to encrypt

    Returns:
        Encrypted value or None if encryption not available
    """
    encryptor = get_encryptor()
    if encryptor:
        return encryptor.encrypt(value)
    return value


def decrypt_value(value: str) -> Optional[str]:
    """
    Convenience function to decrypt a single value.

    Args:
        value: Encrypted value

    Returns:
        Decrypted value or original if decryption fails
    """
    encryptor = get_encryptor()
    if encryptor:
        try:
            return encryptor.decrypt(value)
        except ValueError:
            return value
    return value
