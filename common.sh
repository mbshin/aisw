# Shared by aisw, statusline.sh and on-limit.sh. Sourced, not run.
# State lives in ~/.aisw (AISW_STATE overrides it, for tests).

STATE=${AISW_STATE:-$HOME/.aisw}
# Renamed from clsw (1.1.0): keep the old state.
if [ -z "${AISW_STATE:-}" ] && [ -d "$HOME/.clsw" ] && [ ! -e "$STATE" ]; then mv "$HOME/.clsw" "$STATE"; fi
ACCOUNTS_FILE=$STATE/accounts  # one account per line: <name> <tool> <folder>; line order = list order
TOOLS="claude codex agy"
FIVE_FULL=95   # an account is used up at 5h >= 95% ...
SEVEN_FULL=98  # ... or 7d >= 98%
WARN=80        # status line shows ⚠
NOTIFY_AT=90   # macOS notification, once per 5h window
GUESS_SECONDS=18000  # limit hit with no reset time known: assume 5 hours

mkdir -p "$STATE"

# 1.x had fixed Claude accounts a, b, c (~/.claude-<x>) plus Codex/Antigravity fallbacks.
# The first 2.x run turns them into named accounts, keeping every folder and login where it is.
migrate_accounts() {
  local x n letter lines=() used=" "
  [ -f "$ACCOUNTS_FILE" ] && return 0
  for x in a b c; do
    if [ -d "$HOME/.claude-$x" ]; then lines+=("$x claude $HOME/.claude-$x"); used+="$x "; fi
  done
  take() {
    for letter in {a..z}; do
      case $used in *" $letter "*) ;; *) lines+=("$letter $1 $2"); used+="$letter "; return ;; esac
    done
  }
  if [ -f "$HOME/.codex/auth.json" ] || grep -qx codex "$STATE/fallback" 2>/dev/null; then take codex "$HOME/.codex"; fi
  for n in 2 3 4 5 6 7 8 9; do
    if [ -f "$HOME/.codex-$n/auth.json" ]; then take codex "$HOME/.codex-$n"; fi
  done
  if grep -qx agy "$STATE/fallback" 2>/dev/null; then take agy "$HOME/.gemini/antigravity-cli"; fi
  unset -f take
  [ ${#lines[@]} -gt 0 ] || return 0
  printf '%s\n' "${lines[@]}" > "$ACCOUNTS_FILE"
  rm -f "$STATE/fallback" "$STATE/handoff.json"
}
migrate_accounts

names() { awk '{print $1}' "$ACCOUNTS_FILE" 2>/dev/null; }
has_account() { [ -n "$1" ] && names | grep -qxF -- "$1"; }
tool_of() { awk -v n="$1" '$1 == n {print $2; exit}' "$ACCOUNTS_FILE" 2>/dev/null; }
folder_of() { awk -v n="$1" '$1 == n {sub(/^[^ ]+ [^ ]+ /, ""); print; exit}' "$ACCOUNTS_FILE" 2>/dev/null; }
names_of_tool() { awk -v t="$1" '$2 == t {print $1}' "$ACCOUNTS_FILE" 2>/dev/null; }

# Which account this Claude process runs as, by its CLAUDE_CONFIG_DIR; "default" for plain ~/.claude.
account_name() {
  local d=${CLAUDE_CONFIG_DIR:-} name
  d=${d%/}
  if [ -n "$d" ]; then
    name=$(awk -v d="$d" '$2 == "claude" { f = $0; sub(/^[^ ]+ [^ ]+ /, "", f); sub(/\/$/, "", f)
      if (f == d) { print $1; exit } }' "$ACCOUNTS_FILE" 2>/dev/null)
  fi
  echo "${name:-default}"
}

now() { date +%s; }

hhmm() { date -r "$1" '+%a %H:%M' 2>/dev/null || date -d "@$1" '+%a %H:%M'; }

notify() {
  [ "${AISW_QUIET:-}" = 1 ] && return 0
  osascript -e "display notification \"$1\" with title \"aisw\"" >/dev/null 2>&1 || true
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

# First free Claude account in list order, other than $1.
next_free_claude() {
  local acct
  for acct in $(names_of_tool claude); do
    [ "$acct" = "${1:-}" ] && continue
    if [ -z "$(blocked_until "$acct")" ]; then echo "$acct"; return 0; fi
  done
  return 1
}
