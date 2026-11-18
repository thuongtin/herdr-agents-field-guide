#!/bin/zsh
# Functional test of hc-claude-resume in a separate core, with forced misses:
#   once     misses its probe at the first start      -> restarted once, then has a status
#   always   misses at every start                    -> 2 restarts, then "giving up"
#   dupold / dupnew   two records for one session     -> only the later one is resumed
#   stale / moved     same, but the old tab's shell was not lost -> it stays a shell
#   off      misses while "no-status-retry" exists    -> logged, not restarted
#
#   functional-test.sh <tag>        WAIT=<seconds, default 200>
# Needs 5 session ids in $PROBE_BASE/copies.txt. See docs/reproduce.md.
set -u
TAG=${1:?usage: functional-test.sh <tag>}
HERE=${0:A:h}
source "$HERE/probe-env.zsh"
OUT=$BASE/$TAG; mkdir -p "$OUT"; ln -sfn "$OUT" "$BASE/cur"
(( ${#session_ids} >= 5 )) || { echo "needs 5 session ids in $BASE/copies.txt" >&2; exit 1; }
: > "$RS/events.log"

once=$(new_terminal "$TAG-once"); always=$(new_terminal "$TAG-always")
dupold=$(new_terminal "$TAG-dupold"); dupnew=$(new_terminal "$TAG-dupnew")
stale=$(new_terminal "$TAG-stale"); moved=$(new_terminal "$TAG-moved")
sleep 6
now=$(date +%s)
write_record "$once" "${session_ids[1]}" "$now";   touch "$OUT/miss-$once"
write_record "$always" "${session_ids[2]}" "$now"; touch "$OUT/missalways-$always"
write_record "$dupold" "${session_ids[3]}" $((now-100)); write_record "$dupnew" "${session_ids[3]}" "$now"
write_record "$stale" "${session_ids[4]}" $((now-100));  write_record "$moved" "${session_ids[4]}" "$now"
echo "once=$once always=$always dupold=$dupold dupnew=$dupnew stale=$stale moved=$moved" | tee "$OUT/terms.txt"
date '+%H:%M:%S killing the shells (all but "stale")'
kill -9 "$(program_pid "$once")" "$(program_pid "$always")" "$(program_pid "$dupold")" "$(program_pid "$dupnew")" "$(program_pid "$moved")"
sleep "${WAIT:-200}"
for t in $once $always $dupold $dupnew $stale $moved; do
  echo "$t $(terminal_state "$t") record=$([[ -e "$RS/$t.json" ]] && echo yes || echo no)"
done | tee "$OUT/result.txt"

echo "--- off switch"
touch "$RS/no-status-retry"
off=$(new_terminal "$TAG-off"); sleep 5
write_record "$off" "${session_ids[5]}" "$(date +%s)"; touch "$OUT/missalways-$off"
kill -9 "$(program_pid "$off")"
sleep 60
echo "$off $(terminal_state "$off")" | tee -a "$OUT/result.txt"
rm -f "$RS/no-status-retry"

echo "--- launches"; cat "$OUT/launch.log"
echo "--- events"; grep -vE "SessionEnd|recorded session" "$RS/events.log"
remove_probe_terminals
