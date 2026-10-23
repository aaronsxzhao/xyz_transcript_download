"""Account-bound encryption for user-supplied model credentials."""
import base64
import hashlib
import hmac
import os
import secrets
import tempfile
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken
from config import DATA_DIR, SUPABASE_SERVICE_KEY


def _cipher(owner: str, field: str) -> Fernet:
    seed = os.getenv("MODEL_CREDENTIAL_KEY") or SUPABASE_SERVICE_KEY
    if seed:
        secret = seed.encode()
    else:
        path = Path(DATA_DIR) / ".model-credential-key"
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            secret = path.read_bytes()
        except FileNotFoundError:
            # Publish a complete seed atomically; concurrent first saves must
            # never derive a cipher from another request's half-written file.
            with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as output:
                temporary = Path(output.name)
                output.write(secrets.token_bytes(32))
            try:
                try:
                    os.link(temporary, path)
                except FileExistsError:
                    pass
                secret = path.read_bytes()
            finally:
                temporary.unlink(missing_ok=True)
    key = hmac.new(secret, f"xyz-model-key-v1:{owner}:{field}".encode(), hashlib.sha256).digest()
    return Fernet(base64.urlsafe_b64encode(key))


def encrypt_key(owner: str, field: str, value: str) -> str:
    return _cipher(owner, field).encrypt(value.encode()).decode() if value else ""


def decrypt_key(owner: str, field: str, value: str) -> str:
    try:
        return _cipher(owner, field).decrypt(value.encode()).decode() if value else ""
    except (InvalidToken, AttributeError, TypeError):
        raise ValueError("Saved model key cannot be opened. Re-enter the key in Settings.") from None
