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
              echo "Login method: Claude Team account"
              org=$(cat "$CLAUDE_CONFIG_DIR/org" 2>/dev/null || echo "Example Inc")
              [ -n "$org" ] && echo "Organization: $org"
              echo "Email: $(cat "$CLAUDE_CONFIG_DIR/login")"
            else echo "Not logged in."; fi ;;
    login) echo "$acct $*" >> "$HOME/logins.log"
           echo "$BROWSER" >> "$HOME/browser.log"
           [ -f "$HOME/login-fails" ] && exit 1
           echo "user-${acct#.claude-}@x" > "$CLAUDE_CONFIG_DIR/login" ;;
  esac
  exit 0
fi
echo "$acct $PWD $*" >> "$HOME/calls.log"
if grep -qx "${acct#.claude-}" "$HOME/hits" 2>/dev/null; then
  echo '{"session_id": "s-123", "cwd": "'"$HOME/work"'", "hook_event_name": "StopFailure"}' \\
    | "$TOOL/on-limit.sh"
fi
# A scripted handoff note (e.g. from another account), copied in during the run.
if [ -f "$HOME/fake-handoff" ]; then cp "$HOME/fake-handoff" "$AISW_STATE/handoff.json"; fi
exit "$(cat "$HOME/exit-code" 2>/dev/null || echo 0)"
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


def run(home, script, *args, stdin="", account=None, tmpdir=None, fzf=None, codex=None, ui=None, cwd=None,
        quiet=True):
    env = {
        # $HOME/bin first, for fakes such as osascript.
        "PATH": f"{home}/bin:{os.environ['PATH']}",
        "HOME": str(home),
        "TOOL": str(TOOL),
        "AISW_STATE": str(home / "state"),
        "AISW_CLAUDE": str(home / "fake-claude"),
        "AISW_WAIT": "0",
    }
    if quiet:
        env["AISW_QUIET"] = "1"
    if tmpdir:
        env["TMPDIR"] = str(tmpdir)
    if fzf:
        env["AISW_FZF"] = str(fzf)
    if codex:
        env["AISW_CODEX"] = str(codex)
    if ui:
        env["AISW_UI"] = str(ui)
    if account:
        env["CLAUDE_CONFIG_DIR"] = str(home / f".claude-{account}")
    return subprocess.run(
        [str(TOOL / script), *args], input=stdin, env=env, capture_output=True, text=True, cwd=cwd or home,
        check=False,
    )


def usage(five, seven, resets_in=3600, reset=None):
    reset = reset or int(time.time()) + resets_in
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
    out = run(home, "aisw", "claude")
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
    out = run(home, "aisw", "claude")
    assert out.returncode == 1
    assert "All accounts are at their limit" in out.stderr
    assert "aisw claude a|b|c" in out.stderr
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

    (home / ".zshrc").write_text("export A=1\n# aisw: three Claude accounts\nalias claude='aisw claude'\n")
    out = run(home, "aisw", "unsetup")
    assert out.returncode == 0, out.stderr
    assert json.loads((claude_dir / "settings.json").read_text()) == before
    assert (home / ".zshrc").read_text() == "export A=1\n"
    assert "alias claude='aisw claude'" in run(home, "aisw", "setup").stdout


@pytest.mark.parametrize("old", ["# aisw: three Claude accounts\nalias claude=aisw\n", "# clsw: x\nalias claude=aisw\n"])
def test_unsetup_removes_the_old_alias_too(home, old):
    (home / ".zshrc").write_text("export A=1\n" + old)
    out = run(home, "aisw", "unsetup")
    assert out.returncode == 0, out.stderr
    assert (home / ".zshrc").read_text() == "export A=1\n"


def test_unsetup_leaves_an_empty_zshrc_when_only_the_alias_was_there(home):
    (home / ".zshrc").write_text("alias claude='aisw claude'\n")
    run(home, "aisw", "unsetup")
    assert (home / ".zshrc").read_text() == ""
    assert not (home / ".zshrc.tmp").exists()


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
    assert "aisw claude" in out.stdout and "alias claude='aisw claude'" in out.stdout
    assert not (home / "calls.log").exists()


