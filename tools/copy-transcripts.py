#!/usr/bin/env python3
"""Make throwaway copies of Claude Code transcripts for the probe runs.

A resumed session appends to its transcript, so the tests never resume a real session:
each given transcript is copied under a new session id in the same project folder.

  copy-transcripts.py <transcript.jsonl> [more.jsonl ...]   make copies
  copy-transcripts.py --clean                               delete the copies again

The new ids go to $PROBE_BASE/copies.txt (default $TMPDIR/hc-probe/copies.txt), one per
line; copies-paths.txt beside it lists the files, and --clean deletes exactly those.
The copies are private data like the originals: never publish or commit them.
"""
import os
import sys
import uuid

BASE = os.environ.get("PROBE_BASE") or os.path.join(os.environ.get("TMPDIR") or "/tmp", "hc-probe")
IDS = os.path.join(BASE, "copies.txt")
PATHS = os.path.join(BASE, "copies-paths.txt")


def clean():
    try:
        paths = open(PATHS, encoding="utf-8").read().split("\n")
    except FileNotFoundError:
        paths = []
    for path in filter(None, paths):
        try:
            os.remove(path)
            print("removed", os.path.basename(path))
        except FileNotFoundError:
            pass
    for path in (IDS, PATHS):
        try:
            os.remove(path)
        except FileNotFoundError:
            pass


def copy(sources):
    os.makedirs(BASE, exist_ok=True)
    for src in sources:
        old = os.path.basename(src)[: -len(".jsonl")]
        if not src.endswith(".jsonl") or not os.path.isfile(src):
            sys.exit(f"not a transcript: {src}")
        new = str(uuid.uuid4())
        dst = os.path.join(os.path.dirname(os.path.abspath(src)), new + ".jsonl")
        with open(src, "rb") as fin, open(dst, "xb") as fout:
            for line in fin:
                fout.write(line.replace(old.encode(), new.encode()))
        with open(IDS, "a", encoding="utf-8") as fh:
            fh.write(new + "\n")
        with open(PATHS, "a", encoding="utf-8") as fh:
            fh.write(dst + "\n")
        print(new)


if __name__ == "__main__":
    args = sys.argv[1:]
    if args == ["--clean"]:
        clean()
    elif args and not args[0].startswith("-"):
        copy(args)
    else:
        sys.exit(__doc__.strip())
