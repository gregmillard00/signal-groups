#!/usr/bin/env bash
# The Signal Groups game (#32), served at interhuman-connections.pl-labs.net.
#
# WHY THIS EXISTS (#474, 2026-09-11)
#
# Two problems, one fix.
#
# 1. NOTHING RESTARTED IT. The process had run since 17 August from an interactive
#    login session, reparented to PID 1, with no systemd unit and no entry in
#    site_watchdog.sh. Of 61 published hostnames it was the only one that would
#    have stayed down if it died. Twenty-five days of uptime is stability, not
#    supervision - it only means nothing has knocked it over yet.
#
# 2. IT INHERITED FAR MORE ENVIRONMENT THAN IT NEEDED. Started from a shell that had
#    sourced the operator's .env, so the process carried a number of unrelated
#    credentials into a public web server that required none of them. Fixed here, and
#    the specifics live in the internal ticket rather than in this file: THIS REPO IS
#    PUBLIC, and an inventory of what was once exposed is worth more to a stranger
#    than to a maintainer.
#
#    server.py imports only stdlib and flask, and reads exactly one variable: PORT.
#
# So this starts it with a DELIBERATE, minimal environment. The opposite failure is
# already recorded in /home/greg/pl-labs-review/run.sh: that service ran for four
# days only because the shell that started it happened to export a key, and died
# the moment a watchdog restarted it cleanly. The lesson from both is the same -
# a service's environment should be stated here, not inherited from whoever
# happened to type the command.
set -u
cd "$(dirname "$0")"

PIDFILE="interhuman.pid"
LOG="run.log"
PORT="${PORT:-8770}"
PY=/home/greg/personal-agent/venv/bin/python3

# Is something already serving, whoever started it? The pidfile only knows about
# processes THIS script launched, and the original was started by hand - so a
# pidfile check alone would have reported "not running" for a live server and
# invited a second one onto the same port.
listening() { ss -ltn 2>/dev/null | grep -q "127.0.0.1:${PORT} "; }

start() {
  if listening; then echo "already serving on :$PORT"; return 0; fi
  # setsid, not just nohup: a job left in the caller's process group dies when that
  # group tears down, which has killed real work on this box before.
  setsid nohup env -i \
    PATH=/usr/bin:/bin \
    HOME="$HOME" \
    PORT="$PORT" \
    "$PY" server.py >> "$LOG" 2>&1 < /dev/null &
  echo $! > "$PIDFILE"
  for _ in 1 2 3 4 5 6 7 8 9 10; do listening && break; sleep 1; done
  if listening; then echo "started $(cat "$PIDFILE") on :$PORT"; else
    echo "FAILED to come up on :$PORT - see $LOG" >&2; return 1; fi
}

stop() {
  if [ -f "$PIDFILE" ] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
    kill "$(cat "$PIDFILE")" 2>/dev/null
  else
    # Started by hand before this script existed, so there is no pidfile. Find it
    # BY THE PORT IT HOLDS, never by command-line pattern: `pkill -f "python3
    # server.py"` also matches the shell running this very script, whose command
    # line contains that string. That is not hypothetical - the same mistake killed
    # a shell on this box earlier today with `pkill -f serve_wf.py`.
    local holder
    holder="$(ss -ltnp 2>/dev/null | grep "127.0.0.1:${PORT} " \
              | grep -o 'pid=[0-9]*' | head -1 | cut -d= -f2)"
    [ -n "$holder" ] && kill "$holder" 2>/dev/null
  fi
  rm -f "$PIDFILE"
  sleep 1
  echo stopped
}

case "${1:-start}" in
  start)   start ;;
  stop)    stop ;;
  restart) stop; sleep 1; start ;;
  status)  if listening; then echo running; else echo "not running"; exit 1; fi ;;
  *)       echo "usage: $0 {start|stop|restart|status}" >&2; exit 2 ;;
esac
