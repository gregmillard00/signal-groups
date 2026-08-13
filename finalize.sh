#!/bin/bash
# Waits for any in-flight sweep/analyze to finish, labels whatever new candidates
# the last sweep produced, then rebuilds the deck. Run detached; it is safe to
# re-run, since analyze.py skips clips it has already paid for.
cd "$(dirname "$0")"
set -a; . ./.env; set +a

while pgrep -f "sweep\.py|analyze\.py" > /dev/null; do sleep 30; done

"${PYTHON:-python3}" analyze.py --min-face 0.30 --max 25 --target 8 >> analyze.log 2>&1
"${PYTHON:-python3}" build_deck.py
