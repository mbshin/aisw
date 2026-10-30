# Codex and Antigravity as fallbacks when every Claude account is used up (opt-in: aisw setup --codex,
# aisw setup --agy). Sourced by aisw, not run. Neither can read Claude's session files, so each gets a
# handoff note: task, recent requests, where Claude stopped, and the git state.

CODEX_BIN=${AISW_CODEX:-codex}
AGY_BIN=${AISW_AGY:-agy}

# Enabled fallbacks in the order they're offered, one per line of $STATE/fallback.
fallbacks() { cat "$STATE/fallback" 2>/dev/null; }
fallback_enabled() { fallbacks | grep -qx "$1"; }
codex_enabled() { fallback_enabled codex; }
fallback_add() { fallback_enabled "$1" || echo "$1" >> "$STATE/fallback"; }
fallback_remove() {
  local rest
  rest=$(fallbacks | grep -vx "$1")
  if [ -n "$rest" ]; then echo "$rest" > "$STATE/fallback"; else rm -f "$STATE/fallback"; fi
}

# Tools: codex (= codex1, ~/.codex), codex2… (~/.codex-2, via CODEX_HOME), agy.
is_tool() { case $1 in codex|codex[1-9]|agy) return 0 ;; *) return 1 ;; esac; }
tool_base() { echo "${1%%[0-9]*}"; }
tool_slot() { local n=${1#"$(tool_base "$1")"}; echo "${n:-1}"; }
tool_label() {
  local name
  case $(tool_base "$1") in codex) name=Codex ;; agy) name=Antigravity ;; esac
  if [ "$(tool_slot "$1")" = 1 ]; then echo "$name"; else echo "$name $(tool_slot "$1")"; fi
}
tool_bin() { case $(tool_base "$1") in codex) echo "$CODEX_BIN" ;; agy) echo "$AGY_BIN" ;; esac; }
tool_install() {
  case $(tool_base "$1") in codex) echo "brew install --cask codex" ;; agy) echo "brew install --cask antigravity-cli" ;; esac
}
# with_tool <tool> <cmd...>: run cmd with that slot's login folder (Codex slot 2+ = CODEX_HOME=~/.codex-<n>).
with_tool() {
  local t=$1 n
  shift
  n=$(tool_slot "$t")
  if [ "$(tool_base "$t")" = codex ] && [ "$n" != 1 ]; then
    mkdir -p "$HOME/.codex-$n"
    CODEX_HOME=$HOME/.codex-$n "$@"
  else
    "$@"
  fi
}
tool_missing() {
  command -v "$(tool_bin "$1")" >/dev/null && return 1
  echo "$(tool_label "$1") not found: $(tool_install "$1")" >&2
}

