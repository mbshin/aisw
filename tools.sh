# Per-tool sign-in and status for aisw: Claude Code, Codex, Antigravity. Sourced by aisw, not run.
# Never reads login tokens: only each tool's own status commands.

CLAUDE_BIN=${AISW_CLAUDE:-claude}
CODEX_BIN=${AISW_CODEX:-codex}
AGY_BIN=${AISW_AGY:-agy}

tool_label() { case $1 in claude) echo "Claude Code" ;; codex) echo Codex ;; agy) echo Antigravity ;; esac; }
tool_bin() { case $1 in claude) echo "$CLAUDE_BIN" ;; codex) echo "$CODEX_BIN" ;; agy) echo "$AGY_BIN" ;; esac; }
tool_install() {
  case $1 in
    claude) echo "brew install --cask claude-code" ;;
    codex) echo "brew install --cask codex" ;;
    agy) echo "brew install --cask antigravity-cli" ;;
  esac
}
tool_missing() {
  command -v "$(tool_bin "$1")" >/dev/null && return 1
  echo "$(tool_label "$1") not found: $(tool_install "$1")" >&2
}

# in_folder <tool> <folder> <cmd...>: run cmd with that account's login folder.
# Codex's own ~/.codex needs no CODEX_HOME; Antigravity has one login (no per-account folder yet).
in_folder() {
  local tool=$1 dir=$2
  shift 2
  case $tool in
    claude) CLAUDE_CONFIG_DIR=$dir "$@" ;;
    codex) if [ "$dir" = "$HOME/.codex" ]; then env -u CODEX_HOME "$@"; else CODEX_HOME=$dir "$@"; fi ;;
    *) "$@" ;;
  esac
}

# "Email<TAB>Plan<TAB>Org" of a Claude folder, or nothing when logged out.
claude_login() {
  local out org plan
  out=$(CLAUDE_CONFIG_DIR=$1 "$CLAUDE_BIN" auth status --text 2>/dev/null </dev/null)
  grep -q '^Email:' <<<"$out" || return 1
  plan=$(sed -n 's/^Login method: //p' <<<"$out"); plan=${plan#Claude }; plan=${plan% account}
  org=$(sed -n 's/^Organization: //p' <<<"$out")
  case $org in *"'s Organization") org=personal ;; esac
  printf '%s\t%s\t%s\n' "$(sed -n 's/^Email: //p' <<<"$out")" "$plan" "$org"
}

codex_signed_in() { in_folder codex "$1" "$CODEX_BIN" login status 2>&1 </dev/null | grep -qi '^logged in'; }

# Antigravity has no status command; `agy models` fails with "Please sign in" when logged out.
agy_signed_in() { command -v "$AGY_BIN" >/dev/null && "$AGY_BIN" models >/dev/null 2>&1 </dev/null; }

signed_in() {
  case $1 in
    claude) claude_login "$2" >/dev/null ;;
    codex) codex_signed_in "$2" ;;
    agy) agy_signed_in ;;
  esac
}

# Close the Incognito sign-in windows that signin-browser.sh opened, and delete their profiles.
close_signin_browser() {
  pkill -f -- '--user-data-dir=.*aisw-login\.' 2>/dev/null || true
  rm -rf "${TMPDIR:-/tmp}"/aisw-login.*
}

# sign_in <name> <tool> <folder>: the tool's own sign-in only, never its interactive screen.
sign_in() {
  local name=$1 tool=$2 dir=$3 email code
  tool_missing "$tool" && return 1
  case $tool in
    claude)
      email=$(claude_login "$dir" | cut -f1)
      [ -n "$email" ] || email=$(cat "$STATE/$name.email" 2>/dev/null)
      if [ -z "$email" ] && [ -t 0 ]; then read -rp "Email for $name (Enter to skip): " email; fi
      echo "== $name: sign in to Claude${email:+ as $email} in the new Incognito window"
      BROWSER=${AISW_BROWSER:-$(dirname "$0")/signin-browser.sh} \
        CLAUDE_CONFIG_DIR=$dir "$CLAUDE_BIN" auth login ${email:+--email "$email"}
      code=$?
      close_signin_browser
      email=$(claude_login "$dir" | cut -f1)
      if [ -n "$email" ]; then echo "$email" > "$STATE/$name.email"; fi
      [ "$code" -eq 0 ] && [ -n "$email" ]
      ;;
    codex) codex_device_login "$name" "$dir" && codex_signed_in "$dir" ;;
    agy) agy_login ;;
  esac
}

# Codex with a one-time code (`codex login --device-auth`): the code shows here, the link opens in the same
# empty Incognito window as Claude sign-ins. If ChatGPT blocks device codes for the account (the page says
# so; Ctrl+C here) or the code never shows, falls back to Codex's normal browser login.
codex_device_login() {
  local name=$1 dir=$2 out pid url code rc i alive blocked=
  out=$(mktemp "${TMPDIR:-/tmp}/aisw-codex-login.XXXXXX")
  in_folder codex "$dir" "$CODEX_BIN" login --device-auth > "$out" 2>&1 &
  pid=$!
  for i in $(seq 1 100); do # up to ~20 s for the link and the code
    alive=; kill -0 "$pid" 2>/dev/null && alive=1  # checked first, so a quick exit's output is still read
    url=$(tr -d '\033' < "$out" | grep -oE 'https://[A-Za-z0-9./_?=&-]+' | head -1)
    code=$(tr -d '\033' < "$out" | grep -oE '[A-Z0-9]{4}-[A-Z0-9]{4,6}' | head -1)
    [ -n "$url" ] && [ -n "$code" ] && break
    [ -n "$alive" ] || break
    sleep 0.2
  done
  if [ -n "$url" ] && [ -n "$code" ]; then
    echo "== $name: sign in to Codex with your ChatGPT account in the new Incognito window"
    echo "   One-time code: $code   (expires in 15 minutes)"
    echo "   If the page says device code sign-in is off, press Ctrl+C for the normal browser login."
    "${AISW_BROWSER:-$(dirname "$0")/signin-browser.sh}" "$url"
    trap 'blocked=1; kill "$pid" 2>/dev/null' INT
    wait "$pid"
    rc=$?
    trap - INT
    close_signin_browser
    [ -n "$blocked" ] && { wait "$pid" 2>/dev/null; echo; rc=1; }
  else
    kill "$pid" 2>/dev/null
    wait "$pid" 2>/dev/null
    rc=1
    blocked=1
  fi
  if [ "$rc" -ne 0 ] && { [ -n "$blocked" ] || grep -qi "device code" "$out"; }; then
    rm -f "$out"
    cat <<'EOF2'
ChatGPT doesn't allow device-code sign-in for this account. To use it next time:
  chatgpt.com → profile → Settings → Security → turn on device code sign-in
== Falling back to the normal Codex login (your regular browser; sign in with the right account)
EOF2
    in_folder codex "$dir" env -u BROWSER "$CODEX_BIN" login
    return
  fi
  [ "$rc" -eq 0 ] || cat "$out" >&2
  rm -f "$out"
  return "$rc"
}

# Antigravity signs in on its first start (no login command). Start it, watch for the sign-in in the
# background, and quit it as soon as it's done, so nobody has to press Ctrl+C.
agy_login() {
  local parent=$$ watcher
  echo "== Antigravity: sign in with your Google account in the browser window it opens."
  echo "   It closes by itself once you're signed in."
  (
    while sleep 2; do
      if agy_signed_in; then
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
  agy_signed_in
}
