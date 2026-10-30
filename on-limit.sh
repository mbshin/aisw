#!/usr/bin/env bash
# StopFailure hook (matcher rate_limit): mark this account used up and leave a handoff for aisw.
# The hook's output and exit code are ignored by Claude Code, so this only writes files and notifies.
. "$(dirname "$0")/common.sh"

acct=$(account_name)
input=$(cat)
t=$(now)

until=$(blocked_until "$acct")
if [ -z "$until" ]; then
  # No usage numbers past the limit: take the 5h reset if we know it, else guess.
  until=$(jq -r '.five_hour.resets_at // 0 | floor' "$STATE/$acct.usage.json" 2>/dev/null || echo 0)
  if [ "${until:-0}" -le "$t" ]; then until=$((t + GUESS_SECONDS)); fi
fi
echo "$until" > "$STATE/$acct.limit"

case $acct in
  a|b|c)
    jq -n --arg from "$acct" --argjson at "$t" --argjson input "$input" \
      '{from: $from, at: $at, session_id: $input.session_id, cwd: $input.cwd}' > "$STATE/handoff.json"
    label=$(tr '[:lower:]' '[:upper:]' <<<"$acct")
    notify "Account $label hit its limit (resets $(hhmm "$until")). Type /exit to go on in the next account."
    ;;
  *)
    notify "Claude hit its usage limit (resets $(hhmm "$until"))."
    ;;
esac
exit 0
