"""aisw 2.x: accounts list, activate, launch, add/login/remove, status line and limit hook, against fake tools."""

import json
import os
import shutil
import subprocess
import time
from pathlib import Path

import pytest

TOOL = Path(__file__).resolve().parent.parent

pytestmark = pytest.mark.skipif(shutil.which("jq") is None, reason="needs jq")

# Fake claude: `auth status` reads <folder>/login, `auth login` writes it (fails when $HOME/login-fails exists);
# anything else is a session start, logged with its folder and args.
FAKE_CLAUDE = """#!/usr/bin/env bash
dir=${CLAUDE_CONFIG_DIR:-$HOME/.claude}
if [ "$1" = auth ]; then
  case $2 in
    status) if [ -f "$dir/login" ]; then
              echo "Login method: Claude Team account"
              echo "Organization: Example Inc"
              echo "Email: $(cat "$dir/login")"
            else echo "Not logged in."; fi ;;
    login) echo "$dir $*" >> "$HOME/logins.log"
           echo "$BROWSER" >> "$HOME/browser.log"
           [ -f "$HOME/login-fails" ] && exit 1
           echo "user-$(basename "$dir")@x" > "$dir/login" ;;
  esac
  exit 0
fi
echo "claude $dir ${AISW_ACCOUNT:-} $*" >> "$HOME/calls.log"
"""

# Fake codex: one login per folder (CODEX_HOME, else ~/.codex), kept in auth.json like the real one.
FAKE_CODEX = """#!/usr/bin/env bash
dir=${CODEX_HOME:-$HOME/.codex}
if [ "$1" = login ]; then
  if [ "${2:-}" = status ]; then
    if [ -f "$dir/auth.json" ]; then echo "Logged in using ChatGPT"; else echo "Not logged in"; exit 1; fi
    exit 0
  fi
  echo "$dir $*" >> "$HOME/codex-logins.log"
  [ -f "$HOME/login-fails" ] && exit 1
  mkdir -p "$dir"; echo '{}' > "$dir/auth.json"; exit 0
fi
echo "codex ${CODEX_HOME:-unset} ${AISW_ACCOUNT:-} $*" >> "$HOME/calls.log"
"""

# Fake agy: signed in when $HOME/agy-in exists (`agy models` is aisw's status check).
FAKE_AGY = """#!/usr/bin/env bash
if [ "$1" = models ]; then [ -f "$HOME/agy-in" ]; exit; fi
echo "agy ${AISW_ACCOUNT:-} $*" >> "$HOME/calls.log"
"""


def write_exec(path, text):
    path.write_text(text)
    path.chmod(0o755)


@pytest.fixture
def home(tmp_path):
    (tmp_path / "bin").mkdir()
    (tmp_path / ".claude").mkdir()
    write_exec(tmp_path / "fake-claude", FAKE_CLAUDE)
    write_exec(tmp_path / "fake-codex", FAKE_CODEX)
    write_exec(tmp_path / "fake-agy", FAKE_AGY)
    # Notifications land in a file instead of on screen.
    write_exec(tmp_path / "bin" / "osascript", '#!/usr/bin/env bash\necho "$2" >> "$HOME/notes.log"\n')
    return tmp_path


def env_for(home, account=None, extra=None):
    env = {
        "PATH": f"{home}/bin:{os.environ['PATH']}",
        "HOME": str(home),
        "SHELL": "/bin/zsh",
        "AISW_STATE": str(home / "state"),
        "AISW_CLAUDE": str(home / "fake-claude"),
        "AISW_CODEX": str(home / "fake-codex"),
        "AISW_AGY": str(home / "fake-agy"),
        "AISW_BROWSER": "fake-browser",
        "TMPDIR": str(home / "tmp"),
    }
    (home / "tmp").mkdir(exist_ok=True)
    if account:
        env["CLAUDE_CONFIG_DIR"] = account
    env.update(extra or {})
    return env


def run(home, script, *args, stdin="", account=None, extra=None):
    return subprocess.run(
        [str(TOOL / script), *args], input=stdin, env=env_for(home, account, extra), capture_output=True,
        text=True, cwd=home, check=False,
    )


def aisw(home, *args, **kw):
    return run(home, "aisw", *args, **kw)


def accounts(home):
    path = home / "state" / "accounts"
    return path.read_text().splitlines() if path.exists() else []


def write_accounts(home, *lines):
    (home / "state").mkdir(exist_ok=True)
    (home / "state" / "accounts").write_text("".join(f"{line}\n" for line in lines))


