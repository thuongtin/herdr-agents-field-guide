#!/bin/sh
# Test launcher for the probe core. Install as ~/.local/bin/claude-<label> (default
# label: probe). The resume tool starts it as `claude-<label> --resume <id>`.
#
# It adds a debug log per terminal and two switches that force the "missed probe"
# symptom, so the repair path can be tested without loading the machine:
#   <run folder>/miss-<terminal>        the next start in that terminal reports no status
#   <run folder>/missalways-<terminal>  every start in that terminal reports no status
# CLAUDE_CODE_DISABLE_TERMINAL_TITLE=1 is what makes a session report no status.
D="${PROBE_BASE:-${TMPDIR:-/tmp}/hc-probe}/cur"
mkdir -p "$D"
label=$(basename "$0"); label=${label#claude-}
export CLAUDE_ACCOUNT_LABEL="$label"
miss=0
if [ -e "$D/miss-$HC_TERMINAL_ID" ]; then rm -f "$D/miss-$HC_TERMINAL_ID"; miss=1; fi
[ -e "$D/missalways-$HC_TERMINAL_ID" ] && miss=1
[ "$miss" = 1 ] && export CLAUDE_CODE_DISABLE_TERMINAL_TITLE=1
echo "$(date +%H:%M:%S) start $HC_TERMINAL_ID miss=$miss" >> "$D/launch.log"
if [ -n "${PROBE_SETTINGS:-}" ]; then
  exec claude --settings "$PROBE_SETTINGS" --debug-file "$D/dbg-$HC_TERMINAL_ID.log" "$@"
fi
exec claude --debug-file "$D/dbg-$HC_TERMINAL_ID.log" "$@"