# Fake dashboard: logs that it ran; writes $HOME/ui-choice (e.g. "start b") as its result, once.
FAKE_UI = """#!/usr/bin/env bash
echo ran >> "$HOME/ui.log"
if [ -f "$HOME/ui-choice" ]; then cat "$HOME/ui-choice" > "$AISW_UI_RESULT"; rm "$HOME/ui-choice"; fi
"""


@pytest.fixture
def ui(home):
    fake = home / "fake-ui"
    fake.write_text(FAKE_UI)
    fake.chmod(0o755)
    return fake


def test_aisw_alone_opens_the_dashboard_not_claude(home, ui):
    out = run(home, "aisw", ui=ui)
    assert out.returncode == 0, out.stderr
    assert (home / "ui.log").read_text() == "ran\n"
    assert not (home / "calls.log").exists()


def test_dashboard_start_b_starts_claude_on_b(home, ui):
    (home / "hits").write_text("")
    (home / "ui-choice").write_text("start b")
    out = run(home, "aisw", "ui", ui=ui)
    assert out.returncode == 0, out.stderr
    assert (home / "calls.log").read_text().splitlines() == [f".claude-b {home} "]


def test_aisw_alone_start_from_dashboard_starts_claude(home, ui):
    (home / "hits").write_text("")
    (home / "ui-choice").write_text("start c")
    run(home, "aisw", ui=ui)
    assert (home / "calls.log").read_text().splitlines() == [f".claude-c {home} "]
    assert (home / "ui.log").read_text() == "ran\n"  # not back to the dashboard


def test_aisw_claude_picks_the_first_free_account(home):
    (home / "hits").write_text("")
    block(home, "a")
    out = run(home, "aisw", "claude", "--continue")
    assert out.returncode == 0, out.stderr
    assert (home / "calls.log").read_text().splitlines() == [f".claude-b {home} --continue"]


@pytest.mark.parametrize(
    "args",
    [("claude", "c", "--dry-run"), ("claude", "--dry-run", "c"), ("--dry-run", "claude", "c"), ("--dry-run", "c")],
)
def test_dry_run_with_a_forced_account(home, args):
    out = run(home, "aisw", *args)
    assert out.stdout.strip() == f"CLAUDE_CONFIG_DIR={home}/.claude-c {home}/fake-claude"


def test_claude_dry_run_and_old_dry_run_print_a(home):
    for args in (("claude", "--dry-run"), ("--dry-run",)):
        out = run(home, "aisw", *args)
        assert out.stdout.strip() == f"CLAUDE_CONFIG_DIR={home}/.claude-a {home}/fake-claude"


def test_account_letter_still_starts_claude(home):
    (home / "hits").write_text("")
    run(home, "aisw", "b", "--resume", "s-1")
    assert (home / "calls.log").read_text().splitlines() == [f".claude-b {home} --resume s-1"]


def test_aisw_claude_forced_account_passes_options(home):
    (home / "hits").write_text("")
    run(home, "aisw", "claude", "b", "--resume", "s-1")
    assert (home / "calls.log").read_text().splitlines() == [f".claude-b {home} --resume s-1"]


