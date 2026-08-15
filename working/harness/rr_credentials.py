"""RocketRide client credentials — resolved once, for every driver in the process.

WHY THIS IS NOT LEFT TO THE SDK
-------------------------------
Every driver here builds its client bare — `RocketRideClient()` — and lets the SDK resolve the
endpoint and key (`engine/rocketride/client.py:200-205`): explicit argument, else `os.environ`,
else a **`.env` in the current working directory**, else a built-in default.

`.env` is gitignored (`.gitignore:62`). That single fact is why every RocketRide arm worked on the
laptop and failed on a fresh clone with `AuthenticationException: No authorization provided`.

Two failure modes this module closes, both of which have already cost a run:

1. **Auth is an exact match, not a presence check.** The engine in OSS mode compares the presented
   credential against the SERVER's own `ROCKETRIDE_APIKEY`
   (`engine/ai/account/oss/__init__.py:92-99`)::

       oss_key = os.environ.get('ROCKETRIDE_APIKEY', '')
       if oss_key and oss_key != credential:
           return (401, 'Invalid API key')

   Both engine images set `local-dev` (ours `docker/Dockerfile.rocketride:59`, Leela's compose);
   `working/scripts/start_engine.sh` uses `MYAPIKEY` for the native path. Only an *empty*
   server-side key disables the check, and no image we run does that.

2. **An unset endpoint does not fail — it goes to the internet.** With `ROCKETRIDE_URI` unset the
   SDK falls back to `CONST_DEFAULT_WEB_CLOUD`, so a misconfigured driver silently measures the
   hosted service instead of the container under test. `strict=True` refuses anything non-loopback.

`harness/__init__.py` calls this with `strict=False` on import, so any script that imports the
harness inherits working credentials without exporting anything by hand. The measured drivers call
it again with `strict=True`, where a remote endpoint must be fatal rather than merely odd.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent

DEFAULTS = {
    "ROCKETRIDE_URI": "http://127.0.0.1:5565",
    # Matches BOTH engine images. The native path (start_engine.sh) uses MYAPIKEY instead, so a
    # native run must export it or keep a .env — the default cannot satisfy both.
    "ROCKETRIDE_APIKEY": "local-dev",
}
LOOPBACK = ("127.0.0.1", "localhost", "::1")

# Provenance is recorded on the FIRST resolution and reused afterwards. Without this, the second
# call reports "process environment" for everything — true, but only because the first call put it
# there — and the manifest would lose the one fact worth recording: whether the credential came
# from a real environment variable, a gitignored .env, or the built-in default.
_FIRST: dict = {}


def _from_dotenv(key: str) -> str | None:
    """Read one key from the repo-root .env, the same file the SDK reads from the CWD."""
    p = ROOT / ".env"
    if not p.exists():
        return None
    for line in p.read_text().splitlines():
        if line.startswith(f"{key}="):
            return line.split("=", 1)[1].strip() or None
    return None


def resolve(strict: bool = False) -> dict:
    """Resolve endpoint + key into os.environ and describe where each came from.

    Idempotent: an already-set environment variable always wins, so calling this from
    `harness/__init__.py` and again from a driver cannot change the answer.

    Returns a manifest-ready dict. The key's VALUE is never included — only a `sha256[:8]`
    fingerprint, which is enough to prove two sites used the same credential without writing a
    secret into a result file that gets uploaded to S3.
    """
    out: dict = {}
    for key, default in DEFAULTS.items():
        if key in _FIRST:
            val, src = os.environ.get(key, _FIRST[key][0]), _FIRST[key][1]
        else:
            dotenv_val = _from_dotenv(key)
            if os.environ.get(key):
                val, src = os.environ[key], "process environment"
            elif dotenv_val:
                val, src = dotenv_val, f"{ROOT}/.env (gitignored — absent on a fresh clone)"
            else:
                val, src = default, "harness default (matches both engine images)"
            _FIRST[key] = (val, src)
        os.environ[key] = val          # every bare RocketRideClient() in this process sees it
        out[key] = {"source": src}
        if key.endswith("URI"):
            out[key]["value"] = val
        else:
            out[key]["sha256_8"] = hashlib.sha256(val.encode()).hexdigest()[:8]

    uri = os.environ["ROCKETRIDE_URI"]
    out["loopback"] = any(h in uri for h in LOOPBACK)
    if strict and not out["loopback"]:
        raise RuntimeError(
            f"ROCKETRIDE_URI resolved to {uri!r}, which is not loopback. Refusing: the SDK's "
            "fallback when the variable is unset is the hosted cloud service, and a benchmark "
            "that silently measures a remote endpoint is worse than one that fails.")
    return out


def auth_hint() -> str:
    """Appended to auth failures so the message names the mismatch instead of restating it."""
    fp = hashlib.sha256(os.environ.get("ROCKETRIDE_APIKEY", "").encode()).hexdigest()[:8]
    return (f"The engine compares the credential against ITS OWN ROCKETRIDE_APIKEY and rejects a "
            f"mismatch with 401 'Invalid API key'. Driver used sha256[:8]={fp}. Compare with "
            f"`docker exec <rr container> printenv ROCKETRIDE_APIKEY`.")
