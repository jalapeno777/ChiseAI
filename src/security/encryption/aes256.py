"""AES-256 Encryption Implementation for NFR-008 Security Hardening."""
import base64
import hashlib
import logging
import os
import secrets
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from enum import Enum
from typing import Optional, Union

logger = logging.getLogger(__name__)

# Try to import cryptography, fall back to basic implementation
try:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    from cryptography.hazmat.backends import default_backend
    HAS_CRYPTOGRAPHY = True
except ImportError:
    HAS_CRYPTOGRAPHY = False
    logger.warning("cryptography package not available, using fallback implementation")


class EncryptionMode(Enum):
    GCM = "gcm"  # Galois/Counter Mode (authenticated encryption)
    CBC = "cbc"  # Cipher Block Chaining


@dataclass
class EncryptedData:
    """Container for encrypted data with metadata."""
    ciphertext: bytes
    nonce: bytes  # IV for CBC, nonce for GCM
    tag: Optional[bytes] = None  # Authentication tag for GCM
    version: int = 1
    algorithm: str = "AES-256-GCM"
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    key_id: Optional[str] = None
    
    def to_dict(self) -> dict:
        return {
            "ciphertext": base64.b64encode(self.ciphertext).decode(),
            "nonce": base64.b64encode(self.nonce).decode(),
            "tag": base64.b64encode(self.tag).decode() if self.tag else None,
            "version": self.version,
            "algorithm": self.algorithm,
            "timestamp": self.timestamp.isoformat(),
            "key_id": self.key_id,
        }
    
    def to_bytes(self) -> bytes:
        """Serialize to bytes for storage/transmission."""
        # Format: version(1) | nonce_len(2) | tag_len(2) | nonce | tag | ciphertext
        nonce_len = len(self.nonce)
        tag_len = len(self.tag) if self.tag else 0
        header = bytes([self.version, nonce_len >> 8, nonce_len & 0xFF, tag_len >> 8, tag_len & 0xFF])
        tag_bytes = self.tag if self.tag else b""
        return header + self.nonce + tag_bytes + self.ciphertext
    
    @classmethod
    def from_bytes(cls, data: bytes) -> "EncryptedData":
        """Deserialize from bytes."""
        version = data[0]
        nonce_len = (data[1] << 8) | data[2]
        tag_len = (data[3] << 8) | data[4]
        offset = 5
        nonce = data[offset:offset + nonce_len]
        offset += nonce_len
        tag = data[offset:offset + tag_len] if tag_len > 0 else None
        offset += tag_len
        ciphertext = data[offset:]
        return cls(
            ciphertext=ciphertext,
            nonce=nonce,
            tag=tag,
            version=version,
        )


@dataclass
class KeyInfo:
    """Information about an encryption key."""
    key_id: str
    created_at: datetime
    expires_at: Optional[datetime] = None
    is_active: bool = True
    algorithm: str = "AES-256"
    usage_count: int = 0
    
    def is_expired(self) -> bool:
        if self.expires_at is None:
            return False
        return datetime.now(timezone.utc) > self.expires_at
    
    def to_dict(self) -> dict:
        return {
            "key_id": self.key_id,
            "created_at": self.created_at.isoformat(),
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "is_active": self.is_active,
            "algorithm": self.algorithm,
            "usage_count": self.usage_count,
        }