# Fake codex: logs its folder and prompt, keeps a copy of the handoff note it was pointed at.
FAKE_CODEX = """#!/usr/bin/env bash
if [ "$1 $2" = "login status" ]; then echo "Logged in using ChatGPT"; exit 0; fi
echo "$PWD|$*" >> "$HOME/codex.log"
note=$(grep -o '/[^ ]*aisw-handoff[^ ]*' <<<"$*" | head -1)
[ -n "$note" ] && cp "$note" "$HOME/note.md"
exit "$(cat "$HOME/codex-exit" 2>/dev/null || echo 0)"
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
    out = run(home, "aisw", "claude", stdin="y\n", codex=codex, tmpdir=home)
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
    out = run(home, "aisw", "claude", stdin="\n", codex=codex)
    assert out.returncode == 1
    assert not (home / "codex.log").exists()


def test_no_codex_question_when_fallback_is_off(home, codex):
    block(home, "a", "b", "c")
    out = run(home, "aisw", "claude", stdin="y\n", codex=codex)
    assert out.returncode == 1 and "Codex" not in out.stderr


# ---- Switch rules (common.sh): which account counts as used up, and until when ----


def hhmm(t):
    return time.strftime("%a %H:%M", time.localtime(t))


def write_usage(home, acct, five, seven, r5=None, r7=None):
    t = int(time.time())
    r5, r7 = r5 or t + 2 * 3600, r7 or t + 3 * 86400
    (home / "state").mkdir(exist_ok=True)
    data = {"five_hour": {"used_percentage": five, "resets_at": r5}, "seven_day": {"used_percentage": seven, "resets_at": r7}}
    (home / "state" / f"{acct}.usage.json").write_text(json.dumps(data))
    return r5, r7


def picked(home):
    """The account aisw claude would start on, or None."""
    out = run(home, "aisw", "claude", "--dry-run").stdout.strip()
    return out.split("/.claude-")[1][0] if out else None


def status_of(home, acct):
    lines = run(home, "aisw", "status").stdout.splitlines()
    return next(line for line in lines if line.startswith(acct.upper() + ":"))


def test_five_hour_at_95_blocks_until_its_reset(home):
    r5, _ = write_usage(home, "a", 95, 10)
    assert status_of(home, "a") == f"A: used up until {hhmm(r5)}"
    assert picked(home) == "b"


def test_five_hour_at_94_is_still_free(home):
    write_usage(home, "a", 94, 10)
    assert status_of(home, "a") == "A: free (5h 94% · 7d 10%)"
    assert picked(home) == "a"


def test_seven_day_at_98_blocks_until_its_reset(home):
    _, r7 = write_usage(home, "a", 10, 98)
    assert status_of(home, "a") == f"A: used up until {hhmm(r7)}"
    assert picked(home) == "b"


def test_a_limit_in_the_past_counts_as_free(home):
    (home / "state").mkdir()
    (home / "state" / "a.limit").write_text(str(int(time.time()) - 60))
    assert status_of(home, "a") == "A: free (no usage seen yet)"
    assert picked(home) == "a"


def test_the_later_of_limit_file_and_usage_reset_wins(home):
    t = int(time.time())
    r5, _ = write_usage(home, "a", 96, 10, r5=t + 7200)
    (home / "state" / "a.limit").write_text(str(t + 600))
    assert status_of(home, "a") == f"A: used up until {hhmm(r5)}"
    (home / "state" / "a.limit").write_text(str(t + 3 * 86400 + 600))
    assert status_of(home, "a") == f"A: used up until {hhmm(t + 3 * 86400 + 600)}"


@pytest.mark.parametrize(
    ("blocked", "expected"), [((), "a"), (("a",), "b"), (("b",), "a"), (("a", "c"), "b"), (("a", "b", "c"), None)]
)
def test_pick_order_is_a_b_c_skipping_used_up(home, blocked, expected):
    block(home, *blocked)
    assert picked(home) == expected


# ---- Status line ----


@pytest.fixture
def osascript(home):
    """Fake osascript on PATH: notifications land in $HOME/notify.log (use run(..., quiet=False))."""
    (home / "bin").mkdir()
    fake = home / "bin" / "osascript"
    fake.write_text('#!/usr/bin/env bash\necho "$2" >> "$HOME/notify.log"\n')
    fake.chmod(0o755)
    return home / "notify.log"


def test_statusline_no_warning_below_80(home):
    assert run(home, "statusline.sh", stdin=usage(79.9, 79), account="a").stdout.strip() == "A · 5h 79% · 7d 79%"


@pytest.mark.parametrize(("five", "seven"), [(80, 10), (10, 80)])
def test_statusline_warns_at_exactly_80(home, five, seven):
    assert run(home, "statusline.sh", stdin=usage(five, seven), account="a").stdout.strip().endswith("⚠")


def test_statusline_notifies_once_per_five_hour_window(home, osascript):
    window = int(time.time()) + 3600
    run(home, "statusline.sh", stdin=usage(91, 10, reset=window), account="b", quiet=False)
    assert len(osascript.read_text().splitlines()) == 1
    assert "Account B at 91% of its 5-hour limit" in osascript.read_text()
    warned = (home / "state" / "b.warned").read_text().strip()
    run(home, "statusline.sh", stdin=usage(93, 10, reset=window), account="b", quiet=False)
    assert len(osascript.read_text().splitlines()) == 1  # same window: no second notification
    run(home, "statusline.sh", stdin=usage(92, 10, reset=window + 5 * 3600), account="b", quiet=False)
    assert len(osascript.read_text().splitlines()) == 2  # next window
    assert (home / "state" / "b.warned").read_text().strip() != warned


def test_statusline_no_notification_below_90(home, osascript):
    run(home, "statusline.sh", stdin=usage(89, 10), account="a", quiet=False)
    assert not osascript.exists()
    assert not (home / "state" / "a.warned").exists()


def test_statusline_for_plain_claude_shows_main(home):
    out = run(home, "statusline.sh", stdin=usage(50, 20))
    assert out.stdout.strip() == "main · 5h 50% · 7d 20%"
    assert (home / "state" / "default.usage.json").exists()


# ---- Limit hook (on-limit.sh) ----


def test_limit_hook_without_usage_guesses_five_hours(home):
    t = time.time()
    run(home, "on-limit.sh", stdin='{"session_id": "s-1", "cwd": "/tmp"}', account="a")
    assert abs(int((home / "state" / "a.limit").read_text()) - (t + 18000)) < 5


def test_limit_hook_uses_the_known_five_hour_reset(home):
    r5, _ = write_usage(home, "a", 60, 10)  # under 95%: not yet used up by the numbers
    run(home, "on-limit.sh", stdin='{"session_id": "s-1", "cwd": "/tmp"}', account="a")
    assert int((home / "state" / "a.limit").read_text()) == r5


def test_limit_hook_with_a_past_reset_guesses(home):
    write_usage(home, "a", 60, 10, r5=int(time.time()) - 60)
    t = time.time()
    run(home, "on-limit.sh", stdin='{"session_id": "s-1", "cwd": "/tmp"}', account="a")
    assert abs(int((home / "state" / "a.limit").read_text()) - (t + 18000)) < 5


def test_limit_hook_handoff_fields_and_notification(home, osascript):
    t = time.time()
    run(home, "on-limit.sh", stdin='{"session_id": "s-42", "cwd": "/w"}', account="b", quiet=False)
    handoff = json.loads((home / "state" / "handoff.json").read_text())
    assert (handoff["from"], handoff["session_id"], handoff["cwd"]) == ("b", "s-42", "/w")
    assert abs(handoff["at"] - t) < 5
    assert "Account B hit its limit" in osascript.read_text() and "/exit" in osascript.read_text()


# ---- Handoff loop in the wrapper ----


def fake_handoff(home, frm, at_offset=60):
    (home / "fake-handoff").write_text(
        json.dumps({"from": frm, "at": int(time.time()) + at_offset, "session_id": "s-x", "cwd": str(home)})
    )


def test_handoff_from_another_account_is_ignored(home):
    (home / "hits").write_text("")
    fake_handoff(home, "a")
    out = run(home, "aisw", "claude", "b")
    assert out.returncode == 0, out.stderr
    assert len((home / "calls.log").read_text().splitlines()) == 1
    assert not (home / "state" / "handoff.json").exists()


def test_handoff_when_the_rest_is_used_up_prints_resume_and_keeps_the_exit_code(home):
    block(home, "b", "c")
    (home / "exit-code").write_text("7")
    out = run(home, "aisw", "claude")
    assert out.returncode == 7
    assert "All accounts are at their limit" in out.stderr
    assert "Resume later with: aisw claude --resume s-123" in out.stderr
    assert len((home / "calls.log").read_text().splitlines()) == 1


def test_switch_message_names_the_next_account(home):
    block(home, "a")
    (home / "hits").write_text("b\n")
    out = run(home, "aisw", "claude")
    assert "B hit its limit. Going on in C in 0s (Ctrl+C to stop)..." in out.stdout


def test_missing_account_folder_says_run_setup(home):
    (home / ".claude-b").rmdir()
    out = run(home, "aisw", "b")
    assert out.returncode == 1 and "run aisw setup" in out.stderr


# ---- Login and who ----


def test_login_with_all_logged_in_logs_nothing_in(home):
    for acct in "abc":
        (home / f".claude-{acct}" / "login").write_text(f"{acct}@x\n")
    out = run(home, "aisw", "login")
    assert out.returncode == 0, out.stderr
    assert not (home / "logins.log").exists()
    assert len(out.stdout.splitlines()) == 3


def test_login_unknown_slot_is_a_usage_error(home):
    out = run(home, "aisw", "login", "x")
    assert out.returncode == 1 and "usage: aisw login" in out.stderr
    assert not (home / "logins.log").exists()


def test_failed_login_keeps_the_saved_email_and_fails(home):
    (home / "state").mkdir()
    (home / "state" / "b.email").write_text("saved-b@x\n")
    (home / "login-fails").write_text("")
    out = run(home, "aisw", "login", "b")
    assert out.returncode != 0
    assert (home / "state" / "b.email").read_text() == "saved-b@x\n"


def test_failed_login_writes_no_email_file(home):
    (home / "login-fails").write_text("")
    out = run(home, "aisw", "login", "c")
    assert out.returncode != 0
    assert not (home / "state" / "c.email").exists()


def test_who_shows_a_personal_plan_as_personal(home):
    (home / ".claude-a" / "login").write_text("me@x\n")
    (home / ".claude-a" / "org").write_text("me@x's Organization\n")
    assert run(home, "aisw", "who").stdout.splitlines()[0] == "A: me@x · personal (Claude Team account)"


def test_who_without_organization_has_no_dot(home):
    (home / ".claude-a" / "login").write_text("me@x\n")
    (home / ".claude-a" / "org").write_text("")
    assert run(home, "aisw", "who").stdout.splitlines()[0] == "A: me@x (Claude Team account)"


# ---- Resume ----


def fzf_fake(home, body):
    fake = home / "fake-fzf"
    fake.write_text("#!/usr/bin/env bash\n" + body + "\n")
    fake.chmod(0o755)
    return fake


def test_resume_with_no_sessions_starts_nothing(home):
    fzf = fzf_fake(home, 'cat > "$HOME/fzf-input"; exit 1')  # fzf on empty input: no pick
    out = run(home, "aisw", "resume", fzf=fzf)
    assert out.returncode != 0
    assert (home / "fzf-input").read_text() == ""
    assert not (home / "calls.log").exists()


def test_resume_of_a_deleted_folder_says_so(home):
    gone = str(home / "gone")
    session(home, gone, "s-1", {"type": "user", "cwd": gone, "message": {"content": "hi"}})
    out = run(home, "aisw", "resume", fzf=fzf_fake(home, "head -1"))
    assert out.returncode != 0
    assert f"Folder is gone: {gone}" in out.stderr
    assert not (home / "calls.log").exists()


def test_resume_passes_the_words_as_fzf_query(home):
    fzf = fzf_fake(home, 'printf "%s\\n" "$@" > "$HOME/fzf-args"; exit 1')
    run(home, "aisw", "resume", "fix", "login", fzf=fzf)
    assert "--query=fix login" in (home / "fzf-args").read_text().splitlines()


def test_resume_lists_no_message_for_meta_only_sessions(home):
    work = str(home / "work")
    session(
        home, work, "s-meta",
        {"type": "user", "cwd": work, "isMeta": True, "message": {"content": "meta"}},
        {"type": "user", "cwd": work, "message": {"content": "<command-name>/clear</command-name>"}},
    )
    run(home, "aisw", "resume", fzf=fzf_fake(home, 'cat > "$HOME/fzf-input"; exit 1'))
    assert "(no message)" in (home / "fzf-input").read_text()


# ---- Codex ----


def test_codex_fallback_without_a_session_starts_plain_codex(home, codex):
    block(home, "a", "b", "c")
    (home / "state" / "fallback").write_text("codex\n")
    out = run(home, "aisw", "claude", stdin="y\n", codex=codex)
    assert out.returncode == 0, out.stderr
    assert (home / "codex.log").read_text() == f"{home}|\n"


def test_codex_missing_is_a_clear_error(home):
    out = run(home, "aisw", "codex", codex=home / "no-such-codex")
    assert out.returncode == 1 and "Codex not found" in out.stderr


def test_aisw_codex_hands_over_the_newest_session(home, codex):
    old = {"type": "user", "cwd": str(home), "message": {"content": "old task"}}
    new = {"type": "user", "cwd": str(home), "message": {"content": "new task"}}
    session(home, str(home), "s-old", old)
    session(home, str(home), "s-new", new)
    proj = home / ".claude" / "projects" / str(home).replace("/", "-")
    os.utime(proj / "s-old.jsonl", (time.time() - 600, time.time() - 600))
    out = run(home, "aisw", "codex", codex=codex, tmpdir=home)
    assert out.returncode == 0, out.stderr
    note = (home / "note.md").read_text()
    assert "new task" in note and "old task" not in note


def test_codex_note_has_repo_state_only_in_a_git_repo(home, codex):
    repo = home / "repo"
    repo.mkdir()
    for folder, in_git in ((home / "work", False), (repo, True)):
        if in_git:
            subprocess.run(["git", "init", "-q", str(repo)], check=True)
            (repo / "new.txt").write_text("x")
        session(home, str(folder), "s-1", {"type": "user", "cwd": str(folder), "message": {"content": "task"}})
        run(home, "aisw", "codex", codex=codex, tmpdir=home, cwd=folder)
        note = (home / "note.md").read_text()
        assert ("## Repo state" in note) == in_git
    assert "?? new.txt" in note


def test_codex_note_is_removed_when_codex_fails(home, codex):
    session(home, str(home), "s-1", {"type": "user", "cwd": str(home), "message": {"content": "task"}})
    (home / "codex-exit").write_text("3")
    out = run(home, "aisw", "codex", codex=codex, tmpdir=home)
    assert out.returncode == 3
    assert (home / "note.md").exists()
    assert not list(home.glob("aisw-handoff.*"))


# ---- Setup, unsetup, test-hit ----


def test_setup_creates_settings_when_missing(home):
    out = run(home, "aisw", "setup")
    assert out.returncode == 0, out.stderr
    settings = json.loads((home / ".claude" / "settings.json").read_text())
    assert settings["statusLine"]["command"] == f"{TOOL}/statusline.sh"


def test_unsetup_with_nothing_set_up(home):
    out = run(home, "aisw", "unsetup")
    assert out.returncode == 0, out.stderr
    assert not (home / ".zshrc").exists()


def test_unsetup_keeps_a_users_own_status_line(home):
    (home / ".claude").mkdir()
    mine = {"statusLine": {"type": "command", "command": "/home/me/statusline.sh"}}
    (home / ".claude" / "settings.json").write_text(json.dumps(mine))
    run(home, "aisw", "unsetup")
    assert json.loads((home / ".claude" / "settings.json").read_text()) == mine


@pytest.mark.parametrize(
    ("lib", "expected"),
    [("hb/Cellar/aisw/1.2.0/libexec", "hb/opt/aisw/libexec"), ("src/aisw", "src/aisw")],
)
def test_lib_dir_uses_homebrews_stable_path(home, lib, expected):
    (home / lib).mkdir(parents=True)
    out = subprocess.run(
        ["bash", "-c", '. "$1"; lib_dir', str(home / lib / "aisw"), str(TOOL / "admin.sh")],
        capture_output=True, text=True, check=True,
    )
    assert out.stdout.strip() == str(home / expected)


def test_test_hit_bad_slot_is_a_usage_error(home):
    out = run(home, "aisw", "test-hit", "x")
    assert out.returncode == 1 and "usage: aisw test-hit" in out.stderr


def test_test_hit_without_sessions_says_so(home):
    out = run(home, "aisw", "test-hit", "a", str(home / "work"))
    assert out.returncode == 1 and "No session found" in out.stderr
    assert not (home / "state" / "handoff.json").exists()