def claude_account(home, name, email=None):
    """A signed-in Claude account <name> in ~/.claude-<name>, as 1.x left them."""
    d = home / f".claude-{name}"
    d.mkdir()
    if email:
        (d / "login").write_text(email + "\n")
    return d


def usage(five, seven, resets_in=3600, reset=None):
    reset = reset or int(time.time()) + resets_in
    return json.dumps({
        "session_id": "s-1",
        "rate_limits": {
            "five_hour": {"used_percentage": five, "resets_at": reset},
            "seven_day": {"used_percentage": seven, "resets_at": reset + 86400},
        },
    })


def calls(home):
    path = home / "calls.log"
    return path.read_text().splitlines() if path.exists() else []


# --- migration from 1.x ------------------------------------------------------------------------------


def test_first_run_turns_1x_accounts_into_named_accounts(home):
    for x in "abc":
        claude_account(home, x)
    (home / ".codex").mkdir()
    (home / ".codex" / "auth.json").write_text("{}")
    (home / ".codex-2").mkdir()
    (home / ".codex-2" / "auth.json").write_text("{}")
    (home / "state").mkdir()
    (home / "state" / "fallback").write_text("codex\nagy\n")
    (home / "state" / "handoff.json").write_text("{}")
    aisw(home, "help")
    assert accounts(home) == [
        f"a claude {home}/.claude-a",
        f"b claude {home}/.claude-b",
        f"c claude {home}/.claude-c",
        f"d codex {home}/.codex",
        f"e codex {home}/.codex-2",
        f"f agy {home}/.gemini/antigravity-cli",
    ]
    assert not (home / "state" / "fallback").exists()
    assert not (home / "state" / "handoff.json").exists()


def test_migration_skips_missing_accounts_and_runs_once(home):
    claude_account(home, "b")
    aisw(home, "help")
    assert accounts(home) == [f"b claude {home}/.claude-b"]
    claude_account(home, "a")  # appearing later doesn't re-run the migration
    aisw(home, "help")
    assert accounts(home) == [f"b claude {home}/.claude-b"]


def test_nothing_to_migrate_leaves_no_accounts_file(home):
    out = aisw(home)
    assert not (home / "state" / "accounts").exists()
    assert out.returncode == 1
    assert "No accounts yet. Add one: aisw add claude|codex|agy" in out.stderr


# --- status line and limit hook ----------------------------------------------------------------------


def test_statusline_shows_the_account_name_and_records_usage(home):
    d = claude_account(home, "b")
    write_accounts(home, f"b claude {d}")
    out = run(home, "statusline.sh", stdin=usage(82.4, 40.0), account=str(d))
    assert out.stdout.strip() == "b · 5h 82% · 7d 40% ⚠"
    assert json.loads((home / "state" / "b.usage.json").read_text())["five_hour"]["used_percentage"] == 82.4


def test_statusline_trailing_slash_and_plain_claude(home):
    d = claude_account(home, "b")
    write_accounts(home, f"b claude {d}")
    assert run(home, "statusline.sh", stdin="{}", account=f"{d}/").stdout.strip() == "b"
    assert run(home, "statusline.sh", stdin="{}").stdout.strip() == "main"


def test_statusline_named_account_in_aisw_home(home):
    d = home / "state" / "home" / "work"
    d.mkdir(parents=True)
    write_accounts(home, f"work claude {d}")
    assert run(home, "statusline.sh", stdin="{}", account=str(d)).stdout.strip() == "work"


def test_statusline_notifies_once_per_window(home):
    d = claude_account(home, "a")
    write_accounts(home, f"a claude {d}")
    reset = int(time.time()) + 3600  # same 5h window both times
    for _ in range(2):
        run(home, "statusline.sh", stdin=usage(91, 10, reset=reset), account=str(d))
    assert (home / "notes.log").read_text().count("at 91% of its 5-hour limit") == 1


def test_limit_hook_marks_the_account_and_names_the_next_free_one(home):
    a, b = claude_account(home, "a"), claude_account(home, "b")
    write_accounts(home, f"a claude {a}", f"b claude {b}", f"d codex {home}/.codex")
    run(home, "on-limit.sh", stdin='{"session_id": "s-1"}', account=str(a))
    until = int((home / "state" / "a.limit").read_text())
    assert until > time.time() + 4 * 3600  # no reset known: guessed 5 hours
    assert "Account a hit its limit" in (home / "notes.log").read_text()
    assert "Next free: b → /exit, aisw activate b, aisw --continue" in (home / "notes.log").read_text()


