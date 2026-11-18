# Agents missing from the list after a reboot: root cause

[Guide](../README.en.md)

## Symptom

After a reboot every tab came back and every agent was resumed, but the Agents panel of the Herdr app showed only some of them. A tab that was clearly working showed no "working" state. On the first real case 9 of 14 Claude Code tabs were missing.

In `hc get <terminal> --json` the missing tabs had:

```json
{ "status": null, "reported": false, "foreground": { "argv": ["claude", "..."] } }
```

The agent was running in the foreground of the terminal. It simply never told the terminal what it was doing.

## How status reaches the list

herdr-core builds the status of a terminal only from what the program inside writes to the terminal: OSC 7501 reports. There is no command and no API call that sets a status from outside. A program that never sends a report has `reported: false` for its whole life and is invisible to anything that lists agents by status.

So the question became: why does Claude Code not send its reports in some tabs?

## What Claude Code does at startup

Seen in the debug log (`claude --debug-file <file>`, line "Terminal capabilities") of Claude Code 2.1.326 and 2.1.327:

1. Right after start it asks the terminal a few questions in one go, among them `OSC 7501 ; ?` ("do you accept program status reports?").
2. It waits for the answers with a fixed deadline of about 2 seconds. The clock starts when the questions are sent, and it runs while Claude Code does its own startup work (loading the transcript, plugins, hooks, MCP servers, the file index).
3. When the deadline passes, every capability that has no answer yet gets its default. For program status the default is "no".
4. It does not ask again. An answer that arrives after the deadline is ignored.

A session that settled on "no" logs:

```
Terminal capabilities ... programStatus=no (not asked yet, no answer); terminal said: CSI ? u flags=5
```

A healthy one logs:

```
Terminal capabilities ... programStatus=yes (probe: OSC 7501 reply); terminal said: CSI ? u flags=5
```

Note the second half of the failing line: the terminal's answer to another question of the same batch is there. The terminal did answer. Claude Code read the answers too late.

The 2 second figure and the missing second probe were read from the shipped client of those two versions. They are not documented behavior and can change in any release.

## Why it happens after a reboot

The terminal is not the slow side. A small program that sends `OSC 7501 ; ?` twice a second from inside a terminal of the same core ([`tools/osc7501-pinger.py`](../tools/osc7501-pinger.py)) got every answer within 0.15 s, even at the worst moment of a 12 session start.

The slow side is the agent. After a reboot all recovered shells reach their prompt together and all agents start in the same seconds. Each one indexes its folder, starts its MCP servers and runs its hooks. When the process does not get enough CPU time to read its input within the deadline, the probe is lost.

Measured facts that support this:

- With 30 agents starting together, single agents took 5 to 20 s to come up.
- The misses line up with short bursts of CPU contention, not with the size of the transcript. Over five runs the same session was sometimes fine and sometimes missed.
- A 50 ms busy loop ([`tools/contention.py`](../tools/contention.py)) took 1.0x its CPU time on the idle machine and 5x to 20x in the seconds around a miss.
- `CLAUDE_CODE_DISABLE_TERMINAL_TITLE=1` produces exactly the same symptom on purpose (no status reports at all). That is useful as a test switch, see [reproduce](reproduce.md).

## What does not fix it

These were tried and measured in simulated reboots with 12 sessions on a 14 core laptop. See [observed results](observed-results.md).

| Attempt | Result |
|---|---|
| Nothing (all agents start together) | 9 of 14 without status on the real reboot |
| Starts 2 s apart | 2 of 12 without status, in two runs out of two |
| One start at a time, the next waits for the previous agent's status | 0 of 12 on a calm run, but 4 of 13 starts missed under heavy load, one session twice in a row |

Spacing the starts lowers the odds. It cannot remove the cause, because the agents that already started keep using the CPU in bursts long after they report their first status.

The first explanation written down for this problem was "starts 2 s apart are enough". It was wrong, and it was only caught because the reboot was reproduced and counted instead of assumed. If you take one thing from this page: reproduce before you call a timing problem fixed.

## What was done instead

The defect is inside the agent, so the only complete fix is upstream: accept a late answer, or ask again later. Until then the damage is detected and repaired automatically:

1. Starts take turns, to keep the number of misses low.
2. Each resumed Claude Code tab is watched. A tab that sits at its idle prompt with no status has missed its probe.
3. That tab is restarted with the same session once the machine is quiet. A restart during the load peak would only miss again.
4. At most 2 restarts per tab per hour. After that the tool gives up and says so in its log.
5. A tab that is busy, shows a dialog or is being typed in is never touched.

Details and the knobs: [resume after a reboot](resume-after-reboot.md).

## Repair by hand

A session that never got its status needs a restart of the agent process. Nothing else brings the status back.

- In the tab: quit the agent and resume the same session (`/exit`, then `claude --resume <id>` or your account launcher with `--resume <id>`).
- From outside, on a machine with the resume tool installed: `kill -9 <pid>` where `<pid>` is the terminal's program from `hc get <terminal> --json` (the tab's shell, not the agent). The core recovers the terminal as a fresh shell and the resume tool brings the same session back. Do not use `exit` in that shell or `hc kill`: both end the terminal and the tab is gone.

Before restarting a tab from outside, look at its screen (`hc read <terminal> --lines 0`): an empty input box, no "esc to interrupt", no dialog. With `status: null` the screen is the only way to know the agent is idle.

## Not covered

- A fresh session (not a resumed one) can miss its probe too when it starts on a loaded machine. The automatic repair only watches tabs it resumed.
- Machines without the resume tool. One long running session on another machine showed the same `status: null` outside any reboot.
- Codex and Grok were not seen with this problem. The watcher only restarts Claude Code.
