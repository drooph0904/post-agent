# DevPost Agent — Design Spec
**Date:** 2026-05-14  
**Status:** Approved  
**Goal:** Both a working daily-use tool AND a clean teaching artifact for agent design patterns

---

## Overview

DevPost is a CLI agent that a student developer runs after a coding session. It reads only **new** Git commits since the last post, generates a tweet (≤280 chars, copied to clipboard) and 6 subreddit-specific Reddit posts, shows everything for approval, posts approved content, and records what was posted so the next run never repeats the same commits.

---

## Tech Stack

| Layer | Technology | Notes |
|---|---|---|
| Language | Python 3.11+ | |
| AI Brain | Anthropic SDK (latest stable ≥0.40.0) | Model: `claude-sonnet-4-6` |
| CLI | Click 8.1.7 | |
| Reddit | PRAW 7.7.1 | Free tier |
| Terminal UI | Rich 13.7.1 | |
| Clipboard | Pyperclip 1.8.2 | |
| Git | GitPython 3.1.43 | |
| Config + Log | `~/.devpost/config.json` + `~/.devpost/post_log.json` | |

> **Spec deviation from original:** `anthropic==0.28.0` replaced with latest SDK because 0.28.0 predates `claude-sonnet-4-6`.  
> **Build backend fix:** `"setuptools.backends.legacy:build"` → `"setuptools.build_meta"`.

---

## Project Structure

```
devpost/
├── pyproject.toml
├── .gitignore
├── .env.example
├── README.md
├── project_context.example.md
└── devpost/
    ├── __init__.py
    ├── main.py           ← CLI entry point (Click) — 5 commands
    ├── agent.py          ← Orchestrator brain
    ├── git_reader.py     ← Dual-mode commit fetching
    ├── post_log.py       ← Persistent hash tracking
    ├── reddit_poster.py  ← PRAW + persona-driven generation
    ├── tweet_builder.py  ← Self-correction loop
    ├── display.py        ← All Rich terminal output
    └── config.py         ← Credential management
```

---

## Architecture

**8 modules, each with a single clear responsibility.** No module uses `print()` — all output goes through `display.py`.

### Module Responsibilities

**`config.py` — ConfigManager**  
Manages `~/.devpost/config.json`. First-run setup wizard. Priority: env var > config file > fallback. Validates all 5 credentials (Anthropic key + 4 Reddit fields).

**`post_log.py` — PostLog**  
Manages `~/.devpost/post_log.json`. Keyed by absolute repo path. Tracks the newest commit hash included in a successful post. Size limit: trim to 40 entries if over 50. Thread-safe file writes not required (CLI tool, single process).

**`git_reader.py` — GitReader**  
Two modes:
- **Hash mode** (returning run): walk git log, stop at saved hash, return only newer commits
- **Time mode** (first run / `--force`): return commits within last N hours

Both return identical `list[dict]` structure. Falls back to time mode if saved hash not found in history (handles rebases).

**`display.py`**  
Single `Console()` instance. All Rich panels, tables, prompts. Every other module imports and calls display functions — never `print()` directly.

**`tweet_builder.py` — TweetBuilder**  
Self-correction loop (max 5 retries). Never returns a tweet >280 chars to the caller. Falls back to word-boundary truncation at 277 + "..." after 5 failures. 30-second timeout on Claude calls.

**`reddit_poster.py` — RedditPoster**  
6 subreddit-specific persona prompts → Claude → `{title, body}` JSON per subreddit. PRAW posting wrapped per-subreddit so one failure doesn't abort the rest.

**`agent.py` — DevPostAgent**  
Central orchestrator. `self.results: dict = {}` and `self.anything_posted: bool = False` initialized in `__init__`, reset at start of each `run()`. Captures `newest_hash` from `commits[0]` before any approval loop.

**`main.py`**  
Click group with 5 commands: `run`, `setup`, `init`, `status`, `reset`.

---

## Core Data Flow

```
devpost run [--path .] [--force] [--dry-run]
  │
  ├─ Step 1/7: Read project_context.md (graceful if missing)
  │
  ├─ Step 2/7: Check post log
  │     ├─ None or --force → GitReader.get_commits_last_hours(24)
  │     └─ hash found      → GitReader.get_commits_since_hash(hash)
  │
  │     commits == [] → print "nothing new to post", exit (log UNCHANGED)
  │
  │     newest_hash = commits[0]["full_hash"]  ← captured here, before approval loop
  │
  ├─ Step 3/7: TweetBuilder.generate() [self-correction loop internal]
  ├─ Step 4/7: RedditPoster.generate_all() [6 persona calls]
  │
  ├─ Step 5/7: Tweet approval → pyperclip.copy() → anything_posted = True
  ├─ Step 6/7: Per-subreddit approval → PRAW post → anything_posted = True
  │
  └─ Step 7/7: if anything_posted (and not --dry-run):
                   PostLog.save_last_hash(repo_path, newest_hash)
               else:
                   log unchanged
```

