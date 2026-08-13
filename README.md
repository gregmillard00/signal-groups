# Signal Groups

A [NYT Connections](https://www.nytimes.com/games/connections)-style puzzle built on
real social-signal analysis. Every tile is a ~10 second clip from a public-domain film,
run through [interhuman.ai](https://interhuman.ai)'s `inter1` model. The groups are not
themes a person wrote - they are clusters of what the model actually perceived.

Find the three groups of three. Lives are unlimited; your score is how few mistakes it
took, so **lower is better**.

## How a board is made

1. `fetch_sources.py` pulls public-domain films from the Internet Archive.
2. `prefilter.py` finds segments with a visible face, using YuNet ONNX detection, and
   discards the rest before spending any API calls.
3. `analyze.py` sends each surviving clip to `inter1` and stores what it returned.
4. `clusters.py` assigns each clip to one of five signal clusters (agreement-interest,
   confidence, hesitation-uncertainty, frustration-disagreement, skepticism-stress).
5. `build_deck.py` assembles boards.

### The one design decision worth explaining

A clip rarely belongs to exactly one cluster - real behaviour is mixed, and forcing a
single label produced boards where two groups were defensibly the same. So membership is
resolved **per board** rather than globally:

```python
def eligible_for(payload, triple):
    hit = set(payload["_clusters"]) & set(triple)
    return next(iter(hit)) if len(hit) == 1 else None
```

A clip is only usable on a board if it matches exactly one of that board's three groups.
Ambiguity is resolved by the company a clip keeps, not by flattening it in advance. This
is what makes the puzzle fair: every tile has exactly one defensible home *on the board
it appears on*.

## Scoring

- Lives are unlimited. A wrong guess costs score, never the run.
- Score = number of wrong guesses. `0` is perfect.
- The scoreboard is shared by all players and polls every 10 seconds, so scores posted
  elsewhere appear without a reload.
- The server validates every submission: the board id must exist and the score must be
  plausible. Nothing the client sends is trusted except the display name.

## Running it

```bash
pip install -r requirements.txt
python server.py            # http://127.0.0.1:8770
```

`data/deck.json` (the board definitions) is in this repository, but the clip media it
points at is not - `static/clips/` is gitignored, since the video is regenerated from
the source films rather than stored here. A fresh clone will serve the interface and
grade guesses, but the tiles have no video until you build the clips yourself.

### Building a deck of your own

The pipeline needs an `inter1` API key. Get one from
[interhuman.ai](https://interhuman.ai) by signing up on their site and creating a key
in your own account, then put it in a `.env` file at the root of this repository:

```
INTERHUMAN_API_KEY=your-key-here
```

Nothing loads that file implicitly - the code reads `os.environ`, so export it before
running the pipeline (the same way `finalize.sh` does):

```bash
set -a; . ./.env; set +a
python fetch_sources.py     # download public-domain films from archive.org into raw/
python sweep.py             # find candidate 10s windows (local, no API calls)
python analyze.py           # cut the clips and send them to inter1 (this costs money;
                            # --dry-run cuts them without calling the API)
python build_deck.py        # write data/deck.json and publish clips to static/clips/
```

`build_deck.py --demo` builds a board without any `inter1` labels, so you can preview
the interface before you have a key. Those boards are flagged provisional everywhere
they appear.

## Layout

| path | what it is |
|---|---|
| `server.py` | Flask app, grading, scoreboard |
| `static/game.js` | Game client |
| `build_deck.py` | Board assembly and the per-board exclusivity rule |
| `analyze.py` | `inter1` calls, with incremental saves |
| `prefilter.py` | Face detection, run before spending API budget |
| `data/deck.json` | The playable deck |
| `data/scores.json` | Scoreboard, written atomically under a lock |

## Notes

- Grading is server-side. The client is told only whether a guess was right and whether
  it was one away - never which tiles were wrong, and never the solution.
- `analyze.py` saves after every call. API budget spent is never lost to a crash.
- `.env` is gitignored. No API key, and no credential of any kind, is in this repository.