class KeyManager:
    """Manages encryption keys with rotation support."""
    
    def __init__(self, key_rotation_days: int = 90):
        self._keys: dict[str, bytes] = {}
        self._key_info: dict[str, KeyInfo] = {}
        self._active_key_id: Optional[str] = None
        self._key_rotation_days = key_rotation_days
    
    def generate_key(self, key_id: Optional[str] = None) -> str:
        """Generate a new AES-256 key (32 bytes)."""
        key_id = key_id or secrets.token_hex(8)
        key = secrets.token_bytes(32)  # 256 bits
        self._keys[key_id] = key
        now = datetime.now(timezone.utc)
        expires = now + timedelta(days=self._key_rotation_days) if self._key_rotation_days > 0 else None
        self._key_info[key_id] = KeyInfo(
            key_id=key_id,
            created_at=now,
            expires_at=expires,
        )
        if self._active_key_id is None:
            self._active_key_id = key_id
        logger.info(f"Generated new encryption key: {key_id}")
        return key_id
    
    def import_key(self, key_id: str, key: bytes) -> None:
        """Import an existing key."""
        if len(key) != 32:
            raise ValueError("AES-256 key must be 32 bytes")
        self._keys[key_id] = key
        now = datetime.now(timezone.utc)
        self._key_info[key_id] = KeyInfo(
            key_id=key_id,
            created_at=now,
        )
        if self._active_key_id is None:
            self._active_key_id = key_id
        logger.info(f"Imported encryption key: {key_id}")
    
    def get_key(self, key_id: str) -> Optional[bytes]:
        """Get a key by ID."""
        return self._keys.get(key_id)
    
    def get_active_key(self) -> Optional[bytes]:
        """Get the currently active key."""
        if self._active_key_id is None:
            return None
        return self._keys.get(self._active_key_id)
    
    def get_active_key_id(self) -> Optional[str]:
        """Get the ID of the active key."""
        return self._active_key_id
    
    def set_active_key(self, key_id: str) -> bool:
        """Set the active key for new encryptions."""
        if key_id not in self._keys:
            return False
        self._active_key_id = key_id
        logger.info(f"Set active encryption key: {key_id}")
        return True
    
    def rotate_key(self) -> str:
        """Generate a new key and set it as active."""
        new_key_id = self.generate_key()
        self.set_active_key(new_key_id)
        return new_key_id
    
    def deactivate_key(self, key_id: str) -> bool:
        """Deactivate a key (it can still decrypt but not encrypt)."""
        if key_id not in self._key_info:
            return False
        self._key_info[key_id].is_active = False
        logger.info(f"Deactivated encryption key: {key_id}")
        return True
    
    def delete_key(self, key_id: str) -> bool:
        """Permanently delete a key."""
        if key_id not in self._keys:
            return False
        del self._keys[key_id]
        del self._key_info[key_id]
        if self._active_key_id == key_id:
            self._active_key_id = None
        logger.warning(f"Deleted encryption key: {key_id}")
        return True
    
    def get_key_info(self, key_id: str) -> Optional[KeyInfo]:
        """Get information about a key."""
        return self._key_info.get(key_id)
    
    def list_keys(self) -> list[KeyInfo]:
        """List all keys."""
        return list(self._key_info.values())
    
    def increment_usage(self, key_id: str) -> None:
        """Increment usage counter for a key."""
        if key_id in self._key_info:
            self._key_info[key_id].usage_count += 1


