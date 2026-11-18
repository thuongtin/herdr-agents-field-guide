#!/bin/zsh
# Reproduce the reboot path in a separate core: kept shells with resume records, then
# the core, its holder and the shells are killed at once and a new core recovers them
# all together, as after a real reboot.
#
#   simulate-reboot.sh <tag> [count]       WAIT=<seconds to watch, default 150>
#                                          PINGER=1 also measures the terminal's replies
# Results: $PROBE_BASE/<tag>/result.txt. See docs/reproduce.md before running.
set -u
TAG=${1:?usage: simulate-reboot.sh <tag> [count]}; N=${2:-12}
HERE=${0:A:h}
source "$HERE/probe-env.zsh"
OUT=$BASE/$TAG; mkdir -p "$OUT"; ln -sfn "$OUT" "$BASE/cur"
(( N <= ${#session_ids} )) || { echo "only ${#session_ids} session ids in $BASE/copies.txt" >&2; exit 1; }

: > "$OUT/terms.txt"; : > "$RS/events.log"
for i in $(seq 1 "$N"); do
  print -r -- "$(new_terminal "$TAG-$i") ${session_ids[$i]}" >> "$OUT/terms.txt"
done
sleep 8
now=$(date +%s)
while read -r t sid; do write_record "$t" "$sid" "$now"; done < "$OUT/terms.txt"

# The processes of the probe core only. Refuse when they cannot be told apart from the
# core that holds the real tabs.
holder=$(pgrep -f "herdr-core/$CORE/$CORE.holder" | head -1)
core=$(ps -o ppid= -p "${holder:-0}" 2>/dev/null | tr -d ' ')
main_holder=$(pgrep -f "herdr-core/default/default.holder" | head -1)
main_core=$(ps -o ppid= -p "${main_holder:-0}" 2>/dev/null | tr -d ' ')
if [[ -z "$holder" || -z "$core" || "$core" == "$main_core" || "$core" == 1 ]]; then
  echo "refusing: holder=$holder core=$core main core=$main_core"; exit 1
fi
shells=()
while read -r t sid; do shells+=("$(program_pid "$t")"); done < "$OUT/terms.txt"
date '+%H:%M:%S killing the probe core, its holder and its shells' | tee "$OUT/run.txt"
kill -9 "$core" "$holder" "${shells[@]}"
sleep 2
date '+%H:%M:%S starting a new probe core' | tee -a "$OUT/run.txt"
P hc ls --json > /dev/null 2>&1
if [[ -n "${PINGER:-}" ]]; then
  P hc run --bg --no-parent --name "ping-$TAG" --cwd "$WORK" -- /usr/bin/python3 "$HERE/osc7501-pinger.py" "$OUT/pinger.log" "${WAIT:-150}" >/dev/null
fi
uptime | tee -a "$OUT/run.txt"
sleep "${WAIT:-150}"
uptime | tee -a "$OUT/run.txt"

: > "$OUT/result.txt"
while read -r t sid; do
  cap=$(grep -h -m1 'Terminal capabilities' "$OUT/dbg-$t.log" 2>/dev/null | sed 's/.*programStatus=/programStatus=/' | cut -c1-60)
  print -r -- "$t $(terminal_state "$t") $cap" >> "$OUT/result.txt"
done < "$OUT/terms.txt"
cat "$OUT/result.txt"
echo "with status: $(grep -vc '"status":null' "$OUT/result.txt") of $N"
echo "--- events"; grep -E "status check|held" "$RS/events.log" | tail -40
if [[ -s "$OUT/pinger.log" ]]; then
  echo "--- slowest terminal replies (ms)"; awk '{gsub("ms","",$3); print $3, $1, $2}' "$OUT/pinger.log" | sort -n | tail -3
fi
remove_probe_terminals
