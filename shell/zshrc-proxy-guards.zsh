# Paste into ~/.zshrc BEFORE the line that sources a shell plugin which wraps the shell
# in its own nested pseudo-terminal (seen with the smart-suggestion plugin in proxy mode).
#
# Why: the multiplexer finds agents by the foreground process of a terminal. A wrapper
# that opens a nested shell hides `claude` / `codex` behind its own process, and a
# command passed with `zsh -ic '<cmd>'` never runs because the nested shell starts first.
# See docs/shell-pitfalls.md. Replace the variable with the off switch of your plugin.

# Terminals of the herdr TUI product set HERDR_ENV=1.
[[ "$HERDR_ENV" == "1" ]] && SMART_SUGGESTION_PROXY_MODE=false

# A shell started to run a command (how the Herdr app launches menu entries:
# zsh -lic '"$@"; exec "$0" -li' zsh <cmd>) must not enter proxy mode.
[[ -n "$ZSH_EXECUTION_STRING" ]] && SMART_SUGGESTION_PROXY_MODE=false

# herdr-core terminals recovered after a reboot are plain `zsh -l`: neither of the two
# markers above is set there, only HC_TERMINAL_ID.
[[ -n "$HC_TERMINAL_ID" ]] && SMART_SUGGESTION_PROXY_MODE=false