def test_limit_hook_uses_the_known_reset_and_says_when_none_is_free(home):
    a = claude_account(home, "a")
    write_accounts(home, f"a claude {a}")
    run(home, "statusline.sh", stdin=usage(50, 10, resets_in=1200), account=str(a))
    run(home, "on-limit.sh", stdin="{}", account=str(a))
    until = int((home / "state" / "a.limit").read_text())
    assert abs(until - (time.time() + 1200)) < 30
    assert "No other Claude account is free: aisw list" in (home / "notes.log").read_text()


# --- activate / deactivate / shell line --------------------------------------------------------------


def two_accounts(home):
    a, b = claude_account(home, "a", "a@x"), claude_account(home, "b", "b@x")
    write_accounts(home, f"a claude {a}", f"b claude {b}", f"d codex {home}/.codex", f"e codex {home}/x y")
    return a, b


def test_activate_writes_the_env_file_for_the_shell_function(home):
    _, b = two_accounts(home)
    out = aisw(home, "activate", "b", extra={"AISW_SHELL_PID": "4242"})
    assert out.returncode == 0
    lines = (home / "state" / "env.4242").read_text().splitlines()
    assert lines == ["export AISW_ACCOUNT=b", f"export CLAUDE_CONFIG_DIR={b}", "unset CODEX_HOME"]
    assert (home / "state" / "current").read_text().strip() == "b"


def test_activate_without_the_shell_line_prints_lines_for_eval(home):
    two_accounts(home)
    out = aisw(home, "activate", "d")
    assert out.stdout.splitlines() == ["export AISW_ACCOUNT=d", "unset CLAUDE_CONFIG_DIR", "unset CODEX_HOME"]
    out = aisw(home, "activate", "e")
    assert f"export CODEX_HOME={home}/x\\ y" in out.stdout.splitlines()


def test_activate_unknown_name_and_old_tool_names(home):
    two_accounts(home)
    out = aisw(home, "activate", "zz")
    assert out.returncode == 1 and "No account named 'zz'." in out.stderr
    out = aisw(home, "activate", "codex2")
    assert "Accounts have names now (aisw list); new one: aisw add codex" in out.stderr
    out = aisw(home, "activate")
    assert out.returncode == 1 and "names: a b d e" in out.stderr
    assert not (home / "state" / "current").exists()


def test_deactivate_forgets_the_current_account(home):
    two_accounts(home)
    aisw(home, "activate", "a")
    out = aisw(home, "deactivate")
    assert out.stdout.strip() == "unset AISW_ACCOUNT CLAUDE_CONFIG_DIR CODEX_HOME"
    assert not (home / "state" / "current").exists()


@pytest.mark.parametrize("shell", ["bash", "zsh"])
def test_shell_function_changes_the_calling_shell(home, shell):
    if not shutil.which(shell):
        pytest.skip(f"no {shell}")
    _, b = two_accounts(home)
    # Like Homebrew's exec script, so aisw still finds its files next to it.
    write_exec(home / "bin" / "aisw", f'#!/bin/bash\nexec "{TOOL}/aisw" "$@"\n')
    script = 'eval "$(aisw shell-init zsh)"; aisw activate b >/dev/null 2>&1; echo "$AISW_ACCOUNT $CLAUDE_CONFIG_DIR"'
    out = subprocess.run([shell, "-c", script], env=env_for(home), capture_output=True, text=True, check=False)
    assert out.stdout.strip() == f"b {b}"
    # A new shell starts with the remembered account.
    out = subprocess.run([shell, "-c", 'eval "$(aisw shell-init zsh)"; echo "$AISW_ACCOUNT"'], env=env_for(home),
                         capture_output=True, text=True, check=False)
    assert out.stdout.strip() == "b"
    assert not list((home / "state").glob("env.*"))


# --- plain aisw: launch the current account's CLI -----------------------------------------------------


def test_launch_without_a_current_account_explains(home):
    two_accounts(home)
    out = aisw(home)
    assert out.returncode == 1
    assert "No current account. Pick one: aisw activate <name>" in out.stderr
    assert calls(home) == []


def test_launch_starts_claude_with_the_account_folder_and_options(home):
    _, b = two_accounts(home)
    aisw(home, "activate", "b")
    assert aisw(home, "--continue", "-n", "x").returncode == 0
    assert calls(home) == [f"claude {b} b --continue -n x"]


def test_launch_prefers_this_shells_account_over_the_remembered_one(home):
    a, _ = two_accounts(home)
    aisw(home, "activate", "b")
    aisw(home, "--", "fix the bug", extra={"AISW_ACCOUNT": "a"})
    assert calls(home) == [f"claude {a} a fix the bug"]


