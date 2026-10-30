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

tool_label() { case $1 in codex) echo Codex ;; agy) echo Antigravity ;; esac; }
tool_bin() { case $1 in codex) echo "$CODEX_BIN" ;; agy) echo "$AGY_BIN" ;; esac; }
tool_install() { case $1 in codex) echo "brew install --cask codex" ;; agy) echo "brew install --cask antigravity-cli" ;; esac; }
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
    "$bin"
    return
  fi
  note=$(mktemp "${TMPDIR:-/tmp}/aisw-handoff.XXXXXX")
  write_note "$f" "$dir" "$note"
  prompt="A Claude Code session hit its usage limit. Read $note for the task and progress, \
check git status and git diff, then continue. Ask before anything destructive."
  echo "Going on in $(tool_label "$tool") (handoff note: $note)."
  case $tool in
    codex) "$bin" "$prompt" ;;
    agy) "$bin" -i "$prompt" ;; # -i: first prompt, then stay interactive
  esac
  code=$?
  rm -f "$note"
  return $code
}

# offer_fallback <session file or empty> <folder>: when every Claude account is used up, ask for each
# enabled fallback in order; the first yes takes over.
offer_fallback() {
  local tool ans
  for tool in $(fallbacks); do
    printf 'All Claude accounts are used up. Continue in %s? [y/N] ' "$(tool_label "$tool")" >&2
    read -r ans || ans=
    case $ans in [yY]*) go_tool "$tool" "$1" "$2"; return ;; esac
  done
  return 1
}

# Antigravity has no status command; `agy models` fails with "Please sign in" when logged out.
agy_status() {
  command -v "$AGY_BIN" >/dev/null || { echo "not installed"; return; }
  if "$AGY_BIN" models >/dev/null 2>&1; then echo "Logged in"; else echo "Not logged in"; fi
}

fallback_who() {
  local tool
  for tool in $(fallbacks); do
    case $tool in
      codex) echo "Codex (fallback): $("$CODEX_BIN" login status 2>&1 | head -1)" ;;
      agy) echo "Antigravity (fallback): $(agy_status)" ;;
    esac
  done
}

# aisw login codex: device-code sign-in (link + one-time code), the link opened in the same empty
# browser window as Claude logins, so the browser's current ChatGPT login is not reused.
# If ChatGPT blocks device codes for the account, falls back to the normal browser login.
codex_login() {
  local out pid url code rc i
  tool_missing codex && return 1
  out=$(mktemp "${TMPDIR:-/tmp}/aisw-codex-login.XXXXXX")
  "$CODEX_BIN" login --device-auth > "$out" 2>&1 &
  pid=$!
  for i in $(seq 1 100); do # up to ~20 s for the link and the code
    url=$(tr -d '\033' < "$out" | grep -oE 'https://[A-Za-z0-9./_-]+' | head -1)
    code=$(tr -d '\033' < "$out" | grep -oE '[A-Z0-9]{4}-[A-Z0-9]{4,6}' | head -1)
    [ -n "$url" ] && [ -n "$code" ] && break
    kill -0 "$pid" 2>/dev/null || break
    sleep 0.2
  done
  if [ -n "$url" ] && [ -n "$code" ]; then
    echo "== Codex: sign in with your ChatGPT account in the new browser window"
    echo "   One-time code: $code   (expires in 15 minutes)"
    "$BROWSER" "$url"
    wait "$pid"
    rc=$?
    close_signin_browser
  else
    kill "$pid" 2>/dev/null
    wait "$pid" 2>/dev/null
    rc=1
  fi
  if [ "$rc" -ne 0 ] && grep -qi "device code sign-in" "$out"; then
    rm -f "$out"
    codex_device_blocked_hint
    echo "== Falling back to the normal Codex login (your regular browser; sign in with the right account)"
    "$CODEX_BIN" login
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

# aisw login agy: Antigravity signs in on its first start. Run it once; quit it after the sign-in.
agy_login() {
  tool_missing agy && return 1
  echo "== Antigravity: sign in with your Google account in the browser window it opens."
  echo "   When its prompt appears, quit it (Ctrl+C) to come back here."
  "$AGY_BIN"
  close_signin_browser
  echo "Antigravity: $(agy_status)"
}
