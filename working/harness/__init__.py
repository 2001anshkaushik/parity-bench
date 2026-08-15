"""Measurement harness.

Importing this package resolves RocketRide client credentials into `os.environ` as a side effect.
That is deliberate: every driver in this repo builds its client bare, the SDK then falls back to a
`.env` that is gitignored, and a fresh clone therefore fails with
`AuthenticationException: No authorization provided` — which is an auth failure that reads like a
measurement failure. Doing it here means any script that imports the harness inherits working
credentials without exporting anything by hand.

`strict=False`: this must never raise at import time. The measured drivers call
`rr_credentials.resolve(strict=True)` themselves, where a non-loopback endpoint has to be fatal.
"""
from . import rr_credentials as _rr_credentials

_rr_credentials.resolve(strict=False)