def test_launch_codex_translates_continue(home):
    two_accounts(home)
    aisw(home, "activate", "e")
    aisw(home, "--continue")
    aisw(home, "activate", "d")
    aisw(home, "--model", "x")
    assert calls(home) == [f"codex {home}/x y e resume --last", "codex unset d --model x"]


def test_launch_agy(home):
    write_accounts(home, f"a agy {home}/.gemini/antigravity-cli")
    aisw(home, "activate", "a")
    aisw(home, "-c")
    assert calls(home) == ["agy a -c"]


def test_launch_with_a_missing_claude_folder(home):
    write_accounts(home, f"a claude {home}/gone")
    aisw(home, "activate", "a")
    out = aisw(home)
    assert out.returncode == 1 and "aisw login a" in out.stderr


# --- add ---------------------------------------------------------------------------------------------


def test_add_claude_signs_in_then_lists_the_account(home):
    out = aisw(home, "add", "claude")
    assert out.returncode == 0, out.stderr
    d = home / "state" / "home" / "a"
    assert accounts(home) == [f"a claude {d}"]
    assert (d / "projects").resolve() == (home / ".claude" / "projects").resolve()
    assert (d / "settings.json").is_symlink()
    assert (home / "logins.log").read_text().strip() == f"{d} auth login"
    assert (home / "browser.log").read_text().strip() == "fake-browser"
    assert (home / "state" / "a.email").read_text().strip() == "user-a@x"
    assert "Added a (Claude Code). Use it: aisw activate a" in out.stdout


def test_first_add_sets_up_settings_and_the_shell_line_once(home):
    aisw(home, "add", "claude")
    aisw(home, "add", "claude", "work")
    settings = json.loads((home / ".claude" / "settings.json").read_text())
    assert settings["statusLine"]["command"].endswith("/statusline.sh")
    hooks = settings["hooks"]["StopFailure"]
    assert len(hooks) == 1 and hooks[0]["matcher"] == "rate_limit"
    rc = (home / ".zshrc").read_text()
    assert rc.count('eval "$(aisw shell-init zsh)"') == 1


def test_add_uses_bashrc_for_bash(home):
    aisw(home, "add", "claude", extra={"SHELL": "/bin/bash"})
    assert 'eval "$(aisw shell-init bash)"' in (home / ".bashrc").read_text()


def test_add_failed_sign_in_adds_nothing(home):
    (home / "login-fails").write_text("")
    out = aisw(home, "add", "claude", "work")
    assert out.returncode == 1
    assert "Sign-in didn't finish: work not added." in out.stderr
    assert accounts(home) == []
    assert not (home / "state" / "home" / "work").exists()


def test_add_takes_the_next_free_letter(home):
    claude_account(home, "a")
    claude_account(home, "c")
    aisw(home, "help")
    aisw(home, "add", "claude")
    assert accounts(home)[-1] == f"b claude {home}/state/home/b"


@pytest.mark.parametrize(("name", "msg"), [
    ("Work", "Names: lowercase"), ("list", "is a command or tool name"), ("codex", "is a command or tool name"),
    ("a", "There is already an account named 'a'."),
])
def test_add_rejects_bad_names(home, name, msg):
    write_accounts(home, f"a claude {home}/.claude-a")
    out = aisw(home, "add", "claude", name)
    assert out.returncode == 1 and msg in out.stderr
    assert len(accounts(home)) == 1


def test_add_needs_a_known_tool(home):
    out = aisw(home, "add", "gemini")
    assert out.returncode == 1 and "usage: aisw add claude|codex|agy [name]" in out.stderr


def test_add_codex_first_uses_codex_home_then_its_own_folder(home):
    aisw(home, "add", "codex")
    aisw(home, "add", "codex", "work")
    assert accounts(home) == [f"a codex {home}/.codex", f"work codex {home}/state/home/work"]
    assert (home / "codex-logins.log").read_text().splitlines() == [
        f"{home}/.codex login", f"{home}/state/home/work login",
    ]


def test_add_codex_already_signed_in_skips_the_sign_in(home):
    (home / ".codex").mkdir()
    (home / ".codex" / "auth.json").write_text("{}")
    write_accounts(home, f"a claude {home}/.claude-a")
    out = aisw(home, "add", "codex")
    assert "b: already signed in." in out.stdout
    assert not (home / "codex-logins.log").exists()
    assert accounts(home)[-1] == f"b codex {home}/.codex"


