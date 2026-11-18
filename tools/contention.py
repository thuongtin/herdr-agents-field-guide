#!/usr/bin/env python3
"""Log how contended the CPU is, once per second.

The number is wall time over CPU time of a 50 ms busy loop: 1.0 when the loop gets a
core to itself, more when programs queue for the CPU. This is the same measure the
resume tool uses before it restarts an agent (`cpu_contention` in bin/hc-claude-resume).
Load average reacts too slowly to show the bursts that make an agent miss a 2 s deadline.

  contention.py <output file> <seconds>
"""
import os
import sys
import time


def cpu_contention(cpu_s=0.05):
    t0, c0 = time.perf_counter(), time.process_time()
    while time.process_time() - c0 < cpu_s:
        pass
    return (time.perf_counter() - t0) / max(time.process_time() - c0, 1e-3)


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__.strip())
    out, seconds = sys.argv[1], float(sys.argv[2])
    end = time.time() + seconds
    with open(out, "a", encoding="utf-8") as fh:
        while time.time() < end:
            fh.write("%s %.2f load=%.0f\n" % (time.strftime("%H:%M:%S"), cpu_contention(), os.getloadavg()[0]))
            fh.flush()
            time.sleep(1)
