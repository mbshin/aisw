"""aisw: status line, limit hook and wrapper, run against a fake `claude`."""

import json
import os
import shutil
import subprocess
import time
from pathlib import Path

import pytest

TOOL = Path(__file__).resolve().parent.parent

pytestmark = pytest.mark.skipif(shutil.which("jq") is None, reason="needs jq")

# Fake claude: logs how it was started; on accounts listed in $HOME/hits it plays a limit hit by
# running the hook.
FAKE_CLAUDE = """#!/usr/bin/env bash
acct=$(basename "$CLAUDE_CONFIG_DIR")
if [ "$1" = auth ]; then
  case $2 in
    status) if [ -f "$CLAUDE_CONFIG_DIR/login" ]; then
              printf 'Login method: Claude Team account\nOrganization: Example Inc\nEmail: %s\n' \
                "$(cat "$CLAUDE_CONFIG_DIR/login")"
            else echo "Not logged in."; fi ;;
    login) echo "$acct $*" >> "$HOME/logins.log"
           echo "$BROWSER" >> "$HOME/browser.log"
           echo "user-${acct#.claude-}@x" > "$CLAUDE_CONFIG_DIR/login" ;;
  esac
  exit 0
fi
echo "$acct $PWD $*" >> "$HOME/calls.log"
if grep -qx "${acct#.claude-}" "$HOME/hits" 2>/dev/null; then
  echo '{"session_id": "s-123", "cwd": "'"$HOME/work"'", "hook_event_name": "StopFailure"}' \\
    | "$TOOL/on-limit.sh"
fi
"""


@pytest.fixture
def home(tmp_path):
    for d in (".claude-a", ".claude-b", ".claude-c", "work"):
        (tmp_path / d).mkdir()
    (tmp_path / "hits").write_text("a\n")
    fake = tmp_path / "fake-claude"
    fake.write_text(FAKE_CLAUDE)
    fake.chmod(0o755)
    return tmp_path


def run(home, script, *args, stdin="", account=None, tmpdir=None, fzf=None, codex=None):
    env = {
        "PATH": os.environ["PATH"],
        "HOME": str(home),
        "TOOL": str(TOOL),
        "AISW_STATE": str(home / "state"),
        "AISW_CLAUDE": str(home / "fake-claude"),
        "AISW_QUIET": "1",
        "AISW_WAIT": "0",
    }
    if tmpdir:
        env["TMPDIR"] = str(tmpdir)
    if fzf:
        env["AISW_FZF"] = str(fzf)
    if codex:
        env["AISW_CODEX"] = str(codex)
    if account:
        env["CLAUDE_CONFIG_DIR"] = str(home / f".claude-{account}")
    return subprocess.run(
        [str(TOOL / script), *args], input=stdin, env=env, capture_output=True, text=True, cwd=home, check=False
    )


def usage(five, seven, resets_in=3600):
    reset = int(time.time()) + resets_in
    return json.dumps(
        {
            "session_id": "s-1",
            "rate_limits": {
                "five_hour": {"used_percentage": five, "resets_at": reset},
                "seven_day": {"used_percentage": seven, "resets_at": reset + 86400},
            },
        }
    )


def test_statusline_without_rate_limits_shows_account_only(home):
    out = run(home, "statusline.sh", stdin='{"session_id": "s-1"}', account="b")
    assert out.stdout.strip() == "B"
    assert not (home / "state" / "b.usage.json").exists()


def test_statusline_records_usage_and_warns(home):
    out = run(home, "statusline.sh", stdin=usage(82.4, 40.0), account="a")
    assert out.stdout.strip() == "A · 5h 82% · 7d 40% ⚠"
    saved = json.loads((home / "state" / "a.usage.json").read_text())
    assert saved["five_hour"]["used_percentage"] == 82.4


def test_high_usage_makes_wrapper_pick_b(home):
    run(home, "statusline.sh", stdin=usage(96, 50), account="a")
    out = run(home, "aisw", "--dry-run")
    assert out.stdout.strip() == f"CLAUDE_CONFIG_DIR={home}/.claude-b {home}/fake-claude"


