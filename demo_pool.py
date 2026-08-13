"""Preview-only clip pool, used by `build_deck.py --demo`.

This exists so the interface can be reviewed before a working inter1 API key is
available. It assigns clips to clusters by round-robin over the candidate list -
an arbitrary ordering that carries no information about what the clips contain.

It is deliberately NOT a heuristic or a guess at the real labels. Nothing here
should ever be presented as a model output; every record is stamped
label_source="placeholder" and margin=None so it is distinguishable downstream,
and build_deck.py marks the whole deck provisional.
"""
import json
import os

from clusters import CLUSTERS
from sources import BY_KEY

HERE = os.path.dirname(os.path.abspath(__file__))
CLIPS = os.path.join(HERE, "clips")
CAND_PATH = os.path.join(HERE, "data", "candidates.json")

PER_CLUSTER = 3


def demo_records(rng):
    """Build placeholder records from whatever clips have already been cut to disk."""
    if not os.path.exists(CAND_PATH):
        return []
    with open(CAND_PATH) as f:
        by_source = json.load(f)

    cut = set()
    if os.path.isdir(CLIPS):
        cut = {n[:-4] for n in os.listdir(CLIPS) if n.endswith(".mp4")}

    cands = []
    for key in sorted(by_source):
        for c in sorted(by_source[key], key=lambda c: -c["score"]):
            cid = f"{key}_{int(c['start'])}"
            if cid in cut:
                cands.append((cid, key, c))

    rng.shuffle(cands)
    need = len(CLUSTERS) * PER_CLUSTER
    cands = cands[:need]

    recs = []
    for i, (cid, key, c) in enumerate(cands):
        src = BY_KEY[key]
        recs.append({
            "clip_id": cid,
            "source": key,
            "title": src["title"],
            "year": src["year"],
            "start": c["start"],
            "duration": 10.0,
            # Round-robin, i.e. meaningless on purpose.
            "cluster": CLUSTERS[i % len(CLUSTERS)]["id"],
            "margin": None,
            "label_source": "placeholder",
            "result": {"signals": []},
        })
    return recs
