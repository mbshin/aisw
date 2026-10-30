# Shared by statusline.sh, on-limit.sh and clsw. Sourced, not run.
# State lives in ~/.clsw (CLSW_STATE overrides it, for tests).

STATE=${CLSW_STATE:-$HOME/.clsw}
ACCOUNTS="a b c"
FIVE_FULL=95   # an account is used up at 5h >= 95% ...
SEVEN_FULL=98  # ... or 7d >= 98%
WARN=80        # status line shows ⚠
NOTIFY_AT=90   # macOS notification, once per 5h window
GUESS_SECONDS=18000  # limit hit with no reset time known: assume 5 hours

mkdir -p "$STATE"

# Which account this process runs as: a, b, c, or default (plain `claude`).
account_name() {
  local d=${CLAUDE_CONFIG_DIR:-}
  d=${d%/}
  case ${d##*/} in
    .claude-a) echo a ;;
    .claude-b) echo b ;;
    .claude-c) echo c ;;
    *) echo default ;;
  esac
}

now() { date +%s; }

hhmm() { date -r "$1" '+%a %H:%M' 2>/dev/null || date -d "@$1" '+%a %H:%M'; }

notify() {
  [ "${CLSW_QUIET:-}" = 1 ] && return 0
  osascript -e "display notification \"$1\" with title \"Claude\"" >/dev/null 2>&1 || true
}

# Prints the epoch until which the account is used up; nothing if it is free.
blocked_until() {
  local acct=$1 t=$(now) until=0 f5 r5 f7 r7
  if [ -f "$STATE/$acct.limit" ]; then
    until=$(cat "$STATE/$acct.limit")
  fi
  if [ -f "$STATE/$acct.usage.json" ]; then
    read -r f5 r5 f7 r7 < <(jq -r '[.five_hour.used_percentage // 0, .five_hour.resets_at // 0,
      .seven_day.used_percentage // 0, .seven_day.resets_at // 0] | map(floor) | @tsv' "$STATE/$acct.usage.json")
    if [ "$f5" -ge "$FIVE_FULL" ] && [ "$r5" -gt "$until" ]; then until=$r5; fi
    if [ "$f7" -ge "$SEVEN_FULL" ] && [ "$r7" -gt "$until" ]; then until=$r7; fi
  fi
  if [ "$until" -gt "$t" ]; then echo "$until"; fi
}

# First account that is not used up, in order a, b, c.
pick_account() {
  local acct
  for acct in $ACCOUNTS; do
    if [ -z "$(blocked_until "$acct")" ]; then echo "$acct"; return 0; fi
  done
  return 1
}
