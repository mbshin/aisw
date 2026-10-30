# aisw how-to

Step-by-step guides. For what aisw is, see the [README](../README.md).

| # | Guide |
|---|---|
| 1 | [Install: aisw, Claude Code, Codex, Antigravity](#1-install) |
| 2 | [Set up the accounts](#2-set-up-the-accounts) |
| 3 | [Log in](#3-log-in) |
| 4 | [Turn it on](#4-turn-it-on) |
| 5 | [Everyday use](#5-everyday-use) |
| 6 | [When a limit is hit](#6-when-a-limit-is-hit) |
| 7 | [The dashboard](#7-the-dashboard) |
| 8 | [Try a switch without waiting for a limit](#8-try-a-switch-without-waiting-for-a-limit) |
| 9 | [Troubleshooting](#9-troubleshooting) |
| 10 | [Update and uninstall](#10-update-and-uninstall) |
| 11 | [Fallbacks: Codex and Antigravity](#11-fallbacks-codex-and-antigravity) |

## 1. Install

### 1.1 aisw

```zsh
brew install mbshin/tools/aisw
```

This also installs `jq` (scripts), `fzf` (`aisw resume`) and `uv` (runs the dashboard). Check:

```zsh
aisw status
# A: free (no usage seen yet)
# B: free (no usage seen yet)
# C: free (no usage seen yet)
```

### 1.2 Claude Code (required)

```zsh
brew install --cask claude-code                 # or: curl -fsSL https://claude.ai/install.sh | bash
claude --version
```

You need at least one Claude account (Pro, Max, Team or Enterprise); aisw uses up to three. You log
them in with aisw in step 3, not with `claude` itself.

### 1.3 Codex (optional fallback)

```zsh
brew install --cask codex
aisw login codex                                # one-time code shown in Terminal; also turns on the fallback
```

Needs a ChatGPT plan. The code sign-in must be allowed once: chatgpt.com → profile → **Settings →
Security** → turn on **device code sign-in** (on a Business/Enterprise workspace only the admin can).
If it's off, `aisw login codex` says so and falls back to the normal browser login.

### 1.4 Antigravity CLI (optional fallback, Google's Gemini agent)

```zsh
brew install --cask antigravity-cli             # the command is `agy`
aisw login agy                                  # sign in with Google, quit agy (Ctrl+C); also turns on the fallback
```

**Not Gemini CLI:** since 18 June 2026 Gemini CLI no longer serves personal Google accounts (free,
AI Pro, AI Ultra). Google moved them to Antigravity CLI. Gemini CLI (`brew install gemini-cli`) still
works only with a paid Gemini API key or a Gemini Code Assist license, and aisw doesn't use it.

## 2. Set up the accounts

```zsh
aisw setup
```

| It does | Detail |
|---|---|
| Makes `~/.claude-a`, `~/.claude-b`, `~/.claude-c` | One Claude Code config folder per account |
| Links `projects`, `settings.json`, `skills`, `plugins` in each to `~/.claude` | Shared history, memory, settings |
| Adds to `~/.claude/settings.json` (backup first) | `statusLine` → aisw's status line; a `StopFailure` hook, matcher `rate_limit` → aisw's limit hook |

Your existing `~/.claude` login stays as it is; plain Claude Code keeps working.

## 3. Log in

```zsh
aisw login
```

For each account that isn't logged in yet, aisw opens the sign-in page in a **new, empty Chrome
window** (a throwaway profile). Sign in with the account for that slot and approve; the window closes
by itself.

> **Why an empty profile?** The sign-in page reuses whatever account your browser is already signed in
> to, and even Incognito windows share one login while any of them is open. Without this, every slot
> ends up with the same account.

Check that the accounts differ:

```zsh
aisw who
# A: you@work.example · Work Inc (Claude Team account)
# B: you@home.example · personal (Claude Max account)
# C: you@side.example · Side Co (Claude Team account)
```

Wrong account in a slot? `aisw login b` redoes just that one.

## 4. Turn it on

```zsh
aisw claude --dry-run     # CLAUDE_CONFIG_DIR=/Users/you/.claude-a claude
aisw claude               # start
```

Optional: `echo "alias claude='aisw claude'" >> ~/.zshrc` lets you keep typing `claude` (inside aisw,
`claude` still means the real Claude Code, so nothing loops). Without the alias, read `claude` in this guide
as `aisw claude`. Plain `aisw` opens the dashboard.

## 5. Everyday use

| Want | Type |
|---|---|
| Start | `aisw claude` |
| Continue the last conversation | `aisw claude --continue` |
| A specific account | `aisw claude b`, `aisw claude b --resume` |
| Which account am I on? | Status line: `A`, or `B · 5h 72% · 7d 40%` |
| Overview | `aisw` (dashboard), `aisw status` |
| Without aisw | `claude` (no alias) or `command claude` |

Order of preference is A → B → C: put the account you want to use up first in A.

## 6. When a limit is hit

1. Claude Code shows its usage-limit message; you get a notification:
   *"Account A hit its limit (resets Thu 18:00). Type /exit to go on in the next account."*
2. Type `/exit`.
3. aisw prints *"A hit its limit. Going on in B in 3s (Ctrl+C to stop)..."*
4. B resumes the same conversation and is told to check `git status` / `git diff` and continue.

All used up? aisw stops, prints each reset time and the `--resume` command for later.

When the plan reports usage, the status line warns early: ⚠ at 80%, a notification at 90% ("good time to
commit"), and the account counts as used up at 95% (5h) or 98% (7 days), so the next `claude` starts
elsewhere before the hard stop.

## 7. The dashboard

```zsh
aisw          # or aisw ui
```

| Key | Does |
|---|---|
| `↑` `↓` | Select an account |
| `enter` | Start Claude Code on it (in the current folder) |
| `l` | Log in to it (empty browser window), then back to the dashboard |
| `r` | Clear its limit mark (asks first) |
| `q` | Quit |

It refreshes every 5 seconds. Usage gauges appear once an account has sent usage numbers.

## 8. Try a switch without waiting for a limit

```zsh
mkdir -p ~/aisw-trial && cd ~/aisw-trial
aisw claude -n aisw-trial              # Terminal 1: say "remember the word mango"
```

In a second terminal, pretend A just hit its limit in that session:

```zsh
aisw test-hit a ~/aisw-trial
```

Back in the session, type `/exit`. It goes on in B; ask *"what word did I ask you to remember?"*.
Clean up with `aisw ui` → `r` on A, or `rm ~/.aisw/a.limit`.

## 9. Troubleshooting

| Symptom | Fix |
|---|---|
| `aisw who` shows the same account twice | `aisw login <x>` and sign in with the right account |
| Account wrongly "used up" | `aisw ui` → `r`, or `rm ~/.aisw/<x>.limit` |
| No switch after `/exit` | Was there a notification? `jq '.hooks.StopFailure' ~/.claude/settings.json` must list aisw's `on-limit.sh` |
| Session not found on the next account | `ls -l ~/.claude-b/projects` must point to `~/.claude/projects` |
| Status line shows only `A` | No reply yet in this session, or your plan sends no usage numbers |
| Everything odd | `rm -rf ~/.aisw` (state only), then `command claude` |

## 10. Update and uninstall

```zsh
brew upgrade aisw
```

Uninstall:

```zsh
aisw unsetup              # removes the status line + hook (backup first) and the alias line
brew uninstall aisw
rm -rf ~/.aisw            # state
# optional: log out and remove the account folders
for x in a b c; do CLAUDE_CONFIG_DIR=~/.claude-$x claude auth logout; done
rm -rf ~/.claude-a ~/.claude-b ~/.claude-c
```

Plain `claude` with `~/.claude` worked the whole time and keeps working.

## 11. Fallbacks: Codex and Antigravity

Logging in (§1.3, §1.4) turns each one on; they're offered in the order you logged them in.

```zsh
aisw who          # last lines: "Codex (fallback): Logged in using ChatGPT", "Antigravity (fallback): Logged in"
```

`aisw setup --codex` / `--agy` turn one on without a new login (if it's already signed in).

| Situation | What happens |
|---|---|
| Last free Claude account hits its limit, you type `/exit` | "All Claude accounts are used up. Continue in Codex? [y/N]"; on no: "Continue in Antigravity? [y/N]" |
| You start `aisw claude` while all are used up | Same questions |
| `aisw codex` · `aisw agy` | Hand this folder's newest Claude session over now |

The handoff note holds the first request, the last five, Claude's last message and the git state. Codex
gets it as its first prompt (`codex "<prompt>"`), Antigravity too (`agy -i "<prompt>"`). When a Claude
account is free again, `aisw resume` brings you back to the Claude conversation; it checks `git diff` for
what the other tool changed. Turn one off with `aisw unsetup --codex` or `--agy`.
