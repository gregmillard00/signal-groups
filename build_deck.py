"""Turn labelled clips into playable boards (data/deck.json) and publish the media.

A board is a 3x3 grid: three clusters, three clips each.

Eligibility is decided *per board*, not globally, and that distinction is what makes
the game work. inter1's output on this corpus is dominated by `stress` and
`confidence`, so if a clip had to be globally unambiguous almost everything would be
thrown away and three of the five clusters could never be filled.

But a tile only has to be unambiguous against the groups actually on the board with
it. A clip inter1 tagged [frustration, stress] is a perfectly fair "Frustration &
Disagreement" tile on a board whose other two groups are Confidence and Agreement -
nothing on that board competes for it. The same clip would be unfair on a board that
also contains Skepticism/Stress/Confusion, so it simply isn't offered there.

Concretely: a clip is eligible for group G on a board covering clusters {A,B,C} when
the set of clusters its signals touch intersects {A,B,C} in exactly one cluster, G.

--demo builds a board WITHOUT inter1 labels, for previewing the interface before a
working API key exists. Those boards are flagged provisional everywhere they surface.
"""
import argparse
import itertools
import json
import os
import random
import shutil

from clusters import CLUSTERS, BY_ID, IGNORED_SIGNALS, SIGNAL_TO_CLUSTER
from media import poster
from sources import BY_KEY, credit

HERE = os.path.dirname(os.path.abspath(__file__))
CLIPS = os.path.join(HERE, "clips")
DATA = os.path.join(HERE, "data")
ANALYSIS = os.path.join(DATA, "analysis")
PUBLIC = os.path.join(HERE, "static", "clips")
DECK_PATH = os.path.join(DATA, "deck.json")

PER_GROUP = 3
GROUPS_PER_BOARD = 3


def load_records():
    recs = []
    if not os.path.isdir(ANALYSIS):
        return recs
    for name in sorted(os.listdir(ANALYSIS)):
        if name.endswith(".json"):
            with open(os.path.join(ANALYSIS, name)) as f:
                recs.append(json.load(f))
    return recs


def cluster_set(rec):
    """Which clusters this clip's signals touch at all."""
    if rec.get("label_source") == "placeholder":
        return {rec["cluster"]} if rec.get("cluster") else set()
    out = set()
    for s in (rec.get("result") or {}).get("signals", []):
        t = s.get("type")
        if t in IGNORED_SIGNALS:
            continue
        if t in SIGNAL_TO_CLUSTER:
            out.add(SIGNAL_TO_CLUSTER[t])
    return out


def publish(clip_id):
    """Copy the clip into static/ and make a poster frame for the tile."""
    os.makedirs(PUBLIC, exist_ok=True)
    src = os.path.join(CLIPS, clip_id + ".mp4")
    if not os.path.exists(src):
        return None
    dst = os.path.join(PUBLIC, clip_id + ".mp4")
    if not os.path.exists(dst):
        shutil.copy2(src, dst)
    jpg = os.path.join(PUBLIC, clip_id + ".jpg")
    if not os.path.exists(jpg):
        poster(src, jpg, at=1.5)
    return {"video": f"clips/{clip_id}.mp4", "poster": f"clips/{clip_id}.jpg"}


def clip_payload(rec):
    """Per-tile payload. `signals` are inter1's own words and are only ever
    populated from a real API response."""
    media = publish(rec["clip_id"])
    if not media:
        return None
    src = BY_KEY.get(rec["source"], {})
    sigs = [
        {
            "type": s.get("type"),
            "probability": s.get("probability"),
            "rationale": s.get("rationale"),
            "start": s.get("start"),
            "end": s.get("end"),
            "modality": s.get("modality", []),
        }
        for s in (rec.get("result") or {}).get("signals", [])
    ]
    return {
        "id": rec["clip_id"],
        "video": media["video"],
        "poster": media["poster"],
        "title": rec.get("title") or src.get("title"),
        "year": rec.get("year") or src.get("year"),
        "credit": credit(src) if src else "",
        "at": rec.get("start"),
        "margin": rec.get("margin"),
        "signals": sigs,
        "label_source": rec.get("label_source", "inter1"),
        "_clusters": sorted(cluster_set(rec)),
    }


