"""Signal Groups - a Connections-style game over inter1's social-signal labels.

Serves the board and grades guesses. Grading happens server-side so the answer key
isn't sitting in the page source for anyone who opens devtools; the client only
learns a group once it has been solved (or once the player is out of lives).
"""
import json
import os
import threading
from datetime import datetime, timezone

from flask import Flask, jsonify, render_template, request, send_from_directory

HERE = os.path.dirname(os.path.abspath(__file__))
DECK_PATH = os.path.join(HERE, "data", "deck.json")

# Infinite lives, 2026-08-09. A wrong guess no longer ends the run - it costs you
# score. The board is always completable, so the number that matters is how few
# mistakes it took, and lower is better. MAX_MISTAKES is kept only so the client can
# show a scale; nothing enforces it any more.
MAX_MISTAKES = 0  # 0 = unlimited

app = Flask(__name__)


def load_deck():
    if not os.path.exists(DECK_PATH):
        return None
    with open(DECK_PATH) as f:
        return json.load(f)


def public_board(board):
    """The board as the client may see it: tiles shuffled, group membership stripped."""
    tiles = []
    for g in board["groups"]:
        for c in g["clips"]:
            tiles.append({
                "id": c["id"],
                "video": c["video"],
                "poster": c["poster"],
                "title": c["title"],
                "year": c["year"],
                "credit": c["credit"],
                "at": c["at"],
            })
    # Deterministic per board, so a refresh doesn't reshuffle mid-game.
    tiles.sort(key=lambda t: t["id"])
    order = board.get("_order")
    if not order:
        idx = list(range(len(tiles)))
        seed = sum(ord(ch) for ch in board["id"])
        for i in range(len(idx) - 1, 0, -1):
            seed = (seed * 1103515245 + 12345) & 0x7FFFFFFF
            j = seed % (i + 1)
            idx[i], idx[j] = idx[j], idx[i]
        order = idx
    tiles = [tiles[i] for i in order]
    return {
        "id": board["id"],
        "tiles": tiles,
        "group_count": len(board["groups"]),
        "per_group": len(board["groups"][0]["clips"]) if board["groups"] else 0,
        "max_mistakes": MAX_MISTAKES,
    }


def find_board(deck, board_id):
    for b in deck["boards"]:
        if b["id"] == board_id:
            return b
    return None


def group_reveal(g):
    """Everything the client gets once a group is solved or revealed, including
    inter1's own rationale for each clip."""
    return {
        "cluster": g["cluster"],
        "name": g["name"],
        "blurb": g["blurb"],
        "color": g["color"],
        "tint": g["tint"],
        "signals": g["signals"],
        "difficulty": g.get("difficulty", 0),
        "clips": [
            {
                "id": c["id"],
                "title": c["title"],
                "year": c["year"],
                "at": c["at"],
                "credit": c["credit"],
                "signals": c.get("signals", []),
                "label_source": c.get("label_source", "inter1"),
            }
            for c in g["clips"]
        ],
    }


@app.route("/")
def index():
    deck = load_deck()
    return render_template("index.html", deck_missing=deck is None)


@app.route("/api/deck")
def api_deck():
    deck = load_deck()
    if not deck:
        return jsonify({"error": "no deck built yet"}), 503
    return jsonify({
        "provisional": deck.get("provisional", False),
        "notice": deck.get("notice"),
        "clusters": deck["clusters"],
        "clip_count": deck.get("clip_count", 0),
        "boards": [{"id": b["id"]} for b in deck["boards"]],
    })


@app.route("/api/board/<board_id>")
def api_board(board_id):
    deck = load_deck()
    if not deck:
        return jsonify({"error": "no deck built yet"}), 503
    board = find_board(deck, board_id)
    if not board:
        return jsonify({"error": "no such board"}), 404
    return jsonify(public_board(board))


