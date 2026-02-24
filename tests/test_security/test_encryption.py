"""Tests for AES-256 Encryption."""

import os
from datetime import UTC, datetime, timedelta

import pytest
from src.security.encryption.aes256 import (
    AES256Encryptor,
    EncryptedData,
    KeyInfo,
)


class TestEncryptedData:
    """Tests for EncryptedData dataclass."""

    def test_encrypted_data_creation(self):
        """Test creating encrypted data."""
        data = EncryptedData(
            ciphertext=b"encrypted",
            nonce=b"nonce1234567",
            tag=b"tag1234567890123",
        )
        assert data.ciphertext == b"encrypted"
        assert data.nonce == b"nonce1234567"
        assert data.version == 1

    def test_encrypted_data_to_dict(self):
        """Test serializing to dict."""
        data = EncryptedData(
            ciphertext=b"test",
            nonce=b"nonce",
            tag=b"tag",
            key_id="key-1",
        )
        d = data.to_dict()
        assert "ciphertext" in d
        assert "nonce" in d
        assert "algorithm" in d
        assert d["key_id"] == "key-1"

    def test_encrypted_data_to_bytes_roundtrip(self):
        """Test serialization to bytes and back."""
        original = EncryptedData(
            ciphertext=b"encrypted content here",
            nonce=b"nonce12345",
            tag=b"tag1234567890123",
            version=1,
        )
        serialized = original.to_bytes()
        recovered = EncryptedData.from_bytes(serialized)

        assert recovered.ciphertext == original.ciphertext
        assert recovered.nonce == original.nonce
        assert recovered.tag == original.tag
        assert recovered.version == original.version


class TestKeyInfo:
    """Tests for KeyInfo dataclass."""

    def test_key_info_creation(self):
        """Test creating key info."""
        info = KeyInfo(
            key_id="test-key",
            created_at=datetime.now(UTC),
        )
        assert info.key_id == "test-key"
        assert info.is_active is True
        assert info.usage_count == 0

    def test_key_info_expiry(self):
        """Test key expiry checking."""
        # Not expired
        info = KeyInfo(
            key_id="test",
            created_at=datetime.now(UTC),
            expires_at=datetime.now(UTC) + timedelta(days=30),
        )
        assert info.is_expired() is False

        # Expired
        expired_info = KeyInfo(
            key_id="expired",
            created_at=datetime.now(UTC) - timedelta(days=100),
            expires_at=datetime.now(UTC) - timedelta(days=1),
        )
        assert expired_info.is_expired() is True

    def test_key_info_no_expiry(self):
        """Test key with no expiry date."""
        info = KeyInfo(
            key_id="no-expiry",
            created_at=datetime.now(UTC),
            expires_at=None,
        )
        assert info.is_expired() is False


