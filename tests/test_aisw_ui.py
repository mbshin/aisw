"""ui.py: the aisw list dashboard, driven with Textual's test pilot."""

import asyncio
import importlib.util
import json
import time
from pathlib import Path

import pytest

pytest.importorskip("textual")

UI = Path(__file__).resolve().parent.parent / "ui.py"
spec = importlib.util.spec_from_file_location("aisw_ui", UI)
ui = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ui)

FAKE_CLAUDE = """#!/usr/bin/env bash
case $(basename "$CLAUDE_CONFIG_DIR") in
  a) printf 'Login method: Claude Team account\\nOrganization: Example Inc\\nEmail: a@x\\n' ;;
  b) printf "Login method: Claude Max account\\nOrganization: b@x's Organization\\nEmail: b@x\\n" ;;
  *) echo "Not logged in." ;;
esac
"""
FAKE_CODEX = """#!/usr/bin/env bash
if [ -f "$CODEX_HOME/auth.json" ]; then echo "Logged in using ChatGPT"; else echo "Not logged in"; exit 1; fi
"""
FAKE_AGY = "#!/usr/bin/env bash\nexit 1\n"


@pytest.fixture
def env(tmp_path):
    state = tmp_path / "state"
    state.mkdir()
    bins = {}
    for tool, text in (("claude", FAKE_CLAUDE), ("codex", FAKE_CODEX), ("agy", FAKE_AGY)):
        fake = tmp_path / f"fake-{tool}"
        fake.write_text(text)
        fake.chmod(0o755)
        bins[tool] = str(fake)
    (tmp_path / "d").mkdir()
    (tmp_path / "d" / "auth.json").write_text("{}")
    (state / "accounts").write_text(
        f"a claude {tmp_path}/a\nb claude {tmp_path}/b\nc claude {tmp_path}/c\nd codex {tmp_path}/d\n"
        f"e agy {tmp_path}/.gemini/antigravity-cli\n"
    )
    return tmp_path, state, bins


def test_read_accounts_keeps_order_and_spaces_in_folders(tmp_path):
    (tmp_path / "accounts").write_text("b claude /x/my folder\na codex /y\nbroken\n")
    assert ui.read_accounts(tmp_path) == [("b", "claude", "/x/my folder"), ("a", "codex", "/y")]
    assert ui.read_accounts(tmp_path / "none") == []


def test_read_login_per_tool(env):
    home, _, bins = env
    assert ui.read_login("claude", f"{home}/a", bins) == ui.Login("a@x", "Team", "Example Inc", True)
    assert ui.read_login("claude", f"{home}/b", bins) == ui.Login("b@x", "Max", "personal", True)
    assert ui.read_login("claude", f"{home}/c", bins) == ui.Login()
    assert ui.read_login("codex", f"{home}/d", bins) == ui.Login("ChatGPT", signed_in=True)
    assert ui.read_login("codex", f"{home}/none", bins) == ui.Login("ChatGPT", signed_in=False)
    assert ui.read_login("agy", "", bins) == ui.Login("Google", signed_in=False)


def test_read_usage_follows_the_limit_rules(env):
    _, state, _ = env
    now = time.time()
    reset = int(now) + 3600
    usage = {"five_hour": {"used_percentage": 96, "resets_at": reset}, "seven_day": {"used_percentage": 10}}
    (state / "b.usage.json").write_text(json.dumps(usage))
    (state / "c.limit").write_text(str(int(now) - 10))
    b = ui.read_usage(ui.Account("b", "claude", "", ui.Login()), state, now)
    assert b.blocked_until == reset and b.five == 96
    assert ui.read_usage(ui.Account("c", "claude", "", ui.Login()), state, now).blocked_until is None


def test_gauge_and_countdown():
    assert ui.gauge(None) == "–"
    assert ui.gauge(50, width=4) == "[$success]▰▰[/][dim]▱▱[/]  50%"
    assert ui.gauge(96, width=4).startswith("[$error]")
    assert ui.countdown(1000 + 3 * 3600 + 12 * 60, 1000) == "3h 12m"
    assert ui.countdown(1000 + 5 * 60, 1000) == "5m"
    assert ui.countdown(900, 1000) == "0m"


def run_app(env, keys, check=None, current="", size=(120, 40)):
    home, state, bins = env
    result = home / "result"
    result.unlink(missing_ok=True)

    async def go():
        app = ui.AiswUI(state, bins, current, result)
        async with app.run_test(size=size) as pilot:
            await app.workers.wait_for_complete()
            await pilot.pause()
            for key in keys:
                await pilot.press(key)
                await pilot.pause()
            if check:
                check(app)

    asyncio.run(go())
    return result.read_text() if result.exists() else ""


def test_cards_show_every_tool_and_the_current_account(env):
    _, state, _ = env
    (state / "a.limit").write_text(str(int(time.time()) + 600))
    cards = {}

    def check(app):
        for name in "abcde":
            card = app.query_one(f"#card-{name}", ui.Card)
            cards[name] = (str(card.render()), card.has_class("blocked"))

    run_app(env, [], check, current="b")
    assert "a@x" in cards["a"][0] and "Example Inc · Team" in cards["a"][0] and "used up" in cards["a"][0]
    assert cards["a"][1]
    assert "personal · Max" in cards["b"][0] and "current" in cards["b"][0] and "free" in cards["b"][0]
    assert "not signed in" in cards["c"][0]
    assert "Codex" in cards["d"][0] and "signed in" in cards["d"][0]
    assert "Antigravity" in cards["e"][0] and "not signed in" in cards["e"][0]


def test_focus_starts_on_the_current_account(env):
    seen = []
    run_app(env, [], lambda app: seen.append(app.focused.acct), current="d")
    assert seen == ["d"]


def test_enter_launches_and_a_activates_the_selected_account(env):
    assert run_app(env, ["right", "enter"]) == "launch b\n"
    assert run_app(env, ["left", "a"]) == "activate e\n"


def test_n_asks_aisw_to_add(env):
    assert run_app(env, ["n"]) == "add\n"


def test_login_asks_first_on_a_signed_in_account(env):
    assert run_app(env, ["l", "s", "enter"]) == ""  # typing "ls⏎" by mistake: Enter = the focused "No"
    assert run_app(env, ["l", "n"]) == ""
    assert run_app(env, ["l", "y"]) == "login a\n"
    assert run_app(env, ["right", "right", "l"]) == "login c\n"  # not signed in: no question


def test_remove_asks_first(env):
    assert run_app(env, ["d", "enter"]) == ""
    assert run_app(env, ["d", "y"]) == "remove a\n"


def test_arrows_wrap_around(env):
    seen = []
    run_app(env, ["left"], lambda app: seen.append(app.focused.acct))
    run_app(env, ["right"] * 5, lambda app: seen.append(app.focused.acct))
    assert seen == ["e", "a"]


@pytest.mark.parametrize(("width", "narrow"), [(89, True), (90, False)])
def test_narrow_terminal_stacks_the_cards(env, width, narrow):
    seen = []
    run_app(env, [], lambda app: seen.append(app.query_one("#cards").has_class("narrow")), size=(width, 60))
    assert seen == [narrow]


def test_no_accounts_says_how_to_add(env):
    _, state, _ = env
    (state / "accounts").unlink()
    seen = []
    run_app(env, ["enter", "a"], lambda app: seen.append(str(app.query_one("#empty").render())))
    assert "Press n to add one." in seen[0]
    assert run_app(env, ["n"]) == "add\n"


def test_quit_writes_no_result(env):
    assert run_app(env, ["q"]) == ""
