"""Sweep every source film for the most promising 10-second windows.

Writes data/candidates.json incrementally (one source at a time) so an interrupted
run never throws away work already paid for in CPU time.
"""
import json
import os
import sys
from concurrent.futures import ProcessPoolExecutor

from prefilter import score_window
from sources import SOURCES

HERE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(HERE, "raw")
DATA = os.path.join(HERE, "data")
CAND_PATH = os.path.join(DATA, "candidates.json")

CLIP_LEN = 10.0
# How often we probe along the film. Overridable because probe cost varies wildly
# by file: seeking into Beat the Devil's 436 MB encode is roughly 8x slower per
# window than the other sources, so it gets a coarser stride rather than an hour.
STRIDE = float(os.environ.get("SWEEP_STRIDE", "25"))
MIN_SEPARATION = 75.0  # keep chosen windows spread out so clips aren't near-duplicates
PER_SOURCE = 40        # how many survivors to keep per film
WORKERS = 4


def _score(job):
    path, start = job
    return score_window(path, start, CLIP_LEN)


def pick_spread(scored, per_source, min_sep):
    """Greedily take the highest-scoring windows subject to a minimum time gap,
    so we get scenes from across the whole film rather than one dense pocket."""
    chosen = []
    for c in sorted(scored, key=lambda c: -c["score"]):
        if c["score"] <= 1.5:
            break
        if all(abs(c["start"] - k["start"]) >= min_sep for k in chosen):
            chosen.append(c)
        if len(chosen) >= per_source:
            break
    return sorted(chosen, key=lambda c: c["start"])


def load_existing():
    if os.path.exists(CAND_PATH):
        with open(CAND_PATH) as f:
            return json.load(f)
    return {}


def main():
    os.makedirs(DATA, exist_ok=True)
    only = sys.argv[1:]
    out = load_existing()

    for src in SOURCES:
        key = src["key"]
        if only and key not in only:
            continue
        path = os.path.join(RAW, f"{key}.mp4")
        if not os.path.exists(path):
            print(f"[{key}] raw file missing, skipping", flush=True)
            continue
        if key in out:
            print(f"[{key}] already swept ({len(out[key])} candidates), skipping", flush=True)
            continue

        lo, hi = src["sample_from"]
        hi = min(hi, src["duration"] - CLIP_LEN - 5)
        starts = [lo + i * STRIDE for i in range(int((hi - lo) / STRIDE) + 1)]
        print(f"[{key}] probing {len(starts)} windows ...", flush=True)

        with ProcessPoolExecutor(max_workers=WORKERS) as ex:
            scored = list(ex.map(_score, [(path, s) for s in starts], chunksize=4))
        scored = [c for c in scored if "error" not in c]

        picked = pick_spread(scored, PER_SOURCE, MIN_SEPARATION)
        for c in picked:
            c["source"] = key
        out[key] = picked
        with open(CAND_PATH, "w") as f:
            json.dump(out, f, indent=1)
        # picked is ordered by timestamp, so take the max explicitly rather than [0]
        top = max((c["score"] for c in picked), default=0)
        print(f"[{key}] kept {len(picked)} of {len(scored)} (best score {top})", flush=True)

    total = sum(len(v) for v in out.values())
    print(f"total candidates: {total}", flush=True)


if __name__ == "__main__":
    main()