@app.route("/api/guess", methods=["POST"])
def api_guess():
    """Grade a selection. Returns solved / one-away / wrong without leaking which
    group a wrong guess was closest to."""
    body = request.get_json(silent=True) or {}
    deck = load_deck()
    if not deck:
        return jsonify({"error": "no deck built yet"}), 503
    board = find_board(deck, body.get("board", ""))
    if not board:
        return jsonify({"error": "no such board"}), 404

    picked = set(body.get("tiles") or [])
    per_group = len(board["groups"][0]["clips"])
    if len(picked) != per_group:
        return jsonify({"error": f"select exactly {per_group} clips"}), 400

    best_overlap = 0
    for g in board["groups"]:
        ids = {c["id"] for c in g["clips"]}
        overlap = len(ids & picked)
        best_overlap = max(best_overlap, overlap)
        if overlap == per_group:
            return jsonify({"correct": True, "group": group_reveal(g)})

    # Only "one away" goes back, not the raw overlap count - telling the player
    # they matched 0 vs 1 tile would give away more than the game intends.
    return jsonify({
        "correct": False,
        "one_away": best_overlap == per_group - 1,
    })


@app.route("/api/reveal/<board_id>")
def api_reveal(board_id):
    """Full answer key - the client calls this only after a win or a loss."""
    deck = load_deck()
    if not deck:
        return jsonify({"error": "no deck built yet"}), 503
    board = find_board(deck, board_id)
    if not board:
        return jsonify({"error": "no such board"}), 404
    groups = sorted(board["groups"], key=lambda g: g.get("difficulty", 0))
    return jsonify({"groups": [group_reveal(g) for g in groups]})


@app.route("/clips/<path:name>")
def clips(name):
    return send_from_directory(os.path.join(HERE, "static", "clips"), name)


SCORES_PATH = os.path.join(HERE, "data", "scores.json")
_scores_lock = threading.Lock()


def _load_scores():
    try:
        with open(SCORES_PATH) as f:
            return json.load(f)
    except Exception:
        return []


def _save_scores(rows):
    """Atomic write under a lock: the scoreboard is shared, so two players
    finishing at once must not truncate each other's entry."""
    tmp = SCORES_PATH + ".tmp"
    with open(tmp, "w") as f:
        json.dump(rows, f, indent=1)
    os.replace(tmp, SCORES_PATH)


@app.route("/api/score", methods=["POST"])
def api_score():
    body = request.get_json(silent=True) or {}
    name = str(body.get("name", "")).strip()[:24] or "anonymous"
    board_id = str(body.get("board_id", ""))[:64]
    try:
        mistakes = int(body.get("mistakes"))
    except (TypeError, ValueError):
        return jsonify({"error": "mistakes must be an integer"}), 400
    if mistakes < 0 or mistakes > 999:
        return jsonify({"error": "implausible score"}), 400
    # Server decides the timestamp and validates the board - a client is free to
    # send whatever it likes, so nothing it says is taken on trust except the name.
    # load_deck() is the accessor used everywhere else; there is no module-level DECK.
    if board_id not in {bd["id"] for bd in load_deck()["boards"]}:
        return jsonify({"error": "unknown board"}), 400
    row = {"name": name, "mistakes": mistakes, "board_id": board_id,
           "at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    with _scores_lock:
        rows = _load_scores()
        rows.append(row)
        _save_scores(rows)
    return jsonify({"ok": True})


@app.route("/api/scoreboard")
def api_scoreboard():
    """Everyone sees the same board. Fewest mistakes wins, earliest breaks ties."""
    with _scores_lock:
        rows = _load_scores()
    board_id = request.args.get("board_id")
    if board_id:
        rows = [r for r in rows if r.get("board_id") == board_id]
    rows.sort(key=lambda r: (r.get("mistakes", 999), r.get("at", "")))
    return jsonify({"scores": rows[:50], "total": len(rows)})


@app.route("/healthz")
def healthz():
    deck = load_deck()
    return jsonify({
        "ok": True,
        "deck": bool(deck),
        "boards": len(deck["boards"]) if deck else 0,
        "provisional": deck.get("provisional") if deck else None,
    })


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=int(os.environ.get("PORT", "8770")), debug=False)
