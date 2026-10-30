#!/usr/bin/env bash
# StopFailure hook (matcher rate_limit): mark this account used up and say which account is free next.
# The hook's output and exit code are ignored by Claude Code, so this only writes files and notifies.
. "$(dirname "$0")/common.sh"

acct=$(account_name)
cat >/dev/null  # the hook input isn't needed
t=$(now)

until=$(blocked_until "$acct")
if [ -z "$until" ]; then
  # No usage numbers past the limit: take the 5h reset if we know it, else guess.
  until=$(jq -r '.five_hour.resets_at // 0 | floor' "$STATE/$acct.usage.json" 2>/dev/null || echo 0)
  if [ "${until:-0}" -le "$t" ]; then until=$((t + GUESS_SECONDS)); fi
fi
echo "$until" > "$STATE/$acct.limit"

label=$acct
[ "$acct" = default ] && label=main
if next=$(next_free_claude "$acct"); then
  notify "Account $label hit its limit (resets $(hhmm "$until")). Next free: $next → /exit, aisw activate $next, aisw --continue"
else
  notify "Account $label hit its limit (resets $(hhmm "$until")). No other Claude account is free: aisw list"
fi
exit 0