class AES256Encryptor:
    """AES-256 encryption with GCM mode for authenticated encryption."""
    
    NONCE_SIZE = 12  # 96 bits for GCM
    KEY_SIZE = 32    # 256 bits
    
    def __init__(self, key_manager: Optional[KeyManager] = None, key: Optional[bytes] = None):
        if key_manager:
            self._key_manager = key_manager
        elif key:
            if len(key) != self.KEY_SIZE:
                raise ValueError(f"Key must be {self.KEY_SIZE} bytes for AES-256")
            self._key_manager = KeyManager()
            self._key_manager.import_key("default", key)
        else:
            self._key_manager = KeyManager()
            self._key_manager.generate_key("default")
        
        self._use_cryptography = HAS_CRYPTOGRAPHY
    
    @property
    def key_manager(self) -> KeyManager:
        return self._key_manager
    
    def encrypt(self, plaintext: Union[str, bytes], key_id: Optional[str] = None) -> EncryptedData:
        """Encrypt data using AES-256-GCM."""
        if isinstance(plaintext, str):
            plaintext = plaintext.encode("utf-8")
        
        key_id = key_id or self._key_manager.get_active_key_id()
        key = self._key_manager.get_key(key_id) if key_id else None
        
        if key is None:
            raise ValueError("No encryption key available")
        
        nonce = secrets.token_bytes(self.NONCE_SIZE)
        
        if self._use_cryptography:
            aesgcm = AESGCM(key)
            ciphertext = aesgcm.encrypt(nonce, plaintext, None)
            # GCM appends the tag to ciphertext
            tag = ciphertext[-16:]  # Last 16 bytes are the tag
            ciphertext = ciphertext[:-16]
        else:
            # Fallback: simple XOR-based encryption (NOT SECURE - for testing only)
            import warnings
            warnings.warn("Using insecure fallback encryption")
            key_stream = self._generate_keystream(key, nonce, len(plaintext) + 16)
            ciphertext = bytes(a ^ b for a, b in zip(plaintext, key_stream[:len(plaintext)]))
            tag = key_stream[len(plaintext):len(plaintext) + 16]
        
        self._key_manager.increment_usage(key_id)
        
        return EncryptedData(
            ciphertext=ciphertext,
            nonce=nonce,
            tag=tag,
            key_id=key_id,
        )
    
    def decrypt(self, encrypted: EncryptedData) -> bytes:
        """Decrypt data using AES-256-GCM."""
        key_id = encrypted.key_id or self._key_manager.get_active_key_id()
        key = self._key_manager.get_key(key_id) if key_id else None
        
        if key is None:
            raise ValueError(f"No decryption key available for key_id: {key_id}")
        
        if self._use_cryptography:
            aesgcm = AESGCM(key)
            # GCM expects ciphertext + tag
            ciphertext_with_tag = encrypted.ciphertext + (encrypted.tag or b"")
            plaintext = aesgcm.decrypt(encrypted.nonce, ciphertext_with_tag, None)
        else:
            # Fallback decryption
            key_stream = self._generate_keystream(key, encrypted.nonce, len(encrypted.ciphertext))
            plaintext = bytes(a ^ b for a, b in zip(encrypted.ciphertext, key_stream))
        
        self._key_manager.increment_usage(key_id)
        return plaintext
    
    def decrypt_to_string(self, encrypted: EncryptedData) -> str:
        """Decrypt and decode as UTF-8 string."""
        return self.decrypt(encrypted).decode("utf-8")
    
    def _generate_keystream(self, key: bytes, nonce: bytes, length: int) -> bytes:
        """Generate keystream for fallback encryption."""
        # Simple deterministic expansion (NOT CRYPTOGRAPHICALLY SECURE)
        result = b""
        counter = 0
        while len(result) < length:
            data = nonce + counter.to_bytes(4, "big")
            h = hashlib.sha256(key + data).digest()
            result += h
            counter += 1
        return result[:length]
    
    @staticmethod
    def derive_key(password: str, salt: Optional[bytes] = None, iterations: int = 100000) -> tuple[bytes, bytes]:
        """Derive a key from a password using PBKDF2."""
        salt = salt or os.urandom(16)
        if HAS_CRYPTOGRAPHY:
            kdf = PBKDF2HMAC(
                algorithm=hashes.SHA256(),
                length=32,
                salt=salt,
                iterations=iterations,
                backend=default_backend(),
            )
            key = kdf.derive(password.encode("utf-8"))
        else:
            key = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations, dklen=32)
        return key, salt


# Convenience functions
def encrypt(data: Union[str, bytes], key: Optional[bytes] = None) -> EncryptedData:
    """Encrypt data with AES-256-GCM."""
    encryptor = AES256Encryptor(key=key)
    return encryptor.encrypt(data)


def decrypt(encrypted: EncryptedData, key: Optional[bytes] = None) -> bytes:
    """Decrypt data with AES-256-GCM."""
    encryptor = AES256Encryptor(key=key)
    return encryptor.decrypt(encrypted)
