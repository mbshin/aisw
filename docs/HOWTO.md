# aisw how-to (2.x)

## 1. Install

```bash
brew install mbshin/tools/aisw     # brings jq and uv
aisw --version
```

Then install at least one AI CLI:

| Tool | Install | Account |
|---|---|---|
| Claude Code | `brew install --cask claude-code` | Pro, Max, Team or Enterprise |
| Codex | `brew install --cask codex` | A ChatGPT plan |
| Antigravity CLI (`agy`) | `brew install --cask antigravity-cli` | A Google account |

## 2. Add accounts

```bash
aisw add claude          # a
aisw add claude work     # or pick the name
aisw add codex
aisw add agy
```

Each `add` signs in right away and only signs in (the tool's chat screen doesn't open):

| Tool | Sign-in |
|---|---|
| Claude | `claude auth login` in an empty Chrome profile in Incognito, email filled in; the window closes after |
| Codex | `codex login` in your normal browser (its sign-in didn't finish in an empty profile) |
| Antigravity | `agy` starts once and quits by itself after you sign in |

If you cancel, nothing is added. The **first** `add` (or `login`) asks once to set up:

- the status line and limit hook in `~/.claude/settings.json` (a backup is kept), shared by every Claude account;
- one line in `~/.zshrc` so `aisw activate` can change your shell. **Open a new terminal** afterwards.

## 3. Daily use

```bash
aisw list                # dashboard; piped: a table
aisw activate b          # b is current here and in new terminals
aisw                     # starts b's CLI (claude / codex / agy)
aisw --continue          # options go to the CLI (Codex: becomes `codex resume --last`)
```

Plain `claude` and `codex` use the current account too. `aisw deactivate` goes back to their own login.

Tab completion: `aisw <Tab>`, `aisw activate <Tab>` (names with tool and email), `aisw add <Tab>`.

## 4. When a limit hits

A notification says which Claude account is free next:

```
Account a hit its limit (resets Thu 18:00). Next free: b → /exit, aisw activate b, aisw --continue
```

The conversation is shared, so `aisw --continue` goes on with it on b. `aisw list` shows who is used up
until when.

## 5. Accounts

| Want | Do |
|---|---|
| Sign in again (logged out, expired) | `aisw login b` or `l` in the dashboard |
| Take one off the list | `aisw remove b` or `d` (folder and login stay) |
| See the file | `cat ~/.aisw/accounts` (`name tool folder`) |

## 6. Troubleshooting

| Symptom | Fix |
|---|---|
| `aisw activate` prints "This shell can't be changed…" | The `~/.zshrc` line is missing or the terminal is older than it: open a new terminal, or `eval "$(aisw activate b)"` |
| A Claude sign-in used the wrong account | Sign-ins open an empty Incognito profile; without Chrome they use your normal browser. `aisw login <name>` again |
| No usage in `aisw list` | Shown once a session on that account has drawn the status line |

## 7. Update and uninstall

```bash
brew upgrade aisw
brew uninstall aisw
```

Before uninstalling, remove by hand: `statusLine` and the `StopFailure` hook in `~/.claude/settings.json`,
and the aisw line in `~/.zshrc`. Logins stay in their folders (`~/.claude-a`, `~/.aisw/home/<name>`, `~/.codex`).
