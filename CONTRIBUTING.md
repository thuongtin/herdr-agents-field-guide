# Contributing

This is a field guide built on observation. A correction, a result from another version or platform, or a failed reproduction is as welcome as a fix.

## Local checks

From the repository root, Python 3.9 or newer:

```sh
python3 -m unittest discover -s tests -v
git diff --check
```

The tests do not need `hc`, an agent or a network. CI runs the same checks on Linux.

## Adding or changing a result

1. Say what was run: versions, machine class, how many sessions, how many runs.
2. Keep failed attempts and untested cases in the text. A later success does not delete an earlier failure unless the same path was run again.
3. Separate what you observed from what you concluded. "The tab had no status" is an observation. "The deadline is 2 s" is a conclusion and needs its source.
4. A simulated reboot is not a reboot. A forced miss tests the repair, not the cause. Label them.
5. Describe an agent's behavior from the outside (its debug log, its screen, its process). Do not paste code or internal names taken from a shipped client.

## Changing the tool

- `bin/hc-claude-resume` stays one file with the standard library only. It runs inside agent hooks on every prompt, so it must be quick and must never fail loudly.
- When in doubt, do less: not resuming, or not restarting, is the safe side. Never fall back to another account. Never touch a tab that is busy, shows a dialog or has a draft.
- Anything that kills a process needs a test in a separate core first, see [reproduce](docs/reproduce.md).
- Add a unit test for logic that can be tested without `hc`.

## Public-data hygiene

Use placeholders and example labels. Do not commit logs, transcripts, session ids, account labels, host names, home folder paths or anything with a credential. See [privacy](docs/privacy.md). The tests catch some patterns; they do not replace reading the diff before you push.
