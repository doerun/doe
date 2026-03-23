#!/usr/bin/env bash
# prune-bench-out.sh — keep only the latest N timestamped runs per bench/out/ lane.
# Usage: ./scripts/prune-bench-out.sh [keep_count]
# Default: keep 3 latest runs per lane.

set -euo pipefail

KEEP=${1:-3}
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

# Find all parent directories containing timestamped run subdirectories
git ls-files bench/out/ | \
  grep -oP 'bench/out/.+?/\d{8}T\d{6}Z/' | \
  sed 's|/$||' | sort -u | \
  awk -F'/' -v keep="$KEEP" '{
    ts = $NF
    parent = ""
    for (i=1; i<NF; i++) parent = parent (i>1?"/":"") $i
    runs[parent] = runs[parent] " " ts
  }
  END {
    for (p in runs) {
      n = split(runs[p], arr, " ")
      for (i=1; i<=n; i++) for (j=i+1; j<=n; j++) if (arr[i] > arr[j]) { t=arr[i]; arr[i]=arr[j]; arr[j]=t }
      keep_start = n - keep + 1
      if (keep_start < 1) keep_start = 1
      for (i=1; i<keep_start; i++) {
        if (arr[i] != "") print p "/" arr[i]
      }
    }
  }' | while IFS= read -r dir; do
    count=$(git ls-files "$dir/" 2>/dev/null | wc -l)
    if [ "$count" -gt 0 ]; then
      git rm -r --cached --quiet "$dir/" 2>/dev/null
      echo "pruned: $dir/ ($count files)"
    fi
  done

remaining=$(git ls-files bench/out/ | wc -l)
echo ""
echo "bench/out/ now tracks $remaining files (kept latest $KEEP runs per lane)"
