<div align="center">

# clsw

**Claude switch: keep coding when a Claude account hits its usage limit.**

When one account runs out, the same Claude Code conversation goes on in the next free one.
No token juggling, no copy-pasting context, only built-in Claude Code features.

`brew install mbshin/tools/clsw`

</div>

```
 clsw · Claude accounts                                  Fri 10:15:42
 ┌───┬────────────────────────┬──────────┬──────┬────────────┬────────────┬───────────────┐
 │   │ Account                │ Owner    │ Plan │ 5h         │ 7d         │ State         │
 ├───┼────────────────────────┼──────────┼──────┼────────────┼────────────┼───────────────┤
 │ A │ you@work.example       │ Work Inc │ Team │ –          │ –          │ ○ until 14:41 │
 │ B │ you@home.example       │ personal │ Max  │ ███▌░  72% │ █▊░░░  40% │ ● free  next  │
 │ C │ you@side.example       │ Side Co  │ Team │ –          │ –          │ ● free        │
 └───┴────────────────────────┴──────────┴──────┴────────────┴────────────┴───────────────┘
  enter start claude   l login   r reset limit   q quit
```

## Why

Claude Code stops when your plan's 5-hour or weekly limit is reached. If you have more than one
account (say a work seat and a personal plan), switching by hand means logging out, logging in and
finding your conversation again. `clsw` does that for you:

```
(notification) Account A hit its limit (resets Thu 18:00). Type /exit to go on in the next account.
> /exit
A hit its limit. Going on in B in 3s (Ctrl+C to stop)...
```

Account B opens **the same conversation**, checks `git status` for half-done work, and carries on.

## Features

| | |
|---|---|
| 🔁 **Seamless handoff** | Limit hit → `/exit` → same session resumes on the next free account |
| 📊 **Usage in the status line** | `B · 5h 72% · 7d 40%`, ⚠ at 80%, a notification at 90% (when the plan reports usage) |
| 🖥️ **Dashboard** | `clsw ui`: all accounts, usage bars, limits; start, log in, reset with one key |
| 🔎 **Find any conversation** | `clsw resume`: fzf over every past session, in every folder |
| 🔑 **Safe logins** | `clsw login` signs in through a throwaway browser profile, so the wrong account is never reused |
| 🧩 **Shared everything** | Settings, skills, plugins, memory and session history are shared by all accounts |
| 🪶 **Small and readable** | A few hundred lines of bash plus one Python file; never touches login tokens |

## Quick start

```zsh
brew install mbshin/tools/clsw
clsw setup                   # makes ~/.claude-a, -b, -c and adds the status line + limit hook
clsw login                   # log in to each account (throwaway browser window)
clsw who                     # A: you@work.example · Work Inc (Claude Team account) / …
echo 'alias claude=clsw' >> ~/.zshrc && exec zsh
claude                       # starts on the first free account, as usual
```

Full guide: **[docs/HOWTO.md](docs/HOWTO.md)**.

## `claude` or `clsw`?

Same program. `clsw` is the tool; the alias `claude=clsw` lets you keep typing `claude` out of habit.

| You type | What runs |
|---|---|
| `claude` | `clsw` (alias): picks a free account, then starts the real Claude Code |
| `clsw` | The same, also without the alias |
| `command claude` | The real Claude Code, no switching |

**Start Claude with `claude`, manage accounts with `clsw`.** No alias? Use `clsw` for both.

## Commands

| Start Claude | |
|---|---|
| `claude` | First free account, A → B → C |
| `claude a` · `claude b` · `claude c` | Force an account |
| `claude --continue`, `--resume`, `-n name` | All normal options pass through |

| Manage accounts | |
|---|---|
| `clsw who` | Login, owner and plan of each account |
| `clsw status` | Free, or used up until when |
| `clsw ui` | Dashboard |
| `clsw resume [words]` | Fuzzy-find any past conversation (all folders) and resume it on a free account |
| `clsw login [a\|b\|c]` | Log in to every missing account, or one |
| `clsw help` | All commands |

**free** = not at its limit, so `claude` may use it. **no usage seen yet** = no session ran on it
yet (numbers arrive after the first reply).

## How it works

```
 claude (alias) ──► clsw ──► CLAUDE_CONFIG_DIR=~/.claude-a claude
                                   │
            status line ◄──────────┤  usage % → ~/.clsw/a.usage.json
            StopFailure hook ◄─────┘  rate_limit → ~/.clsw/a.limit + handoff.json
                                   │
                         you type /exit
                                   ▼
                  clsw ──► CLAUDE_CONFIG_DIR=~/.claude-b claude --resume <session> "<continue>"
```

- Each account is a Claude Code config folder (`CLAUDE_CONFIG_DIR`) with its own login; `projects/`,
  `settings.json`, `skills/` and `plugins/` are symlinks to `~/.claude`, so `--resume` works across them.
- A [`StopFailure`](https://code.claude.com/docs/en/hooks) hook with matcher `rate_limit` marks the
  account used up and leaves a handoff note. The wrapper reads it after `/exit` and resumes.
- The [status line](https://code.claude.com/docs/en/statusline) records `rate_limits` so an account
  can count as used up *before* the hard stop (95% of 5h, 98% of 7d).

## Limits

- **Usage numbers depend on the plan.** Claude Code documents them for Pro/Max; Team seats sent them
  too in testing. Without numbers, clsw switches on the real limit hit and guesses a 5-hour reset.
- **One `/exit` is needed.** A running session can't change account; the turn that hit the limit is
  repeated by the resume prompt.
- **macOS first.** Notifications use `osascript`; the throwaway sign-in window uses Chrome if installed.

## Use responsibly

Having several accounts is normal (work and personal, for example); using extra accounts only to get
around usage limits may go against your plan's terms. Check the terms of each plan you use. If your
organization offers **extra usage**, that is the official way to keep going past a limit.

`clsw` is a personal tool, **not made by or affiliated with Anthropic**. It uses only documented
Claude Code features and never reads, copies or writes login tokens.

## License

MIT
