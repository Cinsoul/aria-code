#!/usr/bin/env bash
# Usage: annotate-failure.sh TITLE LOG [LINES]
#
# Repeat the end of a failed step's log as error annotations. Annotations are
# readable through the public checks API, job logs only when signed in, so
# this is what lets anyone see why a run failed. GitHub keeps 4 KiB of each
# annotation and ten per step: the log's failure summary lines go first, then
# its tail, split into up to eight annotations.
set -u
title=$1 log=$2 lines=${3:-80}
[ -s "$log" ] || exit 0
encode() { cut -c1-300 | sed -e 's/%/%25/g' -e 's/\r//g' | awk '{printf "%s%%0A", $0}'; }
summary=$(grep -E '^(FAILED|ERROR) ' "$log" | head -n 40)
[ -n "$summary" ] && echo "::error title=${title} summary::$(printf '%s\n' "$summary" | encode)"
part=1
tail -n "$lines" "$log" | split -l 30 - "${log}.part."
for chunk in "${log}".part.*; do
  [ "$part" -le 8 ] || break
  echo "::error title=${title} (${part})::$(encode < "$chunk")"
  part=$((part + 1))
done
rm -f "${log}".part.*