class TestKeyManager:
    """Tests for KeyManager class."""

    def test_initial_state(self, key_manager):
        """Test initial key manager state."""
        assert key_manager.get_active_key_id() is None
        assert len(key_manager.list_keys()) == 0

    def test_generate_key(self, key_manager):
        """Test generating a new key."""
        key_id = key_manager.generate_key()
        assert key_id is not None
        assert key_manager.get_key(key_id) is not None
        assert key_manager.get_active_key_id() == key_id

    def test_generate_key_with_id(self, key_manager):
        """Test generating a key with specific ID."""
        key_id = key_manager.generate_key("my-custom-key")
        assert key_id == "my-custom-key"
        assert key_manager.get_key("my-custom-key") is not None

    def test_import_key(self, key_manager, sample_key):
        """Test importing an existing key."""
        key_manager.import_key("imported-key", sample_key)
        assert key_manager.get_key("imported-key") == sample_key

    def test_import_invalid_key(self, key_manager):
        """Test importing an invalid key raises error."""
        with pytest.raises(ValueError):
            key_manager.import_key("bad-key", b"too short")

    def test_get_active_key(self, key_manager):
        """Test getting the active key."""
        key_manager.generate_key("active")
        key = key_manager.get_active_key()
        assert key is not None
        assert len(key) == 32

    def test_set_active_key(self, key_manager):
        """Test setting the active key."""
        key_manager.generate_key("key1")
        key_manager.generate_key("key2")

        key_manager.set_active_key("key1")
        assert key_manager.get_active_key_id() == "key1"

    def test_set_active_nonexistent_key(self, key_manager):
        """Test setting non-existent key as active."""
        result = key_manager.set_active_key("nonexistent")
        assert result is False

    def test_rotate_key(self, key_manager):
        """Test key rotation."""
        old_id = key_manager.generate_key()
        new_id = key_manager.rotate_key()

        assert new_id != old_id
        assert key_manager.get_active_key_id() == new_id

    def test_deactivate_key(self, key_manager):
        """Test deactivating a key."""
        key_id = key_manager.generate_key()
        result = key_manager.deactivate_key(key_id)

        assert result is True
        info = key_manager.get_key_info(key_id)
        assert info.is_active is False

    def test_delete_key(self, key_manager):
        """Test deleting a key."""
        key_id = key_manager.generate_key()
        result = key_manager.delete_key(key_id)

        assert result is True
        assert key_manager.get_key(key_id) is None

    def test_delete_nonexistent_key(self, key_manager):
        """Test deleting non-existent key."""
        result = key_manager.delete_key("nonexistent")
        assert result is False

    def test_list_keys(self, key_manager):
        """Test listing all keys."""
        key_manager.generate_key("key1")
        key_manager.generate_key("key2")

        keys = key_manager.list_keys()
        assert len(keys) == 2
        key_ids = [k.key_id for k in keys]
        assert "key1" in key_ids
        assert "key2" in key_ids

    def test_increment_usage(self, key_manager):
        """Test incrementing usage counter."""
        key_id = key_manager.generate_key()
        key_manager.increment_usage(key_id)
        key_manager.increment_usage(key_id)

        info = key_manager.get_key_info(key_id)
        assert info.usage_count == 2


