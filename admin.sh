# aisw setup / unsetup / test-hit. Sourced by aisw (needs common.sh and $CLAUDE_BIN), not run.

SHARED="projects settings.json skills plugins"
ALIAS_LINE="alias claude=aisw"

# Where the hooks should point: Homebrew's stable opt/ path, so upgrades don't break settings.json.
lib_dir() {
  local lib
  lib=$(cd "$(dirname "$0")" && pwd)
  case $lib in */Cellar/aisw/*/libexec) lib=${lib%%/Cellar/*}/opt/aisw/libexec ;; esac
  echo "$lib"
}

backup() { cp "$1" "$1.bak-$(date +%Y%m%d-%H%M%S)" && echo "  backup: $1.bak-…"; }

do_setup() {
  local lib settings acct n
  if [ "${1:-}" = --codex ]; then
    command -v "$CODEX_BIN" >/dev/null || { echo "Install Codex first: brew install codex" >&2; return 1; }
    echo codex > "$STATE/fallback"
    echo "Codex fallback on: when every Claude account is used up, aisw offers to go on in Codex."
    echo "Off again: aisw unsetup --codex"
    return 0
  fi
  lib=$(lib_dir)
  settings=$HOME/.claude/settings.json
  mkdir -p "$HOME/.claude/projects" "$HOME/.claude/skills" "$HOME/.claude/plugins"
  [ -f "$settings" ] || echo '{}' > "$settings"

  echo "Account folders"
  for acct in $ACCOUNTS; do
    mkdir -p "$HOME/.claude-$acct"
    for n in $SHARED; do ln -sfn "$HOME/.claude/$n" "$HOME/.claude-$acct/$n"; done
    echo "  ~/.claude-$acct → shares $SHARED with ~/.claude"
  done

  echo "Settings (~/.claude/settings.json, shared by all accounts)"
  backup "$settings"
  jq --arg sl "$lib/statusline.sh" --arg hook "$lib/on-limit.sh" '
    .statusLine = {type: "command", command: $sl}
    | .hooks.StopFailure = ((.hooks.StopFailure // [])
        | map(select(([.hooks[]?.command] | any(endswith("/on-limit.sh"))) | not))
        + [{matcher: "rate_limit", hooks: [{type: "command", command: $hook}]}])
  ' "$settings" > "$settings.tmp" && mv "$settings.tmp" "$settings"
  echo "  status line → $lib/statusline.sh"
  echo "  StopFailure rate_limit hook → $lib/on-limit.sh"

  cat <<EOF

Next:
  aisw login                       log in to each account
  echo '$ALIAS_LINE' >> ~/.zshrc   optional: keep typing \`claude\`
EOF
}

do_unsetup() {
  local settings=$HOME/.claude/settings.json rc=$HOME/.zshrc
  if [ "${1:-}" = --codex ] || [ -f "$STATE/fallback" ]; then
    rm -f "$STATE/fallback"
    echo "Codex fallback off."
    [ "${1:-}" = --codex ] && return 0
  fi
  if [ -f "$settings" ]; then
    echo "Settings"
    backup "$settings"
    jq '
      (if (.statusLine.command // "") | endswith("/statusline.sh") and (contains("aisw") or contains("clsw")) then del(.statusLine) else . end)
      | if .hooks.StopFailure then
          .hooks.StopFailure |= map(select(([.hooks[]?.command] | any(endswith("/on-limit.sh"))) | not))
          | if .hooks.StopFailure == [] then del(.hooks.StopFailure) else . end
        else . end
    ' "$settings" > "$settings.tmp" && mv "$settings.tmp" "$settings"
    echo "  removed aisw's status line and limit hook"
  fi
  if [ -f "$rc" ] && grep -qxF "$ALIAS_LINE" "$rc"; then
    echo "~/.zshrc"
    backup "$rc"
    grep -vxF "$ALIAS_LINE" "$rc" | grep -v '^# aisw: ' > "$rc.tmp" && mv "$rc.tmp" "$rc"
    echo "  removed '$ALIAS_LINE' (open a new terminal)"
  fi
  cat <<EOF

Kept: the account folders (~/.claude-a …) and their logins, state in $STATE.
Remove them too:  for x in $ACCOUNTS; do CLAUDE_CONFIG_DIR=~/.claude-\$x claude auth logout; done
                  rm -rf ~/.claude-{${ACCOUNTS// /,}} $STATE
EOF
}

# aisw test-hit <a|b|c> [dir]: pretend the account just hit its limit in the newest session of dir.
do_test_hit() {
  local acct=${1:-} dir proj latest sid
  case $acct in a|b|c) ;; *) echo "usage: aisw test-hit a|b|c [dir]" >&2; return 1 ;; esac
  dir=$(cd "${2:-$PWD}" && pwd) || return 1
  # Claude Code keeps a folder's sessions in ~/.claude/projects/<path with / and . as ->/<id>.jsonl
  proj=$HOME/.claude/projects/$(tr '/.' '--' <<<"$dir")
  latest=$(ls -t "$proj"/*.jsonl 2>/dev/null | head -1)
  [ -n "$latest" ] || { echo "No session found for $dir" >&2; return 1; }
  sid=$(basename "$latest" .jsonl)
  jq -n --arg sid "$sid" --arg cwd "$dir" '{session_id: $sid, cwd: $cwd, hook_event_name: "StopFailure"}' \
    | CLAUDE_CONFIG_DIR=$HOME/.claude-$acct "$(dirname "$0")/on-limit.sh"
  echo "Marked $(upper "$acct") used up for session $sid. Type /exit in that session."
}
