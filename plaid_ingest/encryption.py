"""
Custom encrypted field using Fernet symmetric encryption.
Derives the encryption key from Django's SECRET_KEY.
"""
import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from django.db import models


def _get_fernet():
    """Derive a Fernet key from Django SECRET_KEY."""
    key_material = settings.SECRET_KEY.encode()
    # Derive a 32-byte key and base64-encode it for Fernet
    derived = hashlib.sha256(key_material).digest()
    fernet_key = base64.urlsafe_b64encode(derived)
    return Fernet(fernet_key)


class EncryptedTextField(models.TextField):
    """
    A TextField that transparently encrypts on save and decrypts on load.
    Stored as base64-encoded Fernet ciphertext in the database.
    """

    description = "Fernet-encrypted text field"

    def get_prep_value(self, value):
        if value is None or value == "":
            return value
        f = _get_fernet()
        return f.encrypt(value.encode()).decode("utf-8")

    def from_db_value(self, value, expression, connection):
        if value is None or value == "":
            return value
        f = _get_fernet()
        try:
            return f.decrypt(value.encode()).decode("utf-8")
        except InvalidToken:
            # If decryption fails (e.g., data was stored unencrypted),
            # return the raw value rather than crashing
            return value

    def value_from_object(self, obj):
        """Return the decrypted value for serialization."""
        return getattr(obj, self.attname)