# Session file of a session id, or the newest session of a folder.
session_file() { ls "$HOME"/.claude/projects/*/"$1".jsonl 2>/dev/null | head -1; }
newest_session_in() { ls -t "$HOME/.claude/projects/$(tr '/.' '--' <<<"$1")"/*.jsonl 2>/dev/null | head -1; }

USER_TEXT='select(.type == "user" and (.isMeta | not)) | .message.content
  | if type == "string" then . else (map(select(.type == "text").text) | first // empty) end
  | select(startswith("<") | not)'
ASSISTANT_TEXT='select(.type == "assistant") | .message.content
  | if type == "string" then . else (map(select(.type == "text").text) | join("\n")) end
  | select(length > 0)'

# write_note <session file> <folder> <note path>
write_note() {
  local f=$1 dir=$2 note=$3
  {
    echo "# Handoff from Claude Code"
    echo
    echo "A Claude Code session in \`$dir\` stopped at its usage limit. Continue the work."
    echo
    echo "## Task (first request)"
    echo
    jq -r "$USER_TEXT" "$f" | head -c 3000 | awk 'NR == 1 || !/^$/' | head -40
    echo
    echo "## Recent requests (oldest first)"
    echo
    jq -r "$USER_TEXT | gsub(\"\\\\s+\"; \" \") | .[0:400]" "$f" | tail -5 | sed 's/^/- /'
    echo
    echo "## Where Claude stopped (its last message)"
    echo
    jq -r "$ASSISTANT_TEXT" "$f" | tail -c 2000
    echo
    if git -C "$dir" rev-parse --git-dir >/dev/null 2>&1; then
      echo "## Repo state"
      echo
      echo '```'
      git -C "$dir" status --short | head -50
      git -C "$dir" diff --stat | tail -20
      echo '```'
    fi
  } > "$note"
}

# go_tool <codex|agy> <session file or empty> <folder>: hand over and run the tool interactively.
go_tool() {
  local tool=$1 f=$2 dir=$3 bin note prompt code
  bin=$(tool_bin "$tool")
  tool_missing "$tool" && return 1
  cd "$dir" || return 1
  if [ -z "$f" ]; then
    with_tool "$tool" "$bin"
    return
  fi
  note=$(mktemp "${TMPDIR:-/tmp}/aisw-handoff.XXXXXX")
  write_note "$f" "$dir" "$note"
  prompt="A Claude Code session hit its usage limit. Read $note for the task and progress, \
check git status and git diff, then continue. Ask before anything destructive."
  echo "Going on in $(tool_label "$tool") (handoff note: $note)."
  case $(tool_base "$tool") in
    codex) with_tool "$tool" "$bin" "$prompt" ;;
    agy) "$bin" -i "$prompt" ;; # -i: first prompt, then stay interactive
  esac
  code=$?
  rm -f "$note"
  return $code
}

# When every Claude account is used up: one menu with the fallbacks, each Claude account "anyway"
# (a limit mark can be a guess), or stop. Prints the pick (codex, agy, a, b, c); nothing = stop.
# Accepts the number, the name, or y (= the first fallback).
choose_when_used_up() {
  local opts=() o i ans
  for o in $(fallbacks); do opts+=("$o"); done
  for o in $ACCOUNTS; do opts+=("$o"); done
  echo "Continue with:" >&2
  for i in "${!opts[@]}"; do
    o=${opts[$i]}
    case $o in
      a|b|c) printf '  %d) Claude %s anyway\n' $((i + 1)) "$(upper "$o")" >&2 ;;
      *) printf '  %d) %s\n' $((i + 1)) "$(tool_label "$o")" >&2 ;;
    esac
  done
  printf '  0) Stop (default)\nChoice: ' >&2
  read -r ans || ans=
  ans=$(tr '[:upper:]' '[:lower:]' <<<"$ans")
  case $ans in
    ""|0|n|no|stop) return 1 ;;
    y|yes) o=$(fallbacks | head -1) ;;
    antigravity) o=agy ;;
    *[!0-9]*) o=$ans ;;
    *) o=${opts[$((ans - 1))]:-} ;;
  esac
  for i in "${opts[@]}"; do [ -n "$o" ] && [ "$i" = "$o" ] && { echo "$o"; return 0; }; done
  return 1
}

# Antigravity has no status command; `agy models` fails with "Please sign in" when logged out.
agy_status() {
  command -v "$AGY_BIN" >/dev/null || { echo "not installed"; return; }
  if "$AGY_BIN" models >/dev/null 2>&1; then echo "Logged in"; else echo "Not logged in"; fi
}

fallback_logged_in() {
  case $(tool_base "$1") in
    codex) with_tool "$1" "$CODEX_BIN" login status 2>&1 | grep -qi "^logged in" ;;
    agy) [ "$(agy_status)" = "Logged in" ] ;;
  esac
}

fallback_who() {
  local tool
  for tool in $(fallbacks); do
    case $(tool_base "$tool") in
      codex) echo "$(tool_label "$tool") (fallback): $(with_tool "$tool" "$CODEX_BIN" login status 2>&1 | head -1)" ;;
      agy) echo "$(tool_label "$tool") (fallback): $(agy_status)" ;;
    esac
  done
}

# Device-code sign-in (link + one-time code), the link opened in the same empty browser window as
# Claude logins. If ChatGPT blocks device codes for the account, falls back to the normal browser login.
# Default: Codex's own browser login (works for every account). `aisw login codex --device` uses the
# one-time code instead (needs ChatGPT Settings → Security → device code sign-in).
codex_login() {
  local tool=${1:-codex}
  tool_missing "$tool" && return 1
  if [ "${2:-}" = --device ]; then
    codex_device_login "$tool"
    return
  fi
  echo "== $(tool_label "$tool"): sign in with your ChatGPT account in the browser"
  with_tool "$tool" "$CODEX_BIN" login
}

codex_device_login() {
  local tool=${1:-codex} out pid url code rc i blocked
  tool_missing "$tool" && return 1
  out=$(mktemp "${TMPDIR:-/tmp}/aisw-codex-login.XXXXXX")
  with_tool "$tool" "$CODEX_BIN" login --device-auth > "$out" 2>&1 &
  pid=$!
  for i in $(seq 1 100); do # up to ~20 s for the link and the code
    url=$(tr -d '\033' < "$out" | grep -oE 'https://[A-Za-z0-9./_-]+' | head -1)
    code=$(tr -d '\033' < "$out" | grep -oE '[A-Z0-9]{4}-[A-Z0-9]{4,6}' | head -1)
    [ -n "$url" ] && [ -n "$code" ] && break
    kill -0 "$pid" 2>/dev/null || break
    sleep 0.2
  done
  if [ -n "$url" ] && [ -n "$code" ]; then
    echo "== $(tool_label "$tool"): sign in with your ChatGPT account in the new browser window"
    echo "   One-time code: $code   (expires in 15 minutes)"
    echo "   If the page says device code sign-in is off, press Ctrl+C: aisw switches to the browser login."
    "$BROWSER" "$url"
    # The "device code sign-in is off" message shows on the web page, not here, so Ctrl+C is the way out.
    blocked=
    trap 'blocked=1; kill "$pid" 2>/dev/null' INT
    wait "$pid"
    rc=$?
    trap - INT
    close_signin_browser
    if [ -n "$blocked" ]; then
      wait "$pid" 2>/dev/null
      echo
      echo "device code sign-in" >> "$out" # take the fallback below
      rc=1
    fi
  else
    kill "$pid" 2>/dev/null
    wait "$pid" 2>/dev/null
    rc=1
  fi
  if [ "$rc" -ne 0 ] && grep -qi "device code sign-in" "$out"; then
    rm -f "$out"
    codex_device_blocked_hint
    echo "== Falling back to the normal Codex login (your regular browser; sign in with the right account)"
    with_tool "$tool" "$CODEX_BIN" login
    return
  fi
  [ "$rc" -eq 0 ] || cat "$out" >&2
  rm -f "$out"
  return $rc
}

codex_device_blocked_hint() {
  cat <<'EOF2'
ChatGPT blocks device-code sign-in for this account. To use it next time:
  chatgpt.com → profile → Settings → Security → turn on device code sign-in
  (same account you sign in with; on a Business/Enterprise workspace only the admin can turn it on)
EOF2
}

# aisw login agy: Antigravity signs in on its first start (no login command). Start it, watch for the
# sign-in in the background, and quit it as soon as it's done, so nobody has to press Ctrl+C.
agy_login() {
  local parent=$$ watcher
  tool_missing agy && return 1
  if [ "$(agy_status)" = "Logged in" ]; then
    echo "Antigravity: already signed in."
    return 0
  fi
  echo "== Antigravity: sign in with your Google account in the browser window it opens."
  echo "   It closes by itself once you're signed in."
  (
    while sleep 2; do
      if [ "$(agy_status)" = "Logged in" ]; then
        sleep 1
        # Like Ctrl+C; TERM if it's still running a moment later.
        for p in $(pgrep -P "$parent"); do [ "$p" != "$BASHPID" ] && kill -INT "$p" 2>/dev/null; done
        sleep 2
        for p in $(pgrep -P "$parent"); do [ "$p" != "$BASHPID" ] && kill -TERM "$p" 2>/dev/null; done
        break
      fi
    done
  ) &
  watcher=$!
  "$AGY_BIN"
  kill "$watcher" 2>/dev/null
  wait "$watcher" 2>/dev/null
  stty sane 2>/dev/null
  echo
  close_signin_browser
  echo "Antigravity: $(agy_status)"
}