def test_limit_hit_moves_the_session_to_b(home):
    out = run(home, "aisw", "-n", "job")
    assert out.returncode == 0, out.stderr
    calls = (home / "calls.log").read_text().splitlines()
    assert calls[0] == f".claude-a {home} -n job"
    assert calls[1].startswith(f".claude-b {home}/work --resume s-123 The previous turn was cut off")
    assert len(calls) == 2
    assert not (home / "state" / "handoff.json").exists()
    assert int((home / "state" / "a.limit").read_text()) > time.time()


def block(home, *accounts):
    later = str(int(time.time()) + 600)
    (home / "state").mkdir(exist_ok=True)
    for acct in accounts:
        (home / "state" / f"{acct}.limit").write_text(later)


def test_a_and_b_used_up_starts_c(home):
    block(home, "a", "b")
    out = run(home, "aisw", "--dry-run")
    assert out.stdout.strip() == f"CLAUDE_CONFIG_DIR={home}/.claude-c {home}/fake-claude"


def test_limit_hit_on_b_moves_to_c_when_a_is_used_up(home):
    block(home, "a")
    (home / "hits").write_text("b\n")
    out = run(home, "aisw")
    assert out.returncode == 0, out.stderr
    calls = (home / "calls.log").read_text().splitlines()
    assert calls[0] == f".claude-b {home} "
    assert calls[1].startswith(f".claude-c {home}/work --resume s-123 ")
    assert len(calls) == 2


def test_limit_hit_on_b_goes_back_to_a_when_free(home):
    (home / "hits").write_text("b\n")
    run(home, "aisw", "b")
    calls = (home / "calls.log").read_text().splitlines()
    assert calls[1].startswith(f".claude-a {home}/work --resume s-123 ")


def test_all_used_up_stops_with_reset_times(home):
    block(home, "a", "b", "c")
    out = run(home, "aisw")
    assert out.returncode == 1
    assert "All accounts are at their limit" in out.stderr
    for label in "ABC":
        assert f"{label}: used up until" in out.stderr
    assert not (home / "calls.log").exists()


def test_force_c_and_status_lists_three(home):
    out = run(home, "aisw", "--dry-run", "c")
    assert out.stdout.strip() == f"CLAUDE_CONFIG_DIR={home}/.claude-c {home}/fake-claude"
    out = run(home, "aisw", "status")
    assert [line.split(":")[0] for line in out.stdout.splitlines()] == ["A", "B", "C"]


def test_limit_hit_on_c_leaves_handoff(home):
    out = run(home, "on-limit.sh", stdin='{"session_id": "s-7", "cwd": "/tmp"}', account="c")
    assert out.returncode == 0
    assert json.loads((home / "state" / "handoff.json").read_text())["from"] == "c"


def test_stale_handoff_is_ignored(home):
    (home / "state").mkdir()
    old = {"from": "b", "at": 1, "session_id": "old", "cwd": str(home)}
    (home / "state" / "handoff.json").write_text(json.dumps(old))
    out = run(home, "aisw", "b")
    assert out.returncode == 0
    assert len((home / "calls.log").read_text().splitlines()) == 1


def test_plain_claude_limit_only_marks_default(home):
    out = run(home, "on-limit.sh", stdin='{"session_id": "s-9", "cwd": "/tmp"}')
    assert out.returncode == 0
    assert (home / "state" / "default.limit").exists()
    assert not (home / "state" / "handoff.json").exists()


def test_who_shows_each_login(home):
    (home / ".claude-a" / "login").write_text("me@x\n")
    out = run(home, "aisw", "who")
    assert out.stdout.splitlines() == [
        "A: me@x · Example Inc (Claude Team account)",
        "B: not logged in",
        "C: not logged in",
    ]


