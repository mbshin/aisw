# Codex as the last fallback (opt-in: aisw setup --codex). Sourced by aisw, not run.
# Codex can't read Claude's session files, so it gets a handoff note: task, recent requests,
# where Claude stopped, and the git state.

CODEX_BIN=${AISW_CODEX:-codex}

codex_enabled() { [ "$(cat "$STATE/fallback" 2>/dev/null)" = codex ]; }

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

# go_codex <session file or empty> <folder>: hand over and run Codex interactively.
go_codex() {
  local f=$1 dir=$2 note prompt code
  command -v "$CODEX_BIN" >/dev/null || { echo "Codex not found: brew install codex" >&2; return 1; }
  cd "$dir" || return 1
  if [ -z "$f" ]; then
    "$CODEX_BIN"
    return
  fi
  note=$(mktemp "${TMPDIR:-/tmp}/aisw-handoff.XXXXXX")
  write_note "$f" "$dir" "$note"
  prompt="A Claude Code session hit its usage limit. Read $note for the task and progress, \
check git status and git diff, then continue. Ask before anything destructive."
  echo "Going on in Codex (handoff note: $note)."
  "$CODEX_BIN" "$prompt"
  code=$?
  rm -f "$note"
  return $code
}

# offer_codex <session file or empty> <folder>: the y/N question when every Claude account is used up.
offer_codex() {
  local ans
  codex_enabled || return 1
  printf 'All Claude accounts are used up. Continue in Codex? [y/N] ' >&2
  read -r ans || ans=
  case $ans in [yY]*) go_codex "$1" "$2" ;; *) return 1 ;; esac
}

codex_who() {
  codex_enabled || return 0
  echo "Codex (fallback): $("$CODEX_BIN" login status 2>&1 | head -1)"
}
