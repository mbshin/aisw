#!/usr/bin/env bash
# Claude Code status line: shows the account and its usage, and records the usage for aisw.
# rate_limits is only sent to Pro/Max subscribers; without it this shows the account only.
. "$(dirname "$0")/common.sh"

acct=$(account_name)
input=$(cat)
label=$acct
[ "$acct" = default ] && label=main  # plain `claude` (~/.claude), not an aisw account

if jq -e '.rate_limits.five_hour or .rate_limits.seven_day' >/dev/null 2>&1 <<<"$input"; then
  jq '.rate_limits | {five_hour, seven_day}' <<<"$input" > "$STATE/$acct.usage.json"
  read -r f5 r5 f7 < <(jq -r '.rate_limits | [.five_hour.used_percentage // 0, .five_hour.resets_at // 0,
    .seven_day.used_percentage // 0] | map(floor) | @tsv' <<<"$input")
  mark=""
  if [ "$f5" -ge "$WARN" ] || [ "$f7" -ge "$WARN" ]; then mark=" ⚠"; fi
  echo "$label · 5h ${f5}% · 7d ${f7}%$mark"

  # One notification per 5h window, remembered by the window's reset time.
  if [ "$f5" -ge "$NOTIFY_AT" ] && [ "$(cat "$STATE/$acct.warned" 2>/dev/null)" != "$r5" ]; then
    echo "$r5" > "$STATE/$acct.warned"
    notify "Account $label at ${f5}% of its 5-hour limit. Good time to commit."
  fi
else
  echo "$label"
fi
