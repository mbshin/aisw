<div align="center">

# aisw

**AI switch: keep coding when an AI agent hits its usage limit.**

When one Claude account runs out, the same conversation goes on in the next free one.
When all of them are out, it can hand the work to **Codex** or **Antigravity** (Google's Gemini agent).
No token juggling, no copy-pasting context, only built-in Claude Code features.

`brew install mbshin/tools/aisw`

</div>

```
 aisw · Claude accounts                                  Fri 10:15:42
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
finding your conversation again. `aisw` does that for you:

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
| 🤝 **Codex and Antigravity fallbacks** | Every Claude account used up? Opt in and aisw hands the task to Codex or Antigravity with a handoff note |
| 📊 **Usage in the status line** | `B · 5h 72% · 7d 40%`, ⚠ at 80%, a notification at 90% (when the plan reports usage) |
| 🖥️ **Dashboard** | `aisw ui`: all accounts, usage bars, limits; start, log in, reset with one key |
| 🔎 **Find any conversation** | `aisw resume`: fzf over every past session, in every folder |
| 🔑 **Safe logins** | `aisw login` (Claude) and `aisw login codex` sign in through a throwaway browser profile, so the wrong account is never reused |
| 🧩 **Shared everything** | Settings, skills, plugins, memory and session history are shared by all accounts |
| 🪶 **Small and readable** | A few hundred lines of bash plus one Python file; never touches login tokens |

## Requirements

| Need | Why | Install |
|---|---|---|
| **macOS** + [Homebrew](https://brew.sh) | aisw is installed with brew; notifications use macOS | – |
| **Claude Code** | The agent aisw switches between accounts | `brew install --cask claude-code` or `curl -fsSL https://claude.ai/install.sh \| bash` |
| **One or more Claude accounts** | Pro, Max, Team or Enterprise; aisw uses up to three (A, B, C) | – |
| Google Chrome (recommended) | Logins open in a throwaway Chrome profile, so the wrong account isn't reused; without Chrome the normal browser opens | – |
| `jq`, `fzf`, `uv` | Scripts, `aisw resume`, the dashboard | Installed with aisw |
| *Optional:* **Codex** + a ChatGPT plan | First fallback when every Claude account is used up | `brew install --cask codex` |
| *Optional:* **Antigravity CLI** (`agy`) + a Google account | Second fallback (Google's Gemini agent) | `brew install --cask antigravity-cli` |

> **Why Antigravity and not Gemini CLI?** Since 18 June 2026 Gemini CLI no longer serves personal Google
> accounts (free, AI Pro, AI Ultra); Google moved them to Antigravity CLI. Gemini CLI still works with a
> paid Gemini API key or a Gemini Code Assist license, but aisw doesn't use it.

How to install and log in to each: **[docs/HOWTO.md §1](docs/HOWTO.md#1-install)**.

## Quick start

```zsh
brew install mbshin/tools/aisw
aisw setup                   # makes ~/.claude-a, -b, -c and adds the status line + limit hook
aisw login                   # log in to each account (throwaway browser window)
aisw who                     # A: you@work.example · Work Inc (Claude Team account) / …
aisw claude                  # starts Claude on the first free account
aisw                         # dashboard of all accounts
# optional: echo "alias claude='aisw claude'" >> ~/.zshrc   (keep typing `claude`)
```

Full guide: **[docs/HOWTO.md](docs/HOWTO.md)**.

## `aisw` and the agents

**`aisw` is the manager; an agent's name starts that agent.** `claude`, `codex` and `agy` stay the plain
tools.

| You type | What runs |
|---|---|
| `aisw` | The dashboard (same as `aisw ui`) |
| `aisw claude` | Picks a free account, then starts the real Claude Code |
| `aisw codex` · `aisw agy` | Hands this folder's newest Claude session to Codex / Antigravity |
| `claude`, `codex`, `agy` | The plain tools, no switching |

Optional: `alias claude='aisw claude'` lets you keep typing `claude`. Old forms still work: `aisw a`,
`aisw --resume …` (any args that start with `-`) mean `aisw claude …`; only plain `aisw` changed in 1.2.0.

## Commands

| Start Claude | |
|---|---|
| `aisw claude` | First free account, A → B → C |
| `aisw claude a` · `b` · `c` | Force an account |
| `aisw claude --continue`, `--resume`, `-n name` | All normal options pass through |
| `aisw claude --dry-run` | Print which account would start |

| Manage accounts | |
|---|---|
| `aisw who` | Login, owner and plan of each account |
| `aisw status` | Free, or used up until when |
| `aisw` · `aisw ui` | Dashboard |
| `aisw resume [words]` | Fuzzy-find any past conversation (all folders) and resume it on a free account |
| `aisw login [a\|b\|c]` | Log in to every missing account, or one |
| `aisw login codex` | Log in to Codex (one-time code in an empty browser window) |
| `aisw login agy` | Log in to Antigravity (signs in on its first start) |
| `aisw help` | All commands |

**free** = not at its limit, so `aisw claude` may use it. **no usage seen yet** = no session ran on it
yet (numbers arrive after the first reply).

## Fallbacks: Codex and Antigravity (opt-in)

```zsh
aisw login codex             # ChatGPT account → Codex becomes a fallback
aisw login agy               # Google account → Antigravity becomes a fallback
```

One step each: a successful login also puts the tool on the fallback list. When every Claude account is
used up, aisw asks for each fallback in the order you logged them in:
**"Continue in Codex? [y/N]"**, then **"Continue in Antigravity? [y/N]"**. On yes it writes a handoff note
(first request, last five requests, Claude's last message, `git status` / `git diff --stat`) to a temp file
and starts the tool in the same folder (`codex "<prompt>"`, `agy -i "<prompt>"`), told to read it, check git
and continue. The note is deleted when the tool exits. `aisw codex` and `aisw agy` do the same on demand.
Neither can read Claude's conversation, so they work from the note and the files, not the full history.
Off again: `aisw unsetup --codex` / `--agy`.

## How it works

```
 claude (alias) ──► aisw claude ──► CLAUDE_CONFIG_DIR=~/.claude-a claude
                                          │
            status line ◄─────────────────┤  usage % → ~/.aisw/a.usage.json
            StopFailure hook ◄────────────┘  rate_limit → ~/.aisw/a.limit + handoff.json
                                          │
                                you type /exit
                                          ▼
                  aisw claude ──► CLAUDE_CONFIG_DIR=~/.claude-b claude --resume <session> "<continue>"
```

- Each account is a Claude Code config folder (`CLAUDE_CONFIG_DIR`) with its own login; `projects/`,
  `settings.json`, `skills/` and `plugins/` are symlinks to `~/.claude`, so `--resume` works across them.
- A [`StopFailure`](https://code.claude.com/docs/en/hooks) hook with matcher `rate_limit` marks the
  account used up and leaves a handoff note. The wrapper reads it after `/exit` and resumes.
- The [status line](https://code.claude.com/docs/en/statusline) records `rate_limits` so an account
  can count as used up *before* the hard stop (95% of 5h, 98% of 7d).

## Limits

- **Usage numbers depend on the plan.** Claude Code documents them for Pro/Max; Team seats sent them
  too in testing. Without numbers, aisw switches on the real limit hit and guesses a 5-hour reset.
- **One `/exit` is needed.** A running session can't change account; the turn that hit the limit is
  repeated by the resume prompt.
- **macOS first.** Notifications use `osascript`; the throwaway sign-in window uses Chrome if installed.

## Use responsibly

Having several accounts is normal (work and personal, for example); using extra accounts only to get
around usage limits may go against your plan's terms. Check the terms of each plan you use. If your
organization offers **extra usage**, that is the official way to keep going past a limit.

`aisw` is a personal tool, **not made by or affiliated with Anthropic**. It uses only documented
Claude Code features and never reads, copies or writes login tokens.

## Renamed from clsw

Until 1.0.1 this was `clsw` (Claude switch). Moving over keeps your logins (they live in `~/.claude-a` …):
`brew uninstall clsw && brew install mbshin/tools/aisw && aisw setup`, then change `alias claude=clsw` to
`alias claude='aisw claude'`. `~/.clsw` moves to `~/.aisw` on first run.

## License

MIT