def test_add_second_antigravity_account_is_refused(home):
    (home / "agy-in").write_text("")
    assert aisw(home, "add", "agy").returncode == 0
    out = aisw(home, "add", "agy")
    assert out.returncode == 1 and "Only one Antigravity account for now" in out.stderr
    assert accounts(home) == [f"a agy {home}/.gemini/antigravity-cli"]


# --- login / remove ----------------------------------------------------------------------------------


def test_login_claude_prefills_the_email(home):
    a = claude_account(home, "a", "old@x")
    write_accounts(home, f"a claude {a}")
    aisw(home, "login", "a")
    assert (home / "logins.log").read_text().strip() == f"{a} auth login --email old@x"


def test_login_codex_signed_in_doesnt_sign_out(home):
    (home / ".codex").mkdir()
    (home / ".codex" / "auth.json").write_text("{}")
    write_accounts(home, f"d codex {home}/.codex")
    out = aisw(home, "login", "d")
    assert "d: already signed in." in out.stdout
    assert not (home / "codex-logins.log").exists()


def test_login_unknown_or_missing_name(home):
    write_accounts(home, f"a claude {home}/.claude-a")
    assert "No account named 'b'." in aisw(home, "login", "b").stderr
    assert "usage: aisw login <name>" in aisw(home, "login").stderr


def test_remove_keeps_the_folder_and_clears_current(home):
    _, b = two_accounts(home)
    aisw(home, "activate", "b")
    (home / "state" / "b.limit").write_text("1")
    out = aisw(home, "remove", "b")
    assert "Removed b. Its folder and login stay in ~/.claude-b." in out.stdout
    assert [line.split()[0] for line in accounts(home)] == ["a", "d", "e"]
    assert b.exists() and not (home / "state" / "current").exists()
    assert not (home / "state" / "b.limit").exists()


# --- list --------------------------------------------------------------------------------------------


def test_list_piped_is_a_table_of_every_account(home):
    two_accounts(home)
    (home / ".codex").mkdir()
    (home / ".codex" / "auth.json").write_text("{}")
    write_accounts(home, *accounts(home), f"f agy {home}/.gemini/antigravity-cli")
    aisw(home, "activate", "b")
    (home / "state" / "a.limit").write_text(str(int(time.time()) + 600))
    run(home, "statusline.sh", stdin=usage(12, 34), account=str(home / ".claude-b"))
    rows = aisw(home, "list").stdout.splitlines()
    assert rows[0].split() == ["NAME", "TOOL", "LOGIN", "PLAN", "STATE", "5H", "7D"]
    assert rows[1].split()[:6] == ["a", "claude", "a@x", "Team", "used", "up"]
    assert rows[2].split() == ["*", "b", "claude", "b@x", "Team", "free", "12%", "34%"]
    assert rows[3].split() == ["d", "codex", "ChatGPT", "-", "signed", "in", "-", "-"]
    assert rows[4].split()[:5] == ["e", "codex", "ChatGPT", "-", "not"]
    assert rows[5].split()[:5] == ["f", "agy", "Google", "-", "not"]


def test_list_with_no_accounts(home):
    assert "No accounts yet." in aisw(home, "list").stdout


# --- help, completion names, removed commands --------------------------------------------------------


def test_version_and_help(home):
    assert aisw(home, "--version").stdout.startswith("aisw 2.")
    out = aisw(home, "help").stdout
    for cmd in ("aisw list", "aisw add", "aisw login", "aisw remove", "aisw activate", "aisw deactivate"):
        assert cmd in out


def test_completion_names_come_from_saved_emails(home):
    write_accounts(home, f"a claude {home}/.claude-a", f"d codex {home}/.codex")
    (home / "state" / "a.email").write_text("a@x\n")
    assert aisw(home, "__names").stdout.splitlines() == ["a:claude a@x", "d:codex "]


@pytest.mark.parametrize(("cmd", "hint"), [
    ("claude", "aisw activate <name>; aisw"), ("status", "aisw list"), ("who", "aisw list"),
    ("resume", "aisw --resume"), ("setup", "aisw add / aisw login"), ("test-hit", ""),
])
def test_removed_commands_say_what_to_use(home, cmd, hint):
    out = aisw(home, cmd)
    assert out.returncode == 2
    assert f"aisw {cmd} was removed in 2.0." in out.stderr and hint in out.stderr


def test_unknown_command(home):
    out = aisw(home, "lst")
    assert out.returncode == 2 and "Unknown command 'lst'" in out.stderr
    assert calls(home) == []


def test_zsh_completion_parses():
    if not shutil.which("zsh"):
        pytest.skip("no zsh")
    assert subprocess.run(["zsh", "-n", str(TOOL / "completions" / "_aisw")], check=False).returncode == 0
