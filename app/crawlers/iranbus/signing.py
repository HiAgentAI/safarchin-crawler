"""
Request signing for the iranbus.ir JSON API.

Every call to ``https://iranbus.ir/api/...`` must carry two headers:

``site-key``
    A constant published in the site's own page configuration.

``token``
    ``<nonce>.<hash>``, where the hash digests the request path, a second
    public constant and the nonce. Both constants ship inside the site's
    ``window.__NUXT__.config`` object, so a client can produce a valid token
    without a server round trip and without any private credential.

The digest is a djb2-style pair of rolling 32-bit hashes over the ASCII bytes
of ``path + secret + nonce``. The two hex strings are concatenated and then
given a mixed-case transform before being right-padded to a fixed width.
"""

import random
import string
from typing import Dict

# Both values are read from the provider's public Nuxt runtime configuration
# (window.__NUXT__.config.public). They identify the client application; they
# are not a private credential and must be replaceable in one place if the
# provider ever rotates them.
SITE_KEY = "I/MxctuG4578Buls"
SECRET_KEY = "DC9B78BE2444CDA2E7BE8CC494DED"

_NONCE_ALPHABET = string.ascii_letters + string.digits
_NONCE_LENGTH = 64
_HASH_WIDTH = 32
_MASK_32 = 0xFFFFFFFF


def _nonce(length: int = _NONCE_LENGTH) -> str:
    """Produce a random alphanumeric nonce."""
    return "".join(random.choice(_NONCE_ALPHABET) for _ in range(length))


def _digest_hex(path: str, nonce: str) -> str:
    """Digest ``path + SECRET_KEY + nonce`` into the provider's hex form."""
    material = f"{path}{SECRET_KEY}{nonce}".encode("utf-8")

    rolling_a = 5381
    rolling_b = 52711
    for byte in material:
        value = byte
        rolling_a = (((rolling_a << 5) + rolling_a + value) & _MASK_32)
        rolling_b = (((rolling_b * 31) ^ value) & _MASK_32)

    digest = format(rolling_a, "x") + format(rolling_b, "x")

    # Mixed-case transform: every third character is upper-cased, otherwise
    # every second character is lower-cased and the rest are left alone.
    return "".join(
        char.upper() if index % 3 == 0 else (char.lower() if index % 2 == 0 else char)
        for index, char in enumerate(digest)
    )


def make_token(path: str) -> str:
    """
    Build a request token for an API path.

    ``path`` must be the full path the token covers - the provider signs
    ``/api/<endpoint>``, not a bare endpoint name.
    """
    nonce = _nonce()
    return f"{nonce}.{_digest_hex(path, nonce).ljust(_HASH_WIDTH, 'X')}"


def auth_headers(path: str) -> Dict[str, str]:
    """Build the headers every iranbus.ir API request needs."""
    return {"site-key": SITE_KEY, "token": make_token(path)}