**Key invariant:** `newest_hash` reflects what was *shown to the user*, captured before the approval loop, so it's deterministic regardless of new commits arriving during a long approval session.

---

## Agent Design Patterns (Teaching Artifact)

| Pattern | File | Description |
|---|---|---|
| Self-correction loop | `tweet_builder.py` | Agent retries until output is valid (≤280 chars) |
| Persistent state | `post_log.py` | Agent memory between runs — no redundant posts |
| Context injection | `agent.py` | `project_context.md` grounds all generation |
| Tool orchestration | `agent.py` | Coordinates git + AI + Reddit + clipboard |
| Human-in-the-loop | `agent.py` | Approval before every external action |
| Multi-format output | `reddit_poster.py` | Same data → 6 audience-specific posts |
| Conditional tool selection | `agent.py` | Hash-mode vs time-mode based on state |

Each pattern module has a comment block at the top explaining the pattern, the problem it solves, and the data flow through that file.

---

## Error Handling

| Scenario | Handling |
|---|---|
| Reddit creds missing/invalid at init | Wrap PRAW init in try/except, print clear message, raise — clean exit |
| PRAW post fails for one subreddit | Catch per-subreddit, store `"failed"` in results, continue loop |
| Claude API timeout (tweet) | 30s timeout, fallback to truncated git summary |
| Hash not in git history (after rebase) | Warn + fallback to `get_commits_last_hours(24)` |
| Clipboard failure | Print tweet in terminal for manual copy, don't crash |
| No commits found | Clean exit, friendly message, log unchanged |
| `--dry-run` flag | Prefix all actions `[DRY RUN]`, skip all external actions, skip log update |
| User skips all posts | `anything_posted` stays False, log unchanged |

---

## CLI Commands

| Command | Description |
|---|---|
| `devpost run` | Main command — only new commits, smart post log |
| `devpost run --force` | Ignore log, fetch last 24h (first run or repost) |
| `devpost run --dry-run` | Preview everything, change nothing |
| `devpost setup` | Run credential wizard → save to `~/.devpost/config.json` |
| `devpost init` | Create `project_context.md` template in current dir |
| `devpost status` | Show all tracked projects + last posted hash (Rich table) |
| `devpost reset` | Clear post log for current dir (with y/N confirmation) |

---

## Post Log Format

`~/.devpost/post_log.json` — keyed by absolute repo path:
```json
{
  "/Users/username/code/my-project": "a3f92b1abc123...",
  "/Users/username/code/another-project": "cc81d04def456..."
}
```

Size limit: if entry count > 50, trim oldest 10.

---

## Known Spec Deviations (Approach B fixes)

1. **`pyproject.toml` build backend**: `"setuptools.backends.legacy:build"` → `"setuptools.build_meta"` (original string is invalid)
2. **`anthropic` version**: latest stable SDK instead of pinned `==0.28.0` (0.28.0 predates claude-sonnet-4-6)
3. **Model string**: `claude-sonnet-4-6` instead of `claude-sonnet-4-20250514` (per user preference)
4. **`agent.py __init__`**: add `self.results: dict = {}` (used in `run()` but missing from `__init__` in spec)
5. **`agent.py run()`**: add `self.results = {}` and `self.anything_posted = False` at top of `run()` so repeated calls don't accumulate stale results
6. **`anthropic` version**: using `>=0.40.0` (unpinned upper) — intentional, we want latest SDK compatible with `claude-sonnet-4-6`

---

## Implementation Plan Phases

11 phases, one commit per phase:
1. Project initialization (pyproject.toml, .gitignore, .env.example, install)
2. `config.py` — ConfigManager
3. `post_log.py` — PostLog
4. `git_reader.py` — GitReader
5. `display.py` — all Rich UI
6. `tweet_builder.py` — TweetBuilder + self-correction loop
7. `reddit_poster.py` — RedditPoster
8. `agent.py` — DevPostAgent orchestrator
9. `main.py` — CLI entry point
10. README + project_context.example.md
11. Hardening: dry-run, timeouts, size limits, rebase fallback + final verification
