#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["textual>=8.0"]
# ///
"""aisw ui: one screen for the three Claude accounts.

Reads the same things as `aisw who` and `aisw status`; never reads login tokens. Enter and `l` need the
whole terminal, so the TUI quits and writes "start <x>" or "login <x>" to the file named by
AISW_UI_RESULT; the aisw wrapper runs it.
"""

import json
import os
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Grid, Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Label, Static

ACCOUNTS = ("a", "b", "c")
# Same rules as common.sh: used up at 5h >= 95% or 7d >= 98%, or until the time in <x>.limit.
FIVE_FULL = 95
SEVEN_FULL = 98
WARN = 80


@dataclass
class Login:
    email: str = ""
    plan: str = ""
    org: str = ""


@dataclass
class Account:
    name: str
    login: Login
    five: float | None = None
    seven: float | None = None
    blocked_until: int | None = None


def read_login(acct: str, home: Path, claude: str) -> Login:
    env = {**os.environ, "CLAUDE_CONFIG_DIR": str(home / f".claude-{acct}")}
    try:
        # Detached from the terminal: the TUI owns it, and claude would otherwise read from it.
        out = subprocess.run(
            [claude, "auth", "status", "--text"],
            env=env,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=20,
            start_new_session=True,
            check=False,
        ).stdout
    except (OSError, subprocess.TimeoutExpired):
        return Login()
    fields = dict(line.split(": ", 1) for line in out.splitlines() if ": " in line)
    plan = fields.get("Login method", "").removeprefix("Claude ").removesuffix(" account")
    # A personal plan's organization is named "<email>'s Organization".
    org = fields.get("Organization", "")
    if org.endswith("'s Organization"):
        org = "personal"
    return Login(fields.get("Email", ""), plan, org)


def read_account(acct: str, state: Path, login: Login, now: float) -> Account:
    a = Account(acct, login)
    until = 0
    limit = state / f"{acct}.limit"
    if limit.exists():
        until = int(limit.read_text().strip() or 0)
    usage = state / f"{acct}.usage.json"
    if usage.exists():
        data = json.loads(usage.read_text())
        five, seven = data.get("five_hour") or {}, data.get("seven_day") or {}
        a.five, a.seven = five.get("used_percentage"), seven.get("used_percentage")
        if (a.five or 0) >= FIVE_FULL:
            until = max(until, int(five.get("resets_at") or 0))
        if (a.seven or 0) >= SEVEN_FULL:
            until = max(until, int(seven.get("resets_at") or 0))
    if until > now:
        a.blocked_until = until
    return a


def gauge(pct: float | None, width: int = 10) -> str:
    """5h/7d usage as ▰▰▰▱▱ plus the percentage, colored like the status line."""
    if pct is None:
        return "–"
    filled = round(max(0.0, min(pct, 100.0)) / 100 * width)
    color = "$error" if pct >= FIVE_FULL else "$warning" if pct >= WARN else "$success"
    return f"[{color}]{'▰' * filled}[/][dim]{'▱' * (width - filled)}[/] {pct:3.0f}%"


def countdown(until: int, now: float) -> str:
    mins = max(0, int(until - now) // 60)
    return f"{mins // 60}h {mins % 60:02d}m" if mins >= 60 else f"{mins}m"


def card_text(a: Account, is_next: bool, now: float) -> str:
    if a.blocked_until:
        state = f"[$error]○ used up · {countdown(a.blocked_until, now)}[/]"
    else:
        state = "[$success]● free[/]" + (" · [bold $accent]next[/]" if is_next else "")
    who = a.login.email or "[dim]not logged in[/]"
    owner = " · ".join(x for x in (a.login.org, a.login.plan) if x)
    lines = [state, who, f"[dim]{owner}[/]" if owner else "", ""]
    if a.five is None and a.seven is None:
        lines.append("[dim]no usage numbers[/]")
    else:
        lines += [f"5h {gauge(a.five)}", f"7d {gauge(a.seven)}"]
    if a.blocked_until:
        lines.append(f"[dim]resets {time.strftime('%a %H:%M', time.localtime(a.blocked_until))}[/]")
    return "\n".join(lines)


class Card(Static, can_focus=True):
    """One account. Focus = selected."""

    def __init__(self, acct: str) -> None:
        super().__init__(id=f"card-{acct}")
        self.acct = acct
        self.border_title = f" {acct.upper()} "


class Confirm(ModalScreen[bool]):
    BINDINGS: ClassVar = [Binding("y", "answer(True)", "yes"), Binding("n,escape", "answer(False)", "no")]

    def __init__(self, question: str) -> None:
        super().__init__()
        self.question = question

    def on_mount(self) -> None:
        self.query_one("#no", Button).focus()  # Enter on a stray keypress must not say yes

    def action_answer(self, yes: bool) -> None:
        self.dismiss(yes)

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Label(self.question)
            with Horizontal():
                yield Button("Yes", id="yes", variant="error")
                yield Button("No", id="no")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == "yes")


