# Paste into ~/.zshenv on a Linux machine where herdr-core may be started by an
# automated Claude Code job (a bot, a scheduled task, a script run by an agent).
#
# herdr-core hands its own environment to every terminal. When the core was started from
# inside a Claude Code session, each tab inherits that session's markers: Claude Code
# then treats a normal tab as a child session and stops saving transcripts, auto memory
# and background tasks are off, and git gets GIT_EDITOR=true. Drop the markers, but only
# in the shell herdr-core itself spawned; shells started by a real Claude Code session
# keep theirs. See docs/core-environment.md.
#
# /proc is Linux only. On macOS use: [[ "$(ps -o comm= -p $PPID)" == *herdr-core ]]
# (not tested there; the case was only seen on Linux).
if [[ -n "$HC_TERMINAL_ID" && -n "$CLAUDECODE$CLAUDE_CODE_CHILD_SESSION" && -r /proc/$PPID/comm ]] \
   && [[ "$(</proc/$PPID/comm)" == herdr-core ]]; then
  unset AI_AGENT CLAUDECODE CLAUDE_PID CLAUDE_EFFORT \
        CLAUDE_CODE_CHILD_SESSION CLAUDE_CODE_ENTRYPOINT CLAUDE_CODE_EXECPATH \
        CLAUDE_CODE_SESSION_ID CLAUDE_CODE_SESSION_ATTENDED \
        CLAUDE_CODE_MESSAGING_SOCKET CLAUDE_CODE_MESSAGING_TOKEN \
        CLAUDE_CODE_DISABLE_AUTO_MEMORY CLAUDE_CODE_DISABLE_BACKGROUND_TASKS \
        BASH_MAX_TIMEOUT_MS ENABLE_TOOL_SEARCH GIT_EDITOR
fi
