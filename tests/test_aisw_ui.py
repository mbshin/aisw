"""ui.py: the aisw ui dashboard, driven with Textual's test pilot."""

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
  .claude-a) printf 'Login method: Claude Team account\\nOrganization: Example Inc\\nEmail: a@x\\n' ;;
  .claude-b) printf "Login method: Claude Max account\\nOrganization: b@x's Organization\\nEmail: b@x\\n" ;;
  *) echo "Not logged in." ;;
esac
"""


@pytest.fixture
def env(tmp_path):
    state = tmp_path / "state"
    state.mkdir()
    fake = tmp_path / "fake-claude"
    fake.write_text(FAKE_CLAUDE)
    fake.chmod(0o755)
    return tmp_path, state, str(fake)


def test_read_login_parses_email_and_plan(env):
    home, _, claude = env
    assert ui.read_login("a", home, claude) == ui.Login("a@x", "Team", "Example Inc")
    assert ui.read_login("b", home, claude) == ui.Login("b@x", "Max", "personal")
    assert ui.read_login("c", home, claude) == ui.Login()


def test_read_account_follows_the_switch_rules(env):
    _, state, _ = env
    now = time.time()
    reset = int(now) + 3600
    usage = {"five_hour": {"used_percentage": 96, "resets_at": reset}, "seven_day": {"used_percentage": 10}}
    (state / "b.usage.json").write_text(json.dumps(usage))
    (state / "c.limit").write_text(str(int(now) - 10))
    assert ui.read_account("b", state, ui.Login(), now).blocked_until == reset
    assert ui.read_account("c", state, ui.Login(), now).blocked_until is None


def test_gauge_and_countdown():
    assert ui.gauge(None) == "–"
    assert ui.gauge(50, width=4) == "[$success]▰▰[/][dim]▱▱[/]  50%"
    assert ui.gauge(96, width=4).startswith("[$error]")
    assert ui.countdown(1000 + 3 * 3600 + 12 * 60, 1000) == "3h 12m"
    assert ui.countdown(1000 + 5 * 60, 1000) == "5m"
    assert ui.countdown(1000 + 59 * 60 + 59, 1000) == "59m"  # under an hour: minutes only
    assert ui.countdown(1000 + 3600, 1000) == "1h 00m"
    assert ui.countdown(900, 1000) == "0m"  # already past


def run_app(home, state, claude, result, keys, check=None, size=(120, 30)):
    async def go():
        app = ui.AiswUI(home, state, claude, result)
        async with app.run_test(size=size) as pilot:
            await app.workers.wait_for_complete()
            await pilot.pause()
            for key in keys:
                await pilot.press(key)
                await pilot.pause()
            if check:
                check(app)

    asyncio.run(go())


def test_cards_show_logins_owner_and_next(env):
    home, state, claude = env
    (state / "a.limit").write_text(str(int(time.time()) + 600))
    cards = {}

    def check(app):
        for acct in ui.ACCOUNTS:
            card = app.query_one(f"#card-{acct}", ui.Card)
            cards[acct] = (str(card.render()), card.has_class("blocked"))

    run_app(home, state, claude, None, [], check)
    assert "a@x" in cards["a"][0] and "Example Inc · Team" in cards["a"][0] and "used up" in cards["a"][0]
    assert cards["a"][1]
    assert "personal · Max" in cards["b"][0] and "next" in cards["b"][0]
    assert "not logged in" in cards["c"][0]


def test_enter_and_login_write_the_choice(env):
    home, state, claude = env
    result = home / "result"
    run_app(home, state, claude, result, ["down", "enter"])
    assert result.read_text() == "start b\n"
    run_app(home, state, claude, result, ["down", "down", "l"])
    assert result.read_text() == "login c\n"


def test_reset_clears_the_limit_after_yes(env):
    home, state, claude = env
    limit = state / "a.limit"
    limit.write_text(str(int(time.time()) + 600))
    run_app(home, state, claude, None, ["r", "tab", "shift+tab"])
    assert limit.exists()  # dialog open, nothing pressed yet
    run_app(home, state, claude, None, ["r", "enter"])
    assert not limit.exists()


def selected_after(env, keys):
    home, state, claude = env
    seen = []
    run_app(home, state, claude, None, keys, lambda app: seen.append(app.focused.acct))
    return seen[0]


def test_left_and_right_wrap_around(env):
    assert selected_after(env, ["left"]) == "c"
    assert selected_after(env, ["right", "right", "right"]) == "a"
    assert selected_after(env, ["up"]) == "c"


@pytest.mark.parametrize(("width", "narrow"), [(80, True), (89, True), (90, False), (120, False)])
def test_narrow_terminal_stacks_the_cards(env, width, narrow):
    home, state, claude = env
    seen = []
    run_app(home, state, claude, None, [], lambda app: seen.append(app.query_one("#cards").has_class("narrow")),
            size=(width, 40))
    assert seen == [narrow]


def test_quit_writes_no_result(env):
    home, state, claude = env
    result = home / "result"
    run_app(home, state, claude, result, ["q"])
    assert not result.exists()


def test_reset_without_a_limit_only_shows_a_notice(env):
    home, state, claude = env
    before = sorted(p.name for p in state.iterdir())
    seen = {}

    def check(app):
        seen["confirm"] = isinstance(app.screen, ui.Confirm)
        seen["notices"] = [n.message for n in app._notifications]

    run_app(home, state, claude, None, ["r"], check)
    assert not seen["confirm"]
    assert seen["notices"] == ["A has no limit mark."]
    assert sorted(p.name for p in state.iterdir()) == before


def test_reset_no_keeps_the_limit(env):
    home, state, claude = env
    limit = state / "b.limit"
    limit.write_text(str(int(time.time()) + 600))
    run_app(home, state, claude, None, ["down", "r", "tab", "enter"])  # tab to No
    assert limit.exists()
