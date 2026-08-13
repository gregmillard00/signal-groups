"""Cut candidate clips and label them with inter1.

Cost discipline (the ticket says the API is expensive, so this matters):
  - Candidates are pre-filtered locally first (see prefilter.py); we only ever
    upload windows that already have a visible face and audible speech.
  - Every response is written to data/analysis/<clip_id>.json the moment it
    arrives. A crash, a killed process, or an exhausted quota mid-run therefore
    costs at most one in-flight call - everything already paid for is on disk and
    a re-run skips it.
  - The run stops as soon as every cluster has TARGET_PER_CLUSTER usable clips,
    rather than grinding through the whole candidate list.
  - A quota error (ih3003) aborts immediately instead of hammering the endpoint.

Usage:
    python analyze.py            # run until targets met or MAX_CALLS reached
    python analyze.py --max 12   # small pilot batch
    python analyze.py --dry-run  # cut clips + show the plan, spend nothing
"""
import argparse
import json
import os
import sys

from clusters import CLUSTERS, IGNORED_SIGNALS, PROBABILITY_WEIGHT, SIGNAL_TO_CLUSTER
from inter1 import Inter1Error, analyze_file, api_key
from media import cut_clip
from sources import BY_KEY

HERE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(HERE, "raw")
CLIPS = os.path.join(HERE, "clips")
DATA = os.path.join(HERE, "data")
ANALYSIS = os.path.join(DATA, "analysis")
CAND_PATH = os.path.join(DATA, "candidates.json")

CLIP_LEN = 10.0
TARGET_PER_CLUSTER = 6
MAX_CALLS = 120
DOMINANCE = 1.5  # top cluster must beat the runner-up by this factor to be usable


def clip_id(cand):
    return f"{cand['source']}_{int(cand['start'])}"


def clip_path(cand):
    return os.path.join(CLIPS, clip_id(cand) + ".mp4")


def result_path(cid):
    return os.path.join(ANALYSIS, cid + ".json")


def cluster_scores(result):
    """Weight each detected signal by its probability band and how long it persists,
    then total per cluster. Longer, higher-confidence signals dominate."""
    scores = {c["id"]: 0.0 for c in CLUSTERS}
    for sig in result.get("signals", []):
        stype = sig.get("type")
        if stype in IGNORED_SIGNALS:
            continue
        cid = SIGNAL_TO_CLUSTER.get(stype)
        if not cid:
            continue
        span = max(0.0, float(sig.get("end", 0)) - float(sig.get("start", 0)))
        # A signal that barely registers still counts, but not much.
        duration_factor = 0.5 + min(span / CLIP_LEN, 1.0)
        scores[cid] += PROBABILITY_WEIGHT.get(sig.get("probability")) * duration_factor
    return scores


def classify(result):
    """Return (cluster_id, confidence_margin) or (None, margin) if too ambiguous.

    A Connections tile has to belong to exactly one group, so a clip where two
    clusters are neck and neck is unusable no matter how interesting it is.
    """
    scores = cluster_scores(result)
    ranked = sorted(scores.items(), key=lambda kv: -kv[1])
    top, top_score = ranked[0]
    runner_up = ranked[1][1] if len(ranked) > 1 else 0.0
    if top_score <= 0:
        return None, 0.0
    margin = top_score / runner_up if runner_up > 0 else float("inf")
    if margin < DOMINANCE:
        return None, margin
    return top, margin


def load_candidates():
    if not os.path.exists(CAND_PATH):
        sys.exit("no data/candidates.json - run sweep.py first")
    with open(CAND_PATH) as f:
        by_source = json.load(f)
    return by_source


def ordered_candidates(by_source, min_face=0.0):
    """Interleave sources, best-first within each, so an early stop still yields
    clips drawn from every film rather than nine tiles from one movie.

    Ordered by face_size (how much of the frame the largest face fills) rather than
    the composite prefilter score. Measured over the first 75 calls, close framing is
    by far the strongest predictor of getting any signal back at all:
    face_size >= 0.35 returned signals 80% of the time versus 37% below it. Since a
    response with no signals is a wasted call, sorting closeups to the front roughly
    doubles usable clips per credit.
    """
    ranked = {
        k: sorted([c for c in v if c.get("face_size", 0) >= min_face],
                  key=lambda c: -c.get("face_size", 0))
        for k, v in by_source.items()
    }
    out, i = [], 0
    while any(len(v) > i for v in ranked.values()):
        for k in sorted(ranked):
            if len(ranked[k]) > i:
                out.append(ranked[k][i])
        i += 1
    return out