def test_login_only_asks_for_missing_accounts(home):
    (home / ".claude-a" / "login").write_text("me@x\n")
    out = run(home, "aisw", "login")
    assert out.returncode == 0, out.stderr
    assert (home / "logins.log").read_text().splitlines() == [".claude-b auth login", ".claude-c auth login"]
    assert out.stdout.splitlines()[-3:] == [
        "A: me@x · Example Inc (Claude Team account)",
        "B: user-b@x · Example Inc (Claude Team account)",
        "C: user-c@x · Example Inc (Claude Team account)",
    ]


def test_login_one_account_passes_options(home):
    run(home, "aisw", "login", "b", "--email", "b@x")
    assert (home / "logins.log").read_text().splitlines() == [".claude-b auth login --email b@x"]


def test_login_opens_sign_in_in_empty_browser_profile(home):
    (home / "tmp").mkdir()
    (home / "tmp" / "aisw-login.old").mkdir()
    run(home, "aisw", "login", "a", tmpdir=home / "tmp")
    assert (home / "browser.log").read_text().strip() == f"{TOOL}/signin-browser.sh"
    assert not (home / "tmp" / "aisw-login.old").exists()  # sign-in profile removed afterwards


def test_login_prefills_the_saved_email_and_saves_the_new_one(home):
    (home / "state").mkdir()
    (home / "state" / "b.email").write_text("saved-b@x\n")
    run(home, "aisw", "login", "b")
    assert (home / "logins.log").read_text().splitlines() == [".claude-b auth login --email saved-b@x"]
    assert (home / "state" / "b.email").read_text() == "user-b@x\n"  # the account that really logged in


def test_relogin_prefills_the_current_email(home):
    (home / ".claude-a" / "login").write_text("me@x\n")
    run(home, "aisw", "login", "a")
    assert (home / "logins.log").read_text().splitlines() == [".claude-a auth login --email me@x"]


def session(home, folder, sid, *lines):
    proj = home / ".claude" / "projects" / folder.replace("/", "-")
    proj.mkdir(parents=True, exist_ok=True)
    (proj / f"{sid}.jsonl").write_text("".join(json.dumps(x) + "\n" for x in lines))


def test_resume_lists_sessions_and_resumes_the_pick(home):
    (home / "hits").write_text("")
    work = str(home / "work")
    session(
        home, work, "s-old",
        {"type": "mode"},
        {"type": "user", "cwd": work, "isMeta": True, "message": {"content": "meta"}},
        {"type": "user", "cwd": work, "message": {"content": "<command-name>/model</command-name>"}},
        {"type": "user", "cwd": work, "message": {"content": [{"type": "text", "text": "remember  mango"}]}},
    )
    fake_fzf = home / "fake-fzf"
    fake_fzf.write_text('#!/usr/bin/env bash\ntee "$HOME/fzf-input" | head -1\n')
    fake_fzf.chmod(0o755)
    out = run(home, "aisw", "resume", fzf=fake_fzf)
    assert out.returncode == 0, out.stderr
    listed = (home / "fzf-input").read_text()
    assert "~/work" in listed and "remember mango" in listed
    assert (home / "calls.log").read_text().splitlines() == [f".claude-a {work} --resume s-old"]


def test_setup_then_unsetup(home):
    claude_dir = home / ".claude"
    claude_dir.mkdir()
    other = {"type": "command", "command": "/x/notify"}
    before = {"model": "m", "hooks": {"StopFailure": [{"hooks": [other]}]}}
    (claude_dir / "settings.json").write_text(json.dumps(before))
    out = run(home, "aisw", "setup")
    assert out.returncode == 0, out.stderr
    settings = json.loads((claude_dir / "settings.json").read_text())
    assert settings["statusLine"]["command"] == f"{TOOL}/statusline.sh"
    assert settings["hooks"]["StopFailure"] == [
        {"hooks": [other]},
        {"matcher": "rate_limit", "hooks": [{"type": "command", "command": f"{TOOL}/on-limit.sh"}]},
    ]
    assert os.readlink(home / ".claude-c" / "projects") == str(claude_dir / "projects")
    run(home, "aisw", "setup")  # twice: still one limit hook
    assert len(json.loads((claude_dir / "settings.json").read_text())["hooks"]["StopFailure"]) == 2

    (home / ".zshrc").write_text("export A=1\n# aisw: three Claude accounts\nalias claude=aisw\n")
    out = run(home, "aisw", "unsetup")
    assert out.returncode == 0, out.stderr
    assert json.loads((claude_dir / "settings.json").read_text()) == before
    assert (home / ".zshrc").read_text() == "export A=1\n"


