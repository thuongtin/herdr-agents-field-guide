# Paste into ~/.zshenv on a macOS machine that is also reached over ssh.
#
# herdr-core starts on demand in the session of whoever asks first. Started from an ssh
# connection it stays inside that ssh session, where nothing can read the login Keychain
# (agent credentials, status line helpers). Without the ssh markers it starts through
# launchd in the GUI login instead, so start it that way before an ssh command talks to
# it. A no-op when a core is already running. See docs/core-environment.md.
if [[ -n "$SSH_CONNECTION" && "$ZSH_EXECUTION_STRING" == (*herdr-core*|hc|hc\ *|*/hc|*/hc\ *) && -x "$HOME/.local/bin/hc" ]]; then
  env -u SSH_CONNECTION -u SSH_CLIENT -u SSH_TTY "$HOME/.local/bin/hc" server status >/dev/null 2>&1 </dev/null
fi