def existing_tallies():
    tallies = {c["id"]: 0 for c in CLUSTERS}
    done = {}
    if not os.path.isdir(ANALYSIS):
        return tallies, done
    for name in os.listdir(ANALYSIS):
        if not name.endswith(".json"):
            continue
        with open(os.path.join(ANALYSIS, name)) as f:
            rec = json.load(f)
        done[rec["clip_id"]] = rec
        if rec.get("cluster"):
            tallies[rec["cluster"]] += 1
    return tallies, done


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max", type=int, default=MAX_CALLS, help="hard cap on API calls this run")
    ap.add_argument("--target", type=int, default=TARGET_PER_CLUSTER)
    ap.add_argument("--dry-run", action="store_true", help="cut clips, make no API calls")
    ap.add_argument("--min-face", type=float, default=0.0,
                    help="skip candidates whose largest face fills less than this "
                         "fraction of frame height (0.35 is the efficiency knee)")
    ap.add_argument("--only-clusters", default="",
                    help="comma-separated cluster ids; stop counting others toward the target")
    args = ap.parse_args()

    os.makedirs(CLIPS, exist_ok=True)
    os.makedirs(ANALYSIS, exist_ok=True)

    key = None
    if not args.dry_run:
        try:
            key = api_key()
        except Inter1Error as e:
            sys.exit(f"{e}\nSet INTERHUMAN_API_KEY (see .env) before running without --dry-run.")

    by_source = load_candidates()
    cands = ordered_candidates(by_source, min_face=args.min_face)
    tallies, done = existing_tallies()
    print(f"{len(cands)} candidates, {len(done)} already analyzed, tallies={tallies}", flush=True)

    calls = 0
    for cand in cands:
        cid = clip_id(cand)
        if cid in done:
            continue
        wanted = ([c for c in CLUSTERS if c["id"] in args.only_clusters.split(",")]
                  if args.only_clusters else CLUSTERS)
        if all(tallies[c["id"]] >= args.target for c in wanted):
            print("all clusters at target, stopping", flush=True)
            break
        if calls >= args.max:
            print(f"hit call cap ({args.max}), stopping", flush=True)
            break

        path = clip_path(cand)
        if not os.path.exists(path):
            r = cut_clip(os.path.join(RAW, f"{cand['source']}.mp4"), cand["start"], CLIP_LEN, path)
            if r.returncode != 0 or not os.path.exists(path):
                print(f"[{cid}] cut failed: {r.stderr[:160]}", flush=True)
                continue

        if args.dry_run:
            print(f"[{cid}] cut ok ({os.path.getsize(path)/1e6:.2f} MB) - dry run, not uploading", flush=True)
            continue

        try:
            result = analyze_file(path, key=key)
        except Inter1Error as e:
            if e.is_quota:
                print(f"[{cid}] QUOTA EXHAUSTED - stopping now, {calls} calls made this run", flush=True)
                break
            print(f"[{cid}] failed: {e}", flush=True)
            if e.fatal and e.error_id in {"ih2001", "ih2002", "ih2003"}:
                print("credentials rejected - aborting run", flush=True)
                break
            continue

        calls += 1
        cluster, margin = classify(result)
        rec = {
            "clip_id": cid,
            "source": cand["source"],
            "title": BY_KEY[cand["source"]]["title"],
            "year": BY_KEY[cand["source"]]["year"],
            "start": cand["start"],
            "duration": CLIP_LEN,
            "prefilter": {k: cand.get(k) for k in ("face_frac", "face_size", "voiced", "score")},
            "cluster": cluster,
            "margin": None if margin == float("inf") else round(margin, 2),
            "scores": {k: round(v, 2) for k, v in cluster_scores(result).items()},
            "result": result,
        }
        # Write before anything else can fail: never lose a call we already paid for.
        with open(result_path(cid), "w") as f:
            json.dump(rec, f, indent=1)
        done[cid] = rec
        if cluster:
            tallies[cluster] += 1

        label = cluster or f"ambiguous(margin={rec['margin']})"
        sigs = ",".join(sorted({s.get("type") for s in result.get("signals", [])}))
        print(f"[{cid}] {label:32} calls={calls} signals=[{sigs}]", flush=True)

    print(f"\ndone. {calls} API calls this run. tallies: {tallies}", flush=True)
    usable = sum(tallies.values())
    print(f"usable clips: {usable}; need {args.target * 3} for a full 3-cluster board rotation", flush=True)


if __name__ == "__main__":
    main()
