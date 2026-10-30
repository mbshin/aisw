# clsw how-to

Step-by-step guides. For what clsw is, see the [README](../README.md).

| # | Guide |
|---|---|
| 1 | [Install](#1-install) |
| 2 | [Set up the accounts](#2-set-up-the-accounts) |
| 3 | [Log in](#3-log-in) |
| 4 | [Turn it on](#4-turn-it-on) |
| 5 | [Everyday use](#5-everyday-use) |
| 6 | [When a limit is hit](#6-when-a-limit-is-hit) |
| 7 | [The dashboard](#7-the-dashboard) |
| 8 | [Try a switch without waiting for a limit](#8-try-a-switch-without-waiting-for-a-limit) |
| 9 | [Troubleshooting](#9-troubleshooting) |
| 10 | [Update and uninstall](#10-update-and-uninstall) |

## 1. Install

```zsh
brew install mbshin/tools/clsw
```

This also installs `jq` (used by the scripts) and `uv` (runs the dashboard). Check:

```zsh
clsw status
# A: free (no usage seen yet)
# B: free (no usage seen yet)
# C: free (no usage seen yet)
```

## 2. Set up the accounts

```zsh
clsw setup
```

| It does | Detail |
|---|---|
| Makes `~/.claude-a`, `~/.claude-b`, `~/.claude-c` | One Claude Code config folder per account |
| Links `projects`, `settings.json`, `skills`, `plugins` in each to `~/.claude` | Shared history, memory, settings |
| Adds to `~/.claude/settings.json` (backup first) | `statusLine` → clsw's status line; a `StopFailure` hook, matcher `rate_limit` → clsw's limit hook |

Your existing `~/.claude` login stays as it is; plain Claude Code keeps working.

## 3. Log in

```zsh
clsw login
```

For each account that isn't logged in yet, clsw opens the sign-in page in a **new, empty Chrome
window** (a throwaway profile). Sign in with the account for that slot and approve; the window closes
by itself.

> **Why an empty profile?** The sign-in page reuses whatever account your browser is already signed in
> to, and even Incognito windows share one login while any of them is open. Without this, every slot
> ends up with the same account.

Check that the accounts differ:

```zsh
clsw who
# A: you@work.example · Work Inc (Claude Team account)
# B: you@home.example · personal (Claude Max account)
# C: you@side.example · Side Co (Claude Team account)
```

Wrong account in a slot? `clsw login b` redoes just that one.

## 4. Turn it on

```zsh
echo 'alias claude=clsw' >> ~/.zshrc
exec zsh
claude --dry-run     # CLAUDE_CONFIG_DIR=/Users/you/.claude-a claude
```

Inside the wrapper `claude` still means the real Claude Code, so nothing loops.

## 5. Everyday use

| Want | Type |
|---|---|
| Start | `claude` |
| Continue the last conversation | `claude --continue` |
| A specific account | `claude b`, `claude b --resume` |
| Which account am I on? | Status line: `A`, or `B · 5h 72% · 7d 40%` |
| Overview | `clsw status`, `clsw ui` |
| Without clsw | `command claude` |

Order of preference is A → B → C: put the account you want to use up first in A.

## 6. When a limit is hit

1. Claude Code shows its usage-limit message; you get a notification:
   *"Account A hit its limit (resets Thu 18:00). Type /exit to go on in the next account."*
2. Type `/exit`.
3. clsw prints *"A hit its limit. Going on in B in 3s (Ctrl+C to stop)..."*
4. B resumes the same conversation and is told to check `git status` / `git diff` and continue.

All used up? clsw stops, prints each reset time and the `--resume` command for later.

When the plan reports usage, the status line warns early: ⚠ at 80%, a notification at 90% ("good time to
commit"), and the account counts as used up at 95% (5h) or 98% (7 days), so the next `claude` starts
elsewhere before the hard stop.

## 7. The dashboard

```zsh
clsw ui
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
mkdir -p ~/clsw-trial && cd ~/clsw-trial
clsw -n clsw-trial                     # Terminal 1: say "remember the word mango"
```

In a second terminal, pretend A just hit its limit in that session:

```zsh
clsw test-hit a ~/clsw-trial
```

Back in the session, type `/exit`. It goes on in B; ask *"what word did I ask you to remember?"*.
Clean up with `clsw ui` → `r` on A, or `rm ~/.clsw/a.limit`.

## 9. Troubleshooting

| Symptom | Fix |
|---|---|
| `clsw who` shows the same account twice | `clsw login <x>` and sign in with the right account |
| Account wrongly "used up" | `clsw ui` → `r`, or `rm ~/.clsw/<x>.limit` |
| No switch after `/exit` | Was there a notification? `jq '.hooks.StopFailure' ~/.claude/settings.json` must list clsw's `on-limit.sh` |
| Session not found on the next account | `ls -l ~/.claude-b/projects` must point to `~/.claude/projects` |
| Status line shows only `A` | No reply yet in this session, or your plan sends no usage numbers |
| Everything odd | `rm -rf ~/.clsw` (state only), then `command claude` |

## 10. Update and uninstall

```zsh
brew upgrade clsw
```

Uninstall:

```zsh
clsw unsetup              # removes the status line + hook (backup first) and the alias line
brew uninstall clsw
rm -rf ~/.clsw            # state
# optional: log out and remove the account folders
for x in a b c; do CLAUDE_CONFIG_DIR=~/.claude-$x claude auth logout; done
rm -rf ~/.claude-a ~/.claude-b ~/.claude-c
```

Plain `claude` with `~/.claude` worked the whole time and keeps working.
