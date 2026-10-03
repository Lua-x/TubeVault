"""Time-based one-time passwords (RFC 6238) for authenticator apps.

Small enough to keep here instead of adding a dependency: HMAC-SHA1 over the 30-second
time step, dynamically truncated to 6 digits – what Aegis, 2FAS, Google Authenticator,
1Password and friends expect.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import struct
import time
import urllib.parse

PERIOD = 30
DIGITS = 6
WINDOW = 1  # also accept the previous and the next code (clock drift)
ISSUER = "TubeVault"
RECOVERY_ALPHABET = "abcdefghjkmnpqrstuvwxyz23456789"  # no 0/o, 1/l/i


def new_secret() -> str:
    return base64.b32encode(secrets.token_bytes(20)).decode().rstrip("=")


def _key(secret: str) -> bytes:
    cleaned = secret.replace(" ", "").upper()
    return base64.b32decode(cleaned + "=" * (-len(cleaned) % 8))


def code_at(secret: str, counter: int, digits: int = DIGITS) -> str:
    digest = hmac.new(_key(secret), struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    value = struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF
    return str(value % 10**digits).zfill(digits)


def current_counter(now: float | None = None) -> int:
    return int((time.time() if now is None else now) // PERIOD)


def verify(
    secret: str, code: str, *, last_counter: int | None = None, now: float | None = None
) -> int | None:
    """The time step the code belongs to, or None. Each step works only once."""
    code = "".join(ch for ch in code if ch.isdigit())
    if len(code) != DIGITS:
        return None
    counter = current_counter(now)
    for candidate in range(counter - WINDOW, counter + WINDOW + 1):
        if last_counter is not None and candidate <= last_counter:
            continue
        if hmac.compare_digest(code_at(secret, candidate), code):
            return candidate
    return None


def otpauth_uri(secret: str, account: str) -> str:
    label = urllib.parse.quote(f"{ISSUER}:{account}")
    query = urllib.parse.urlencode(
        {"secret": secret, "issuer": ISSUER, "digits": DIGITS, "period": PERIOD}
    )
    return f"otpauth://totp/{label}?{query}"


def new_recovery_codes(count: int = 10) -> list[str]:
    def one() -> str:
        chars = "".join(secrets.choice(RECOVERY_ALPHABET) for _ in range(10))
        return f"{chars[:5]}-{chars[5:]}"

    return [one() for _ in range(count)]


def normalize_recovery_code(code: str) -> str:
    return "".join(ch for ch in code.lower() if ch in RECOVERY_ALPHABET)


def hash_recovery_code(code: str) -> str:
    return hashlib.sha256(normalize_recovery_code(code).encode()).hexdigest()