def eligible_for(payload, triple):
    """The one cluster on this board the clip belongs to, or None if it is
    ambiguous here (touches two of the board's groups) or irrelevant (touches none)."""
    hit = set(payload["_clusters"]) & set(triple)
    return next(iter(hit)) if len(hit) == 1 else None


def build_boards(payloads, max_boards, rng):
    """Fill boards greedily, never reusing a clip, preferring the cluster
    combinations that the corpus supports best so we get the most boards out of it."""
    used = set()
    boards = []
    triples = list(itertools.combinations([c["id"] for c in CLUSTERS], GROUPS_PER_BOARD))

    while len(boards) < max_boards:
        # Score every triple against what is still unused, take the best one.
        options = []
        for triple in triples:
            pools = {t: [] for t in triple}
            for p in payloads:
                if p["id"] in used:
                    continue
                g = eligible_for(p, triple)
                if g:
                    pools[g].append(p)
            if all(len(v) >= PER_GROUP for v in pools.values()):
                options.append((min(len(v) for v in pools.values()), triple, pools))
        if not options:
            break
        # Prefer the tightest viable combination, so scarce clusters get spent
        # while they can still complete a board rather than being stranded.
        options.sort(key=lambda o: o[0])
        _, triple, pools = options[0]

        groups = []
        for cid in triple:
            picked = rng.sample(pools[cid], PER_GROUP)
            for p in picked:
                used.add(p["id"])
            meta = BY_ID[cid]
            groups.append({
                "cluster": cid,
                "name": meta["name"],
                "blurb": meta["blurb"],
                "color": meta["color"],
                "tint": meta["tint"],
                "signals": meta["signals"],
                "clips": [{k: v for k, v in p.items() if k != "_clusters"} for p in picked],
            })

        # Easiest group first: the one whose clips carry the fewest competing signals.
        def noisiness(g):
            return sum(len(c["signals"]) for c in g["clips"])
        groups.sort(key=noisiness)
        for i, g in enumerate(groups):
            g["difficulty"] = i
        boards.append({"id": f"board-{len(boards) + 1}", "groups": groups})

    return boards


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--demo", action="store_true",
                    help="build a preview board with arbitrary (non-inter1) groupings")
    ap.add_argument("--max-boards", type=int, default=20)
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args()

    rng = random.Random(args.seed)
    recs = load_records()
    provisional = False

    if args.demo:
        provisional = True
        from demo_pool import demo_records
        recs = demo_records(rng)
        if not recs:
            raise SystemExit("no clips available for a demo board - run analyze.py --dry-run first")

    payloads = []
    for r in recs:
        if not cluster_set(r):
            continue
        p = clip_payload(r)
        if p:
            payloads.append(p)

    counts = {}
    for p in payloads:
        for c in p["_clusters"]:
            counts[c] = counts.get(c, 0) + 1
    print(f"{len(payloads)} clips carry a signal; per-cluster presence: {counts}")

    boards = build_boards(payloads, args.max_boards, rng)
    used_clusters = sorted({g["cluster"] for b in boards for g in b["groups"]})
    tiles = sum(len(g["clips"]) for b in boards for g in b["groups"])

    deck = {
        "provisional": provisional,
        "notice": (
            "PREVIEW BOARD. These groupings were assigned arbitrarily to demonstrate the "
            "interface, NOT by the inter1 model. No clip here has been analyzed. Replace by "
            "running analyze.py with a working INTERHUMAN_API_KEY, then build_deck.py."
        ) if provisional else None,
        "clusters": CLUSTERS,
        "boards": boards,
        "clip_count": tiles,
    }
    os.makedirs(DATA, exist_ok=True)
    # Write atomically: app.py re-reads deck.json on every request, so a rebuild
    # while someone is playing must never expose a half-written file.
    tmp = DECK_PATH + ".tmp"
    with open(tmp, "w") as f:
        json.dump(deck, f, indent=1)
    os.replace(tmp, DECK_PATH)
    print(f"wrote {DECK_PATH}: {len(boards)} board(s), {tiles} tiles, "
          f"clusters used: {used_clusters}, provisional={provisional}")
    for b in boards:
        print("  " + b["id"] + ": " + ", ".join(g["cluster"] for g in b["groups"]))


if __name__ == "__main__":
    main()
