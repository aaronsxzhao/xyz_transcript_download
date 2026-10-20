"""Password strength and anonymous compromised-password range checks."""
import hashlib
import httpx
from fastapi import HTTPException


def validate_new_password(password: str):
    if len(password) < 8 or len(password) > 1024:
        raise HTTPException(status_code=400, detail='Choose a password with 8–1024 characters.')
    digest = hashlib.sha1(password.encode()).hexdigest().upper()
    # Only the first five hash characters leave the application. Neither the
    # password nor the complete digest is sent to the range service or logged.
    try:
        response = httpx.get('https://api.pwnedpasswords.com/range/' + digest[:5],
                             headers={'Add-Padding': 'true'}, timeout=5)
        response.raise_for_status()
        for line in response.text.splitlines():
            suffix, _, count = line.partition(':')
            if suffix == digest[5:] and count.strip().isdigit() and int(count.strip()) > 0:
                raise HTTPException(status_code=400, detail='This password appears in known data breaches. Choose a different password.')
    except httpx.HTTPError:
        raise HTTPException(status_code=503, detail='Password safety check is temporarily unavailable. Please retry.')
