"""Fail closed. Never decrypt legacy plaintext as a fallback."""
import json
from datetime import datetime, timezone
from cryptography.fernet import Fernet, InvalidToken
from app.core.config import get_settings

def cipher():
    key=get_settings().FERNET_KEY
    if not key: raise ValueError('credential_encryption_not_configured')
    return Fernet(key.encode())

def encrypt(data): return 'v1:'+cipher().encrypt(json.dumps(data).encode()).decode()

def decrypt(value):
    if not value.startswith('v1:'): raise ValueError('legacy_plaintext_requires_migration')
    try: data=json.loads(cipher().decrypt(value[3:].encode()))
    except (InvalidToken,ValueError) as exc: raise ValueError('credential_decryption_failed') from exc
    if data.get('expires_at') and datetime.fromisoformat(data['expires_at'])<=datetime.now(timezone.utc):
        raise ValueError('credentials_expired')
    return data
