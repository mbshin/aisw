<div align="center">

# aisw

**One list of AI accounts: Claude Code, Codex, Antigravity. Pick one, start it.**

Like `conda activate` for your AI coding agents: several Claude accounts, ChatGPT/Codex logins and
Antigravity in one list, with their usage, and one command to start whichever is current.

`brew install mbshin/tools/aisw`

</div>

```
$ aisw list
  NAME   TOOL    LOGIN                    PLAN   STATE              5H    7D
  a      claude  you@work.example         Team   used up → 18:00    96%   41%
* b      claude  you@home.example         Max    free               12%   34%
  c      codex   ChatGPT                  -      signed in          -     -
  d      agy     Google                   -      signed in          -     -

$ aisw activate a      # make a the current account (this shell and new ones)
$ aisw                 # start it: claude, codex or agy, with that account's login
```

## Commands

| Command | Does |
|---|---|
| `aisw [options]` | Start the current account's AI CLI (`claude`, `codex`, `agy`); options pass through: `aisw --continue` |
| `aisw list` | Every account: login, plan, state, 5h / 7d usage; `*` = current. In a terminal it's a dashboard (←→ select, `a` activate, `enter` start, `l` login, `n` add, `d` remove, `q` quit); piped, a plain table |
| `aisw add claude\|codex\|agy [name]` | New account (next free letter, or the name), signed in right away in an Incognito window |
| `aisw login <name>` | Sign an account in again |
| `aisw remove <name>` | Take an account off the list (its folder and login stay) |
| `aisw activate <name>` | Make it the current account of this shell and of new shells; plain `claude` / `codex` use it too |
| `aisw deactivate` | No current account: plain `claude` / `codex` use their own login again |
| `aisw help` | The commands |

Tab completion (zsh) completes the commands, account names (with tool and email) and tools.

## When a limit hits

The [status line](https://code.claude.com/docs/en/statusline) shows the account and its usage
(`b · 5h 72% · 7d 40%`, ⚠ at 80%, a notification at 90%). When a Claude account hits its limit, a
notification names the next free one:

```
Account a hit its limit (resets Thu 18:00). Next free: b → /exit, aisw activate b, aisw --continue
```

All Claude accounts share their conversations, so `aisw --continue` picks up the same one on b.

## Requirements

| Need | Why | Install |
|---|---|---|
| **macOS** + [Homebrew](https://brew.sh) | Installed with brew; notifications use macOS | – |
| At least one of: **Claude Code**, **Codex**, **Antigravity CLI** (`agy`) | The AI CLIs aisw starts | `brew install --cask claude-code` · `brew install --cask codex` · `brew install --cask antigravity-cli` |
| Google Chrome (recommended) | Claude sign-ins open in an empty Incognito profile, so the wrong account is never reused | – |
| `jq`, `uv` | Scripts, the dashboard | Installed with aisw |

> **Why Antigravity and not Gemini CLI?** Since 18 June 2026 Gemini CLI no longer serves personal Google
> accounts; Google moved them to Antigravity CLI.

## Quick start

```bash
brew install mbshin/tools/aisw
aisw add claude        # a: the first add also sets up the status line, limit hook and a ~/.zshrc line
aisw add claude        # b
aisw add codex         # c
# open a new terminal (for the ~/.zshrc line), then:
aisw activate a
aisw
```

Step by step: **[docs/HOWTO.md](docs/HOWTO.md)**.

## How it works

- `~/.aisw/accounts` holds one line per account: `name tool folder`.
- A Claude account is a Claude Code config folder (`CLAUDE_CONFIG_DIR`) with its own login;
  `projects/`, `settings.json`, `skills/` and `plugins/` are symlinks to `~/.claude`, so conversations
  and settings are shared. A Codex account is a `CODEX_HOME` folder (the first one is `~/.codex`).
  Antigravity has one login for now.
- `aisw activate` sets `CLAUDE_CONFIG_DIR` or `CODEX_HOME` in your shell. A program can't change its
  parent shell, so (like `conda init`) aisw adds one line to `~/.zshrc`:
  `command -v aisw >/dev/null && eval "$(aisw shell-init zsh)"`. Without it:
  `eval "$(aisw activate b)"`.
- A [`StopFailure`](https://code.claude.com/docs/en/hooks) hook with matcher `rate_limit` marks a Claude
  account used up and names the next free one; the status line records usage so `aisw list` can show it.

## Upgrading from 1.x

The first 2.x run turns your accounts into the list: A, B, C keep their names and folders
(`~/.claude-a` …), a signed-in Codex and Antigravity become the next letters. No logins are lost.
`aisw claude`, the automatic switch, the Codex/Antigravity handoff, `who`, `status`, `ui`, `resume`,
`setup` and `unsetup` are gone: `aisw list` shows everything, `aisw activate` + `aisw` start an account.
To remove aisw's settings by hand: delete `statusLine` and the `StopFailure` hook from
`~/.claude/settings.json` (a backup is kept) and the aisw line from `~/.zshrc`.

## Use responsibly

Having several accounts is normal (work and personal, for example); using extra accounts only to get
around usage limits may go against your plan's terms. Check the terms of each plan you use. If your
organization offers **extra usage**, that is the official way to keep going past a limit.

`aisw` is a personal tool, **not made by or affiliated with Anthropic, OpenAI or Google**. It uses only
the tools' documented features and never reads, copies or writes login tokens.

## License

MIT
