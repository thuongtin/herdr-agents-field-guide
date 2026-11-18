# Bringing agents back after a reboot

[Guide](../README.en.md)

## The gap

herdr-core keeps terminals across a reboot, a logout or a crash of the core. A lost terminal comes back with its name, folder and scrollback, but as a plain login shell. The command that ran there is not started again.

The tab is still called "Claude (work)" or "Codex", so the natural move is to type the agent's "continue" command. For Claude Code with several accounts that signs in with the default account, not the one the tab was using. The layout survives; the agents and their accounts do not.

[`bin/hc-claude-resume`](../bin/hc-claude-resume) closes that gap for Claude Code, Codex and Grok.

## How it works

```mermaid
flowchart LR
    subgraph before["While the agent runs"]
        H["Agent hook<br/>session start, each prompt"] --> R["Record per terminal<br/>agent, session, folder, account label"]
    end
    subgraph after["After the terminal was lost"]
        S["Recovered shell<br/>first prompt"] --> K["check"]
        K --> Q["Start queue"]
        Q --> C["Resume command typed into the shell"]
        C --> W["Watcher follows the tab"]
    end
    R -. "read by" .-> K
```

1. **Record.** A hook of the agent writes one small JSON file per terminal: agent, session id, folder, account label, the agent's pid and the pid of the terminal's program. No tokens are stored.
2. **Detect the loss.** At the first prompt of a shell, `check` compares the record with the terminal. The agent is resumed only when the terminal's program changed since the record was written, or the record is older than the last boot. Both mean the terminal was lost and recovered.
3. **Resume.** `check` prints one command line and the shell runs it: `cd <folder> && claude-<label> --resume <id>`, `codex resume [flags] <id>` or `grok [flags] --resume <id>`.

Things that deliberately do not resume: quitting the agent in place, a crash in place, a subshell, a second shell in the same terminal. In those cases the terminal's program is still the same one.

What `check` decides at the first prompt of a shell:

```mermaid
flowchart TD
    A["Shell shows its first prompt"] --> B{"Record for this terminal?"}
    B -- "no" --> Z["Nothing happens"]
    B -- "yes" --> C{"Already resumed for this terminal program?"}
    C -- "yes" --> Z
    C -- "no" --> D{"Terminal program changed,<br/>or record older than the last boot?"}
    D -- "no" --> E["Agent ended in place: no resume<br/>Codex and Grok records are removed 25 s later"]
    D -- "yes" --> F{"An agent already in the foreground?"}
    F -- "yes" --> Z
    F -- "no" --> G{"Same session running elsewhere,<br/>or a later record in another live terminal?"}
    G -- "yes" --> Y["Step back, logged as not resumed"]
    G -- "no" --> I{"Launcher or agent installed?"}
    I -- "no" --> X["No resume, nothing logged<br/>never another account"]
    I -- "yes" --> J["Wait for this tab's turn"]
    J --> K["Print the resume command, start the watcher"]
```

## Install

Tested on macOS with zsh. Requirements: `hc` in `PATH`, Python 3.9 or newer.

1. Copy `bin/hc-claude-resume` to `~/.local/bin/` and make it executable.
2. Claude Code: merge [`examples/claude-settings-hooks.json`](../examples/claude-settings-hooks.json) into `~/.claude/settings.json`. Keep the hooks you already have; back the file up first.
3. Codex: merge [`examples/codex-hooks.json`](../examples/codex-hooks.json) into `~/.codex/hooks.json` with `__HOME__` replaced, and make sure hooks are enabled in the Codex config. Codex asks you to review new hooks; until you accept, they do not run. See [Codex and Grok](codex-and-grok.md).
4. Grok: nothing to add. It runs the hooks of `~/.claude/settings.json` itself.
5. Paste [`shell/zshrc-resume-trigger.zsh`](../shell/zshrc-resume-trigger.zsh) into `~/.zshrc`.
6. Sessions that were already running do not pick up new hooks. Run `hc-claude-resume seed` once to record the running Claude Code sessions.
7. Several Claude accounts: use one launcher per account, see [one account per tab](claude-accounts.md) and [`examples/claude-account-launcher.sh`](../examples/claude-account-launcher.sh). The record stores the label and the resume uses the same launcher. A missing launcher means no resume; the tool never falls back to another account.

Check with `hc-claude-resume list` and the log `~/.local/state/hc-claude-resume/<core>/events.log`.

## Rules the record follows

| Situation | What happens | Why |
|---|---|---|
| SessionStart hook did not run (folder trust dialog not accepted yet) | UserPromptSubmit records the session at the first prompt | Claude Code skips SessionStart hooks before the trust dialog |
| `claude -p`, `codex exec` or a subagent started inside the tab | Not recorded | It inherits the terminal id; only the top agent of the terminal counts (the hook walks the parent processes) |
| A wrapper is the terminal's foreground program | Still recorded | The check walks parents instead of comparing with the foreground |
| User ends the Claude session on purpose (`/exit`, `/clear`, logout, resume of another session) | Record removed | SessionEnd reason says so |
| Agent killed (shutdown, closed pty, SIGTERM, SIGHUP) | Record kept | Those arrive as SessionEnd reason `other`, and a shutdown must not erase the record |
| Codex or Grok quit in place | Record removed about 25 s later | They have no usable end hook; a later shell notices the agent is gone while the terminal's program is unchanged. The delay keeps a shutdown from looking like a quit |
| Tab was a bare shell before the hook existed | `hc-claude-resume set <terminal> <agent> <session-id> [folder]` | Writes a record by hand; the next shell in that terminal resumes it |
| Record older than 30 days | Pruned | |

