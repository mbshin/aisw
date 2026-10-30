#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["textual>=8.0"]
# ///
"""aisw list: one screen for every account (Claude Code, Codex, Antigravity).

Reads ~/.aisw/accounts and each tool's own status command; never reads login tokens. Starting, activating,
signing in, adding and removing need the shell or the whole terminal, so the TUI quits and writes
"launch <x>", "activate <x>", "login <x>", "remove <x>" or "add" to the file named by AISW_UI_RESULT;
the aisw wrapper runs it.
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

# Same rules as common.sh: used up at 5h >= 95% or 7d >= 98%, or until the time in <x>.limit.
FIVE_FULL = 95
SEVEN_FULL = 98
WARN = 80
TOOL_LABEL = {"claude": "Claude Code", "codex": "Codex", "agy": "Antigravity"}


@dataclass
class Login:
    email: str = ""
    plan: str = ""
    org: str = ""
    signed_in: bool = False


@dataclass
class Account:
    name: str
    tool: str
    folder: str
    login: Login
    five: float | None = None
    seven: float | None = None
    blocked_until: int | None = None


def read_accounts(state: Path) -> list[tuple[str, str, str]]:
    """(name, tool, folder) per line of the accounts file, in list order."""
    path = state / "accounts"
    if not path.exists():
        return []
    rows = []
    for line in path.read_text().splitlines():
        parts = line.split(" ", 2)
        if len(parts) == 3:
            rows.append((parts[0], parts[1], parts[2]))
    return rows


def run_quiet(cmd: list[str], env: dict[str, str]) -> subprocess.CompletedProcess[str] | None:
    try:
        # Detached from the terminal: the TUI owns it, and the tools would otherwise read from it.
        return subprocess.run(
            cmd,
            env=env,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=20,
            start_new_session=True,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None


def read_login(tool: str, folder: str, bins: dict[str, str]) -> Login:
    env = dict(os.environ)
    if tool == "claude":
        env["CLAUDE_CONFIG_DIR"] = folder
        out = run_quiet([bins["claude"], "auth", "status", "--text"], env)
        fields = dict(line.split(": ", 1) for line in (out.stdout if out else "").splitlines() if ": " in line)
        if "Email" not in fields:
            return Login()
        plan = fields.get("Login method", "").removeprefix("Claude ").removesuffix(" account")
        # A personal plan's organization is named "<email>'s Organization".
        org = fields.get("Organization", "")
        if org.endswith("'s Organization"):
            org = "personal"
        return Login(fields["Email"], plan, org, True)
    if tool == "codex":
        if folder == str(Path.home() / ".codex"):
            env.pop("CODEX_HOME", None)
        else:
            env["CODEX_HOME"] = folder
        out = run_quiet([bins["codex"], "login", "status"], env)
        ok = bool(out) and (out.stdout + out.stderr).lower().startswith("logged in")
        return Login("ChatGPT", signed_in=ok)
    out = run_quiet([bins["agy"], "models"], env)
    return Login("Google", signed_in=bool(out) and out.returncode == 0)


def read_usage(a: Account, state: Path, now: float) -> Account:
    until = 0
    limit = state / f"{a.name}.limit"
    if limit.exists():
        until = int(limit.read_text().strip() or 0)
    usage = state / f"{a.name}.usage.json"
    if usage.exists():
        data = json.loads(usage.read_text())
        five, seven = data.get("five_hour") or {}, data.get("seven_day") or {}
        a.five, a.seven = five.get("used_percentage"), seven.get("used_percentage")
        if (a.five or 0) >= FIVE_FULL:
            until = max(until, int(five.get("resets_at") or 0))
        if (a.seven or 0) >= SEVEN_FULL:
            until = max(until, int(seven.get("resets_at") or 0))
    a.blocked_until = until if until > now else None
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


def card_text(a: Account, is_current: bool, now: float, loaded: bool) -> str:
    if not loaded:
        state = "[dim]…[/]"
    elif not a.login.signed_in:
        state = "[$warning]○ not signed in[/]"
    elif a.blocked_until:
        state = f"[$error]○ used up · {countdown(a.blocked_until, now)}[/]"
    else:
        state = "[$success]● free[/]" if a.tool == "claude" else "[$success]● signed in[/]"
    if is_current:
        state += " · [bold $accent]current[/]"
    who = a.login.email or "[dim]–[/]"
    owner = " · ".join(x for x in (a.login.org, a.login.plan) if x)
    lines = [state, f"[dim]{TOOL_LABEL.get(a.tool, a.tool)}[/]", who, f"[dim]{owner}[/]" if owner else ""]
    if a.tool == "claude":
        if a.five is None and a.seven is None:
            lines.append("[dim]no usage numbers[/]")
        else:
            lines += [f"5h {gauge(a.five)}", f"7d {gauge(a.seven)}"]
    if a.blocked_until:
        lines.append(f"[dim]resets {time.strftime('%a %H:%M', time.localtime(a.blocked_until))}[/]")
    return "\n".join(lines)


class Card(Static, can_focus=True):
    """One account. Focus = selected."""

    def __init__(self, name: str) -> None:
        super().__init__(id=f"card-{name}")
        self.acct = name
        self.border_title = f" {name} "


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
    #cards { grid-size: 3; grid-gutter: 1 2; height: auto; margin: 1 2; }
    #cards.narrow { grid-size: 1; grid-gutter: 1 0; }
    #empty { margin: 1 2; color: $text-muted; }
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
        Binding("enter", "launch", "start"),
        Binding("a", "activate", "activate"),
        Binding("l", "login", "login"),
        Binding("n", "add", "add"),
        Binding("d", "remove", "remove"),
        Binding("q", "quit", "quit"),
        Binding("right,down,tab", "move(1)", show=False, priority=True),
        Binding("left,up,shift+tab", "move(-1)", show=False, priority=True),
    ]

    def __init__(self, state: Path, bins: dict[str, str], current: str, result: Path | None) -> None:
        super().__init__()
        self.state, self.bins, self.current, self.result = state, bins, current, result
        self.rows = read_accounts(state)
        self.logins = {name: Login() for name, _, _ in self.rows}
        self.loaded = False
        self.accounts: list[Account] = []
        self.theme = "tokyo-night"

    def compose(self) -> ComposeResult:
        with Horizontal(id="top"):
            yield Static("aisw", id="name")
            yield Static("", id="clock")
        if not self.rows:
            yield Static("No accounts yet. Press n to add one.", id="empty")
        with Grid(id="cards"):
            for name, _, _ in self.rows:
                yield Card(name)
        yield Static(
            "[b]←→[/] select   [b]⏎[/] start   [b]a[/] activate   [b]l[/] login   [b]n[/] add   [b]d[/] remove"
            "   [b]q[/] quit",
            id="hint",
        )

    def on_mount(self) -> None:
        self.refresh_cards()
        if self.rows:
            first = self.current if self.current in self.logins else self.rows[0][0]
            self.query_one(f"#card-{first}", Card).focus()
        self.set_interval(5, self.refresh_cards)
        self.run_worker(self.load_logins, thread=True)

    def on_resize(self) -> None:
        self.query_one("#cards").set_class(self.size.width < 90, "narrow")

    def load_logins(self) -> None:
        for name, tool, folder in self.rows:
            self.logins[name] = read_login(tool, folder, self.bins)
        self.loaded = True
        self.call_from_thread(self.refresh_cards)

    def refresh_cards(self) -> None:
        now = time.time()
        self.accounts = [
            read_usage(Account(name, tool, folder, self.logins[name]), self.state, now)
            for name, tool, folder in self.rows
        ]
        for a in self.accounts:
            card = self.query_one(f"#card-{a.name}", Card)
            card.update(card_text(a, a.name == self.current, now, self.loaded))
            card.set_class(a.blocked_until is not None, "blocked")
        self.query_one("#clock", Static).update(f"⏱  {time.strftime('%a %H:%M')}")

    @property
    def selected(self) -> Account | None:
        focused = self.focused
        if not isinstance(focused, Card):
            return None
        return next((a for a in self.accounts if a.name == focused.acct), None)

    def action_move(self, step: int) -> None:
        if isinstance(self.screen, Confirm):
            self.screen.focus_next() if step > 0 else self.screen.focus_previous()
            return
        if not self.selected:
            return
        names = [name for name, _, _ in self.rows]
        i = names.index(self.selected.name)
        self.query_one(f"#card-{names[(i + step) % len(names)]}", Card).focus()

    def finish(self, action: str) -> None:
        if self.result:
            self.result.write_text(f"{action}\n")
        self.exit()

    def finish_selected(self, action: str) -> None:
        if self.selected:
            self.finish(f"{action} {self.selected.name}")

    def action_launch(self) -> None:
        self.finish_selected("launch")

    def action_activate(self) -> None:
        self.finish_selected("activate")

    def action_add(self) -> None:
        self.finish("add")

    def action_login(self) -> None:
        acct = self.selected
        if not acct:
            return
        if not acct.login.signed_in:
            self.finish(f"login {acct.name}")
            return

        def done(yes: bool | None) -> None:
            if yes:
                self.finish(f"login {acct.name}")

        who = f" as {acct.login.email}" if acct.tool == "claude" else ""
        self.push_screen(Confirm(f"{acct.name} is signed in{who}. Sign in again?"), done)

    def action_remove(self) -> None:
        acct = self.selected
        if not acct:
            return

        def done(yes: bool | None) -> None:
            if yes:
                self.finish(f"remove {acct.name}")

        self.push_screen(Confirm(f"Remove {acct.name} from the list? (its folder and login stay)"), done)


def main() -> None:
    state = Path(os.environ.get("AISW_STATE", Path.home() / ".aisw"))
    state.mkdir(parents=True, exist_ok=True)
    result = os.environ.get("AISW_UI_RESULT")
    bins = {
        "claude": os.environ.get("AISW_CLAUDE", "claude"),
        "codex": os.environ.get("AISW_CODEX", "codex"),
        "agy": os.environ.get("AISW_AGY", "agy"),
    }
    AiswUI(state, bins, os.environ.get("AISW_CURRENT", ""), Path(result) if result else None).run()


if __name__ == "__main__":
    main()