def test_test_hit_marks_the_newest_session(home):
    work = home / "work"
    session(home, str(work), "s-9", {"type": "user", "cwd": str(work), "message": {"content": "hi"}})
    out = run(home, "aisw", "test-hit", "b", str(work))
    assert out.returncode == 0, out.stderr
    handoff = json.loads((home / "state" / "handoff.json").read_text())
    assert handoff["from"] == "b" and handoff["session_id"] == "s-9"


def test_help_lists_commands_without_starting_claude(home):
    out = run(home, "aisw", "help")
    assert out.returncode == 0
    assert "aisw resume" in out.stdout and "aisw test-hit" in out.stdout
    assert not (home / "calls.log").exists()


# Fake codex: logs its folder and prompt, keeps a copy of the handoff note it was pointed at.
FAKE_CODEX = """#!/usr/bin/env bash
if [ "$1 $2" = "login status" ]; then echo "Logged in using ChatGPT"; exit 0; fi
echo "$PWD|$*" >> "$HOME/codex.log"
note=$(grep -o '/[^ ]*aisw-handoff[^ ]*' <<<"$*" | head -1)
[ -n "$note" ] && cp "$note" "$HOME/note.md"
exit 0
"""


@pytest.fixture
def codex(home):
    fake = home / "fake-codex"
    fake.write_text(FAKE_CODEX)
    fake.chmod(0o755)
    return fake


def test_setup_codex_turns_the_fallback_on_and_who_shows_it(home, codex):
    out = run(home, "aisw", "setup", "--codex", codex=codex)
    assert out.returncode == 0, out.stderr
    assert (home / "state" / "fallback").read_text().strip() == "codex"
    assert run(home, "aisw", "who", codex=codex).stdout.splitlines()[-1] == "Codex (fallback): Logged in using ChatGPT"
    run(home, "aisw", "unsetup", "--codex", codex=codex)
    assert not (home / "state" / "fallback").exists()


def test_all_used_up_hands_over_to_codex_on_yes(home, codex):
    work = home  # aisw runs in home; the newest session of that folder is handed over
    session(
        home, str(work), "s-5",
        {"type": "user", "cwd": str(work), "message": {"content": "build the login page"}},
        {"type": "assistant", "message": {"content": [{"type": "text", "text": "Half done: form added."}]}},
        {"type": "user", "cwd": str(work), "message": {"content": "add a remember-me box"}},
    )
    block(home, "a", "b", "c")
    (home / "state" / "fallback").write_text("codex\n")
    out = run(home, "aisw", stdin="y\n", codex=codex, tmpdir=home)
    assert out.returncode == 0, out.stderr
    assert "Continue in Codex? [y/N]" in out.stderr
    folder, prompt = (home / "codex.log").read_text().strip().split("|", 1)
    assert folder == str(home) and "hit its usage limit" in prompt
    note = (home / "note.md").read_text()
    assert "build the login page" in note and "- add a remember-me box" in note and "Half done" in note
    assert not list(home.glob("aisw-handoff.*"))  # note removed after Codex exits


def test_all_used_up_without_yes_stops_as_before(home, codex):
    block(home, "a", "b", "c")
    (home / "state" / "fallback").write_text("codex\n")
    out = run(home, "aisw", stdin="\n", codex=codex)
    assert out.returncode == 1
    assert not (home / "codex.log").exists()


def test_no_codex_question_when_fallback_is_off(home, codex):
    block(home, "a", "b", "c")
    out = run(home, "aisw", stdin="y\n", codex=codex)
    assert out.returncode == 1 and "Codex" not in out.stderr
