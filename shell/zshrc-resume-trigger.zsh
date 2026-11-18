# Paste into ~/.zshrc, after your prompt theme and plugins are loaded.
#
# herdr-core only gives a lost terminal a fresh shell. This block resumes the agent
# session that ran in the terminal, using the record written by the hc-claude-resume
# hook (see docs/resume-after-reboot.md).
#
# It runs from zle-line-init, as if the command line had been typed. Do not move it to
# plain startup code or to precmd: a prompt theme with an "instant prompt" (for example
# powerlevel10k) redirects output there, and the agent then starts without a terminal.
#
# Conditions: an interactive shell, inside a herdr-core terminal, not a shell started to
# run one command (zsh -ic '...'), not a shell started by Claude Code itself, and a
# record exists for this terminal.
if [[ -o interactive && -n "$HC_TERMINAL_ID" && -z "$ZSH_EXECUTION_STRING" && -z "$CLAUDECODE" ]] \
   && [[ -f "$HOME/.local/state/hc-claude-resume/${${HC_TERMINAL_SOCKET:h:t}:-default}/$HC_TERMINAL_ID.json" ]]; then
  _hc_claude_resume_once() {
    add-zle-hook-widget -d line-init _hc_claude_resume_once
    local cmd
    # Agent starts take turns after a reboot, so `check` can hold this line for a while.
    zle -M "hc-claude-resume: waiting for this tab's turn to resume its agent (ctrl+c skips)"
    zle -R
    cmd=$("$HOME/.local/bin/hc-claude-resume" check 2>/dev/null)
    local rc=$?
    zle -M ""
    (( rc == 0 )) && [[ -n "$cmd" ]] || return 0
    # The leading space keeps the line out of the history when HIST_IGNORE_SPACE is set.
    BUFFER=" $cmd"
    zle accept-line
  }
  autoload -Uz add-zle-hook-widget
  add-zle-hook-widget line-init _hc_claude_resume_once
fi