class AiswUI(App):
    ENABLE_COMMAND_PALETTE = False
    CSS = """
    Screen { background: $background; }
    #top { height: 1; margin: 1 2 0 2; }
    #name { width: 1fr; text-style: bold; color: $accent; }
    #clock { width: auto; color: $text-muted; }
    #cards { grid-size: 3; grid-gutter: 0 2; height: auto; margin: 1 2; }
    #cards.narrow { grid-size: 1; grid-gutter: 1 0; }
    Card {
        height: 10; padding: 0 1;
        border: round $panel-lighten-2; border-title-color: $text-muted; border-title-style: bold;
    }
    Card:focus { border: round $accent; border-title-color: $accent; background: $boost; }
    Card.blocked { border: round $error 60%; }
    Card.blocked:focus { border: round $error; }
    #hint { margin: 0 2; color: $text-muted; }
    Confirm { align: center middle; }
    #dialog { width: 50; height: auto; padding: 1 2; border: round $warning; background: $surface; }
    #dialog Horizontal { height: auto; margin-top: 1; }
    #dialog Button { margin-right: 2; }
    """
    BINDINGS: ClassVar = [
        Binding("enter", "start", "start"),
        Binding("l", "login", "login"),
        Binding("r", "reset", "reset"),
        Binding("q", "quit", "quit"),
        Binding("right,down,tab", "move(1)", show=False, priority=True),
        Binding("left,up,shift+tab", "move(-1)", show=False, priority=True),
    ]

    def __init__(self, home: Path, state: Path, claude: str, result: Path | None) -> None:
        super().__init__()
        self.home, self.state, self.claude, self.result = home, state, claude, result
        self.logins = {acct: Login() for acct in ACCOUNTS}
        self.accounts: list[Account] = []
        self.theme = "tokyo-night"

    def compose(self) -> ComposeResult:
        with Horizontal(id="top"):
            yield Static("aisw", id="name")
            yield Static("", id="clock")
        with Grid(id="cards"):
            for acct in ACCOUNTS:
                yield Card(acct)
        yield Static(
            "[b]←→[/] select   [b]⏎[/] start   [b]l[/] login (asks first)   [b]r[/] reset limit   [b]q[/] quit", id="hint"
        )

    def on_mount(self) -> None:
        self.refresh_cards()
        self.query_one("#card-a", Card).focus()
        self.set_interval(5, self.refresh_cards)
        self.run_worker(self.load_logins, thread=True)

    def on_resize(self) -> None:
        self.query_one("#cards").set_class(self.size.width < 90, "narrow")

    def load_logins(self) -> None:
        for acct in ACCOUNTS:
            self.logins[acct] = read_login(acct, self.home, self.claude)
        self.call_from_thread(self.refresh_cards)

    def refresh_cards(self) -> None:
        now = time.time()
        self.accounts = [read_account(acct, self.state, self.logins[acct], now) for acct in ACCOUNTS]
        nxt = next((a.name for a in self.accounts if a.blocked_until is None), None)
        for a in self.accounts:
            card = self.query_one(f"#card-{a.name}", Card)
            card.update(card_text(a, a.name == nxt, now))
            card.set_class(a.blocked_until is not None, "blocked")
        self.query_one("#clock", Static).update(f"⏱  {time.strftime('%a %H:%M')}")

    @property
    def selected(self) -> Account:
        focused = self.focused
        acct = focused.acct if isinstance(focused, Card) else "a"
        return next(a for a in self.accounts if a.name == acct)

    def action_move(self, step: int) -> None:
        if isinstance(self.screen, Confirm):
            self.screen.focus_next() if step > 0 else self.screen.focus_previous()
            return
        i = ACCOUNTS.index(self.selected.name)
        self.query_one(f"#card-{ACCOUNTS[(i + step) % len(ACCOUNTS)]}", Card).focus()

    def finish(self, action: str) -> None:
        if self.result:
            self.result.write_text(f"{action} {self.selected.name}\n")
        self.exit()

    def action_start(self) -> None:
        self.finish("start")

    def action_login(self) -> None:
        acct = self.selected
        if not acct.login.email:
            self.finish("login")
            return

        def done(yes: bool | None) -> None:
            if yes:
                self.finish("login")

        self.push_screen(Confirm(f"{acct.name.upper()} is signed in as {acct.login.email}. Log in again?"), done)

    def action_reset(self) -> None:
        acct = self.selected.name
        limit = self.state / f"{acct}.limit"
        if not limit.exists():
            self.notify(f"{acct.upper()} has no limit mark.")
            return

        def done(yes: bool | None) -> None:
            if yes:
                limit.unlink(missing_ok=True)
                self.refresh_cards()
                self.notify(f"{acct.upper()} limit cleared.")

        self.push_screen(Confirm(f"Clear the limit mark of {acct.upper()}?"), done)


def main() -> None:
    home = Path.home()
    state = Path(os.environ.get("AISW_STATE", home / ".aisw"))
    state.mkdir(parents=True, exist_ok=True)
    result = os.environ.get("AISW_UI_RESULT")
    claude = os.environ.get("AISW_CLAUDE", "claude")
    AiswUI(home, state, claude, Path(result) if result else None).run()


if __name__ == "__main__":
    main()
