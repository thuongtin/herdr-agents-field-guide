#!/bin/zsh
# Sample which commands use the CPU, every 4 s, grouped by the first words of the
# command line. Shows what loads the machine while many agents start.
#
#   cpu-sample.sh <output file> [samples, default 30]
# The output holds command lines of everything running: private, do not publish it.
out=${1:?usage: cpu-sample.sh <output file> [samples]}; n=${2:-30}; : > "$out"
for i in $(seq 1 "$n"); do
  echo "== $(date +%H:%M:%S) load=$(uptime | sed 's/.*load averages*: *//')" >> "$out"
  ps -Ao pcpu=,args= | awk '$1>3 {cmd=$2; for(i=3;i<=NF && i<=7;i++) cmd=cmd" "$i; c[cmd]+=$1} END{for(k in c) printf "%7.0f %s\n", c[k], substr(k,1,150)}' | sort -rn | head -14 >> "$out"
  sleep 4
done
