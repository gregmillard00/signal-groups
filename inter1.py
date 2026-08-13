"""Client for the Interhuman AI inter1 Signals API.

One endpoint matters here: POST https://api.interhuman.ai/v1/upload/analyze, a
multipart upload of a video file, authenticated with `Authorization: Bearer <key>`.
It returns detected social signals with start/end times, a probability band
(high/medium/low), and a rationale grounded in observable behaviour.

Constraints from the API reference that shape how we call it:
  - video must be >= 3 seconds, upload <= 32 MB (our clips are ~1 MB)
  - accepted containers: mp4, avi, mov, mkv, mpeg-ts, webm
  - max 5 concurrent requests per account (ih3002)
  - rate limit ih3001 and quota ih3003 both surface as HTTP 429
"""
import os
import time

import requests

BASE = "https://api.interhuman.ai"
ANALYZE = f"{BASE}/v1/upload/analyze"

# Errors where retrying the identical request cannot help.
FATAL_ERROR_IDS = {
    "ih2001",  # invalid credentials
    "ih2002",  # missing credentials
    "ih2003",  # insufficient scope
    "ih3003",  # account quota exhausted - stop the whole run, do not burn more
    "ih4003",  # payload too large
    "ih4007",  # video too short
    "ih5001", "ih5002", "ih5003", "ih5004", "ih5005", "ih5006", "ih5007",
}

QUOTA_ERROR_ID = "ih3003"


class Inter1Error(Exception):
    def __init__(self, message, error_id=None, status=None, fatal=False):
        super().__init__(message)
        self.error_id = error_id
        self.status = status
        self.fatal = fatal

    @property
    def is_quota(self):
        return self.error_id == QUOTA_ERROR_ID


def api_key():
    key = os.environ.get("INTERHUMAN_API_KEY", "").strip()
    if not key:
        raise Inter1Error("INTERHUMAN_API_KEY is not set", fatal=True)
    return key


def analyze_file(path, key=None, timeout=300, max_attempts=3):
    """Analyze one video file. Returns the parsed AnalysisResult dict.

    Retries only on transient failures (network, 5xx, rate limit). Anything in
    FATAL_ERROR_IDS raises immediately so we never re-spend on a request that
    cannot succeed.
    """
    key = key or api_key()
    size = os.path.getsize(path)
    if size > 32 * 1024 * 1024:
        raise Inter1Error(f"{path} is {size/1e6:.1f} MB, over the 32 MB cap", fatal=True)

    last = None
    for attempt in range(1, max_attempts + 1):
        try:
            with open(path, "rb") as fh:
                resp = requests.post(
                    ANALYZE,
                    headers={"Authorization": f"Bearer {key}"},
                    files={"file": (os.path.basename(path), fh, "video/mp4")},
                    timeout=timeout,
                )
        except requests.RequestException as e:
            last = Inter1Error(f"network error: {e}")
            if attempt < max_attempts:
                time.sleep(4 * attempt)
                continue
            raise last

        if resp.status_code == 200:
            return resp.json()

        try:
            body = resp.json()
        except ValueError:
            body = {}
        eid = body.get("error_id")
        msg = body.get("message") or resp.text[:300]
        err = Inter1Error(
            f"HTTP {resp.status_code} {eid or ''}: {msg}",
            error_id=eid,
            status=resp.status_code,
            fatal=eid in FATAL_ERROR_IDS,
        )
        if err.fatal:
            raise err

        last = err
        if attempt < max_attempts:
            # 429 without a quota code means slow down; 5xx means try again shortly.
            time.sleep(30 if resp.status_code == 429 else 5 * attempt)
            continue
        raise err

    raise last
