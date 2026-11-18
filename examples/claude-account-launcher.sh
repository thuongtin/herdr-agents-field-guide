#!/bin/sh
# Example account launcher. Install one copy per account as ~/.local/bin/claude-<label>
# and replace "work" below with the same label.
#
# The resume tool brings a session back with the launcher of the account it ran as:
# CLAUDE_ACCOUNT_LABEL is what the hook stores, and `claude-<label> --resume <id>` is
# what it runs after a reboot. A session started with plain `claude` is recorded as the
# default account and resumed with plain `claude`.
#
# The settings file holds that account's sign-in. Keep it out of any repository; the
# resume tool never reads or stores it.
export CLAUDE_ACCOUNT_LABEL="work"
exec claude --settings "$HOME/.claude/accounts/work.json" "$@"