class TestAES256Encryptor:
    """Tests for AES256Encryptor class."""

    def test_encrypt_decrypt_bytes(self, encryptor, sample_plaintext):
        """Test encrypting and decrypting bytes."""
        encrypted = encryptor.encrypt(sample_plaintext)
        decrypted = encryptor.decrypt(encrypted)

        assert decrypted == sample_plaintext

    def test_encrypt_decrypt_string(self, encryptor):
        """Test encrypting and decrypting string."""
        original = "Hello, secure world!"
        encrypted = encryptor.encrypt(original)
        decrypted = encryptor.decrypt_to_string(encrypted)

        assert decrypted == original

    def test_encrypt_produces_different_ciphertext(self, encryptor, sample_plaintext):
        """Test that encryption produces different ciphertext each time."""
        encrypted1 = encryptor.encrypt(sample_plaintext)
        encrypted2 = encryptor.encrypt(sample_plaintext)

        # Different nonces = different ciphertext
        assert encrypted1.ciphertext != encrypted2.ciphertext
        assert encrypted1.nonce != encrypted2.nonce

    def test_encrypt_with_custom_key(self, sample_key, sample_plaintext):
        """Test encryption with custom key."""
        encryptor = AES256Encryptor(key=sample_key)
        encrypted = encryptor.encrypt(sample_plaintext)
        decrypted = encryptor.decrypt(encrypted)

        assert decrypted == sample_plaintext

    def test_encrypt_with_key_manager(self, key_manager, sample_plaintext):
        """Test encryption with key manager."""
        key_manager.generate_key("test-key")
        encryptor = AES256Encryptor(key_manager=key_manager)

        encrypted = encryptor.encrypt(sample_plaintext)
        decrypted = encryptor.decrypt(encrypted)

        assert decrypted == sample_plaintext

    def test_encrypt_with_specific_key_id(self, key_manager, sample_plaintext):
        """Test encryption with specific key ID."""
        key_manager.generate_key("key1")
        key_manager.generate_key("key2")

        encryptor = AES256Encryptor(key_manager=key_manager)
        encrypted = encryptor.encrypt(sample_plaintext, key_id="key2")

        assert encrypted.key_id == "key2"
        decrypted = encryptor.decrypt(encrypted)
        assert decrypted == sample_plaintext

    def test_decrypt_with_wrong_key_fails(self, sample_plaintext):
        """Test that decryption with wrong key fails."""
        encryptor1 = AES256Encryptor(key=os.urandom(32))
        encryptor2 = AES256Encryptor(key=os.urandom(32))

        encrypted = encryptor1.encrypt(sample_plaintext)

        with pytest.raises(Exception):  # Should raise decryption error
            encryptor2.decrypt(encrypted)

    def test_empty_plaintext(self, encryptor):
        """Test encrypting empty data."""
        encrypted = encryptor.encrypt(b"")
        decrypted = encryptor.decrypt(encrypted)
        assert decrypted == b""

    def test_large_plaintext(self, encryptor):
        """Test encrypting large data."""
        large_data = os.urandom(1024 * 1024)  # 1MB
        encrypted = encryptor.encrypt(large_data)
        decrypted = encryptor.decrypt(encrypted)
        assert decrypted == large_data

    def test_encrypted_data_properties(self, encryptor, sample_plaintext):
        """Test encrypted data has expected properties."""
        encrypted = encryptor.encrypt(sample_plaintext)

        assert encrypted.algorithm == "AES-256-GCM"
        assert encrypted.version == 1
        assert encrypted.key_id is not None
        assert encrypted.timestamp is not None

    def test_key_manager_property(self, encryptor):
        """Test accessing key manager."""
        km = encryptor.key_manager
        assert km is not None


class TestKeyDerivation:
    """Tests for key derivation from password."""

    def test_derive_key(self):
        """Test deriving key from password."""
        key, salt = AES256Encryptor.derive_key("my-password")

        assert len(key) == 32
        assert len(salt) == 16

    def test_derive_key_with_salt(self):
        """Test deriving key with specific salt."""
        salt = os.urandom(16)
        key1, _ = AES256Encryptor.derive_key("password", salt=salt)
        key2, _ = AES256Encryptor.derive_key("password", salt=salt)

        assert key1 == key2

    def test_different_passwords_different_keys(self):
        """Test different passwords produce different keys."""
        key1, _ = AES256Encryptor.derive_key("password1")
        key2, _ = AES256Encryptor.derive_key("password2")

        assert key1 != key2

    def test_derived_key_usable(self):
        """Test derived key can be used for encryption."""
        key, salt = AES256Encryptor.derive_key("test-password")
        encryptor = AES256Encryptor(key=key)

        plaintext = b"Secret message"
        encrypted = encryptor.encrypt(plaintext)
        decrypted = encryptor.decrypt(encrypted)

        assert decrypted == plaintext


class TestConvenienceFunctions:
    """Tests for convenience encryption functions."""

    def test_encrypt_decrypt_functions_with_key(self):
        """Test convenience encrypt/decrypt functions with provided key."""
        from src.security.encryption.aes256 import decrypt, encrypt

        key = os.urandom(32)
        plaintext = b"Test message"
        encrypted = encrypt(plaintext, key=key)
        decrypted = decrypt(encrypted, key=key)

        assert decrypted == plaintext

    def test_encrypt_with_custom_key(self):
        """Test convenience function with custom key."""
        from src.security.encryption.aes256 import decrypt, encrypt

        key = os.urandom(32)
        plaintext = b"Test message"

        encrypted = encrypt(plaintext, key=key)
        decrypted = decrypt(encrypted, key=key)

        assert decrypted == plaintext
