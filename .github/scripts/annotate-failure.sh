#!/usr/bin/env bash
# Usage: annotate-failure.sh TITLE LOG [LINES]
#
# Repeat the end of a failed step's log as one error annotation. Annotations
# are readable through the public checks API, job logs only when signed in, so
# this is what lets anyone see why a run failed.
set -u
title=$1 log=$2 lines=${3:-80}
[ -s "$log" ] || exit 0
message=$(tail -n "$lines" "$log" | cut -c1-300 | sed -e 's/%/%25/g' -e 's/\r//g' | awk '{printf "%s%%0A", $0}')
echo "::error title=${title}::${message}"
