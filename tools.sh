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
    codex)
      echo "== $name: sign in to Codex with your ChatGPT account in your browser"
      # Codex's sign-in hung in aisw's empty profile (1.7.1), so it keeps the normal browser.
      in_folder codex "$dir" env -u BROWSER "$CODEX_BIN" login && codex_signed_in "$dir"
      ;;
    agy) agy_login ;;
  esac
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