The life of a Claude Code record:

```mermaid
stateDiagram-v2
    [*] --> Recorded: SessionStart or first prompt
    Recorded --> Recorded: every prompt refreshes it
    Recorded --> Removed: user quits, clears, logs out
    Recorded --> Kept: agent killed, shutdown, closed terminal
    Kept --> Resumed: terminal recovered as a shell
    Resumed --> Recorded: the resumed session records itself again
    Kept --> Removed: recorded in another tab, or older than 30 days
    Removed --> [*]
```

## One session, two tabs

A record survives when an agent dies in place. If the user then continues the same session in another tab, two records point at one session, and after the next reboot both tabs open it. This happened once.

Now:

- When a session is recorded for a terminal, records of the same session whose agent is not running are removed.
- At resume time, a terminal steps back when the same session runs elsewhere or another live terminal has a later record for it.

## Starts take turns, and missed probes are repaired

After a reboot all shells reach their first prompt together. Starting all agents at once makes Claude Code lose its status probe, see [root cause](missing-agents-root-cause.md). So `check` does two more things.

**Queue.** One agent start at a time per core. The next start waits until the previous agent reports a status, 20 s at most per agent, 300 s at most in total. While a tab waits, its prompt shows `hc-claude-resume: waiting for this tab's turn to resume its agent (ctrl+c skips)`.

```mermaid
sequenceDiagram
    participant A as Tab A
    participant S as Start slot file, one per core
    participant B as Tab B
    participant C as herdr-core
    A->>S: lock, write my mark, unlock
    A->>A: runs its resume command
    B->>S: lock, read the mark of tab A
    Note over B,C: prompt shows the waiting line, ctrl+c skips
    loop every 0.5 s, 2 s to 20 s
        B->>C: has tab A reported a status?
        C-->>B: not yet
    end
    C-->>B: tab A reports idle
    B->>S: write my mark, unlock
    B->>B: runs its resume command
    Note over A,B: a third tab waits for the lock all this time
```

**Watcher.** For every resume a detached `status-check` process watches the tab:

- A status appears: done, logged as `reports <state> after Ns`.
- The tab shows Claude Code's empty input box for 12 s and still has no status: the probe was missed.
- The watcher then waits for a quiet machine: no agent start for 30 s and three looks in a row where a 50 ms busy loop takes less than 1.5x its CPU time. After 10 minutes it goes ahead anyway.
- It kills the terminal's program. The core recovers the terminal as a shell and `check` resumes the session again, through the same queue.
- At most 2 restarts per terminal per hour. Then: `giving up (restart the tab's program by hand)`.
- A tab that is busy, shows a dialog, or has text in the input box is left alone. After 4 minutes without an idle prompt the watcher stops.

```mermaid
stateDiagram-v2
    [*] --> Watching: resume command printed
    Watching --> Done: a status is reported
    Watching --> IdleSeen: empty input box, no status
    IdleSeen --> Watching: busy, dialog or typing
    IdleSeen --> Missed: idle for 12 s without status
    Missed --> Done: off switch present, only logged
    Missed --> GaveUp: 2 restarts already done this hour
    Missed --> WaitQuiet: restart allowed
    WaitQuiet --> Watching: busy, dialog or typing
    WaitQuiet --> Done: a status is reported after all
    WaitQuiet --> Restart: 3 quiet looks in a row, or 10 minutes passed
    Restart --> [*]: terminal program killed, check resumes the session, a new watcher starts
    Watching --> LeftAlone: 4 minutes without an idle prompt
    Done --> [*]
    GaveUp --> [*]
    LeftAlone --> [*]
```

Knobs, all constants at the top of the script:

| Constant | Default | Meaning |
|---|---|---|
| `START_GAP_S` | 2.0 | Least seconds between two starts |
| `START_SETTLE_MAX_S` | 20 | Longest wait for the previous agent's status |
| `START_WAIT_MAX_S` | 300 | Longest a start is held in total |
| `STATUS_IDLE_CONFIRM_S` | 12 | Idle prompt without status for this long means a miss |
| `STATUS_RETRY_MAX` | 2 | Restarts per terminal |
| `RESTART_QUIET_S` | 30 | No agent start for this long before a restart |
| `RESTART_CONTENTION_MAX` | 1.5 | Highest contention factor that counts as quiet |
| `RESTART_WAIT_MAX_S` | 600 | Longest wait for a quiet machine |

Switches, empty files in `~/.local/state/hc-claude-resume/<core>/`:

- `no-status-retry`: the watcher only logs a miss and never restarts.
- `debug`: every hook call logs its process chain and payload keys.

## What you will notice

- Agent tabs come back one after another. Twelve tabs took about 35 s on a calm machine and longer under load.
- A tab may restart itself once in the first minutes after a reboot. The session is the same; the scrollback above it stays.
- `events.log` tells the story of each tab: `start held`, `recorded`, `status check`, `not resumed`.

## Limits

- macOS and zsh only were tested. On Linux the boot time lookup returns nothing, so only the "terminal program changed" rule applies.
- The idle check reads the screen for Claude Code's prompt character and the words "esc to interrupt". A redesign of that screen breaks the check; the watcher then does nothing, which is the safe side.
- Verified by simulated reboots in a separate core and by two real reboots of the earlier, simpler version. The queue and the watcher have not gone through a real reboot yet. See [observed results](observed-results.md).
- Only a short list of on/off flags is carried over to the resume command (`RESUME_FLAGS` in the script), never a flag that takes a value. With an account launcher no flag is carried over: the launcher adds its own.
