#!/usr/bin/env python3
"""Ask the terminal `OSC 7501 ; ?` repeatedly and log how long each reply takes.

Run it INSIDE a terminal of the multiplexer (it talks to its own terminal). It shows
whether the terminal side is slow to answer the status probe. In our runs it never was:
the slow side was the agent reading the answer.

  osc7501-pinger.py <output file> <seconds>
"""
import os
import select
import sys
import termios
import time
import tty

if len(sys.argv) != 3:
    sys.exit(__doc__.strip())
out, seconds = sys.argv[1], float(sys.argv[2])
fd = sys.stdin.fileno()
old = termios.tcgetattr(fd)
tty.setraw(fd)
try:
    end = time.time() + seconds
    with open(out, "a", encoding="utf-8") as log:
        while time.time() < end:
            t0 = time.time()
            os.write(sys.stdout.fileno(), b"\x1b]7501;?\x1b\\")
            buf = b""
            while time.time() - t0 < 6:
                ready, _, _ = select.select([fd], [], [], 0.05)
                if ready:
                    buf += os.read(fd, 4096)
                    if b"\x1b]7501;" in buf and (b"\x07" in buf or b"\x1b\\" in buf):
                        break
            ok = b"\x1b]7501;" in buf
            log.write(f"{time.strftime('%H:%M:%S')} {'reply' if ok else 'NOREPLY'} {(time.time() - t0) * 1000:.0f}ms\n")
            log.flush()
            time.sleep(0.5)
finally:
    termios.tcsetattr(fd, termios.TCSADRAIN, old)
