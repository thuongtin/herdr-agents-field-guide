# Sourced by the test scripts. Everything runs in a SEPARATE herdr-core (its own
# terminals and state folder), never in the core that holds your real tabs.
#
#   PROBE_CORE      name of the separate core              (default: probe)
#   PROBE_BASE      folder for logs of the runs            (default: $TMPDIR/hc-probe)
#   PROBE_LABEL     account label of the test launcher     (default: probe)
#   PROBE_WORK_DIR  folder the test sessions run in        (default: current folder)
#   PROBE_SETTINGS  optional settings file for the test launcher (an account file)
CORE=${PROBE_CORE:-probe}
BASE=${PROBE_BASE:-${TMPDIR:-/tmp}/hc-probe}
LABEL=${PROBE_LABEL:-probe}
WORK=${PROBE_WORK_DIR:-$PWD}
RS=$HOME/.local/state/hc-claude-resume/$CORE
mkdir -p "$BASE" "$RS"

if [[ "$CORE" == default ]]; then
  echo "refusing: PROBE_CORE must not be the default core" >&2; exit 1
fi
for need in hc jq "claude-$LABEL"; do
  command -v "$need" >/dev/null 2>&1 || { echo "missing in PATH: $need" >&2; exit 1; }
done
if [[ ! -s "$BASE/copies.txt" ]]; then
  echo "no session ids in $BASE/copies.txt (run tools/copy-transcripts.py first)" >&2; exit 1
fi

# A clean environment: the core hands its environment to every terminal, so a core
# started from an agent's shell would pass that agent's variables to the test tabs.
P() {
  env -i HOME="$HOME" USER="$USER" LOGNAME="$USER" SHELL=/bin/zsh \
    PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin" \
    HC_SESSION="$CORE" PROBE_BASE="$BASE" ${PROBE_SETTINGS:+PROBE_SETTINGS=$PROBE_SETTINGS} "$@"
}

new_terminal() {  # name -> terminal address (a kept shell)
  P hc run --bg --keep --no-parent --name "$1" --cwd "$WORK" --json | jq -r '.terminal.address // .address'
}
write_record() {  # terminal session-id recorded-at
  jq -n --arg t "$1" --arg s "$2" --arg cwd "$WORK" --arg label "$LABEL" --argjson at "$3" \
    '{terminal:$t,agent:"claude",session_id:$s,cwd:$cwd,account:$label,flags:[],agent_pid:0,program_pid:0,recorded_at:$at,source:"set"}' \
    > "$RS/$1.json"
}
program_pid() { P hc get "$1" --json | jq -r '(.terminal // .).pid'; }
terminal_state() {
  P hc get "$1" --json | jq -c '(.terminal // .) | {status:(.status.state // null), fg:((.foreground.argv // [""])[0] | split("/") | last)}'
}
remove_probe_terminals() {
  local t
  for t in $(P hc ls --json | jq -r '.terminals[].address'); do
    P hc kill "$t" >/dev/null 2>&1; P hc rm "$t" >/dev/null 2>&1
  done
}
session_ids=("${(@f)$(cat "$BASE/copies.txt")}")
