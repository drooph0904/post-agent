# DevPost Agent — Architecture Guide

> For a new developer who wants to understand, modify, or extend this project.

---

## 1. Executive Summary

DevPost is a CLI agent that reads only **new** Git commits since the last run, uses OpenAI GPT-4o-mini to generate a tweet (≤280 chars, copied to clipboard) and 6 subreddit-specific Reddit posts, shows everything for user approval, posts what gets approved, and saves the latest commit hash so the next run never repeats the same content.

**Key technologies:** Python 3.11+, Click (CLI), Rich (terminal UI), OpenAI SDK (GPT-4o-mini), PRAW (Reddit API), GitPython (git history), Pyperclip (clipboard)

**Complexity:** Medium. 8 focused modules (~100 lines each), zero circular imports, clean dependency graph. A developer comfortable with Python can understand any single file in under 10 minutes.

---

## 2. High-Level Architecture Diagram

```
User runs: devpost run
               │
               ▼
        ┌─────────────┐
        │   main.py   │  ← Click CLI entry point
        │  (5 commands)│
        └──────┬──────┘
               │ creates DevPostAgent(config)
               ▼
        ┌─────────────┐
        │   agent.py  │  ← Central orchestrator (stateful brain)
        │DevPostAgent │
        └──────┬──────┘
               │
       ┌───────┼───────────────────────────┐
       │       │                           │
       ▼       ▼                           ▼
┌──────────┐ ┌──────────┐         ┌──────────────┐
│post_log.py│ │git_reader│         │  config.py   │
│ PostLog  │ │ GitReader│         │ConfigManager │
│(memory)  │ │(commits) │         │(credentials) │
└──────────┘ └──────┬───┘         └──────────────┘
                    │ commits[]
                    ▼
           ┌─────────────────┐
           │  tweet_builder  │ → OpenAI API → tweet (≤280 chars)
           │  reddit_poster  │ → OpenAI API → 6 × {title, body}
           └────────┬────────┘
                    │ show for approval
                    ▼
             ┌───────────┐
             │ display.py│  ← All Rich terminal output
             └───────────┘
                    │ user approves
                    ▼
           ┌─────────────────┐
           │  pyperclip      │ ← tweet → clipboard
           │  praw (Reddit)  │ ← posts → Reddit API
           └─────────────────┘
                    │ if anything posted
                    ▼
           ┌─────────────────┐
           │  post_log.py    │ ← save newest commit hash
           └─────────────────┘
```

---

## 3. Folder Structure Breakdown

```
post-agent/
│
├── devpost/                    ← The actual Python package
│   ├── __init__.py             ← Empty. Makes devpost/ a package.
│   ├── main.py                 ← CLI entry point. 5 Click commands.
│   ├── agent.py                ← Orchestrator. Coordinates everything.
│   ├── config.py               ← Reads/writes ~/.devpost/config.json
│   ├── post_log.py             ← Reads/writes ~/.devpost/post_log.json
│   ├── git_reader.py           ← Reads git history. Two modes.
│   ├── display.py              ← ALL terminal output. No print() elsewhere.
│   ├── tweet_builder.py        ← OpenAI → tweet. Self-correction loop.
│   └── reddit_poster.py        ← OpenAI → 6 Reddit posts. PRAW posting.
│
├── tests/
│   ├── conftest.py             ← Shared pytest fixture: tmp_devpost_dir
│   ├── test_config.py          ← ConfigManager unit tests
│   ├── test_post_log.py        ← PostLog unit tests
│   ├── test_git_reader.py      ← GitReader unit tests (real temp git repos)
│   ├── test_tweet_builder.py   ← TweetBuilder tests (mocked OpenAI)
│   ├── test_reddit_poster.py   ← RedditPoster tests (mocked PRAW + OpenAI)
│   ├── test_agent.py           ← DevPostAgent integration tests (all mocked)
│   └── test_main.py            ← CLI tests via Click CliRunner
│
├── docs/superpowers/
│   ├── specs/2026-05-14-devpost-design.md   ← Original design spec
│   └── plans/2026-05-14-devpost-agent.md    ← Step-by-step build plan
│
├── pyproject.toml              ← Package config, dependencies, entry point
├── .env.example                ← Template for env var credentials
├── project_context.example.md ← Template users fill in per project
└── README.md                  ← User-facing setup and usage guide
```

**Rule enforced throughout:** No file calls `print()`. Every terminal output goes through `display.py`. This makes the UI swappable and keeps logic files clean.

---

## 4. Entry Point Analysis

### What happens first when you run `devpost run`?

```
1. Python executes /opt/homebrew/bin/devpost
   └── calls cli() from devpost/main.py

2. Click parses arguments → routes to run() command

3. run() in main.py:
   a. Creates ConfigManager() — loads ~/.devpost/config.json
   b. Calls config.validate() — checks all 5 credentials exist
   c. If invalid → prints missing list → Abort()
   d. Creates DevPostAgent(config=config)
      └── This creates: OpenAI client, PostLog, TweetBuilder, RedditPoster
   e. Calls agent.run(project_path, force, dry_run)

4. agent.run() takes over — executes 7 steps (see §7)
```

**Important:** `DevPostAgent` is imported lazily inside the `run()` function (not at the top of `main.py`). This keeps startup fast for commands like `devpost status` and `devpost --help` that don't need OpenAI or PRAW.

---

## 5. File-by-File Deep Explanation

---

### `devpost/config.py` — ConfigManager

**Purpose:** Single source of truth for all credentials. Reads from env vars first, then `~/.devpost/config.json`, then returns `None`.

**Connections:** Used by `main.py` (validation + wizard), `agent.py` (get OpenAI key), `reddit_poster.py` (get Reddit credentials).

**Data in:** Key names as strings (e.g. `"openai_api_key"`)
**Data out:** String values or `None`

**Priority chain:**
```
os.environ["OPENAI_API_KEY"]      ← highest priority
  ↓ (if missing)
~/.devpost/config.json            ← saved via devpost setup
  ↓ (if missing)
None / fallback value             ← lowest priority
```

**Key design:** The env var check uses `key.upper()` — so `config.get("openai_api_key")` checks `os.environ["OPENAI_API_KEY"]`. This means you can override any config value with an environment variable without touching the file.

---

### `devpost/post_log.py` — PostLog

**Purpose:** Agent memory between runs. Remembers which commit was last posted for each project, keyed by absolute path.

**Connections:** Read by `agent.py` at the start of every run. Written by `agent.py` at the end if anything was posted.

**Storage:** `~/.devpost/post_log.json`
```json
{
  "/Users/you/projects/my-app": "a3f92b1abc123def456...",
  "/Users/you/projects/another": "cc81d04def456abc123..."
}
```

**Key behavior:** Paths are always normalized to absolute (`Path(repo_path).resolve()`). This prevents `"."` and `"/Users/you/projects/my-app"` from being treated as different projects.

**Size limit:** If entries exceed 50, oldest 10 are trimmed. Prevents the file growing unboundedly if you use DevPost across many projects.

---

### `devpost/git_reader.py` — GitReader

**Purpose:** Reads git commit history in two modes. Both modes return the same `list[dict]` shape so the caller (`agent.py`) doesn't need to know which mode ran.

**Connections:** Created by `agent.py`. `get_newest_hash()` and `summarize_changes()` are static methods — they can be called on the class without an instance.

**Two modes:**

```
MODE A — Hash mode (returning user):
  get_commits_since_hash("abc1234")
  → walk git log newest-first
  → collect commits until we hit abc1234
  → return only the newer ones
  → if hash not found (rebase happened): fallback to 24h mode + warning

MODE B — Time mode (first run or --force):
  get_commits_last_hours(24)
  → walk git log newest-first
  → collect commits authored in last 24 hours
  → stop at first commit older than cutoff (safe due to chronological order)
```

**Commit dict shape** (what every commit looks like):
```python
{
    "hash": "a3f92b1",          # 7-char short hash
    "full_hash": "a3f92b1abc...", # 40-char full hash
    "message": "feat: add login", # stripped commit message
    "author": "Jane Dev",
    "timestamp": "2026-05-14T10:30:00+00:00",  # ISO format
    "files_changed": ["src/auth.py", "tests/test_auth.py"],
    "insertions": 45,
    "deletions": 12,
}
```

**Critical datetime bug to avoid:** Uses `.astimezone(timezone.utc)` NOT `.replace(tzinfo=timezone.utc)`. The latter would overwrite an existing timezone, producing wrong comparisons for commits made in non-UTC timezones.

---

### `devpost/display.py` — Display

**Purpose:** Owns ALL terminal output. Every other module imports and calls functions from here. No `print()` anywhere else in the codebase.

**Connections:** Imported by `agent.py`, `tweet_builder.py`, `reddit_poster.py`, `config.py`, `main.py`.

**Why this matters:** If you want to change how something looks — swap Rich for plain text, add logging, change colors — you change one file. No grep-and-replace across the codebase.

**Key functions:**
- `print_header()` — Banner shown at start of every run
- `print_step(n, total, msg)` — Progress indicator "[2/7] Checking..."
- `ask_tweet_approval(tweet, char_count) → bool` — Shows tweet panel + prompt
- `ask_reddit_approval(subreddit, title, body, i, total) → bool` — Shows Reddit panel + prompt
- `print_final_summary(results: dict)` — Rich table at end of run

---

### `devpost/tweet_builder.py` — TweetBuilder

**Purpose:** Generates a tweet ≤280 chars using a self-correction loop. The user never sees an over-limit draft.

**Connections:** Created by `agent.py`, receives the OpenAI client. Imports `display` for status messages. Imports `pyperclip` for clipboard.

**Self-correction loop:**
```
attempt 1: Claude generates tweet
  → count chars
  → if ≤280: return it ✓
  → if >280: chars_over = count - 280
             send BACK to Claude with:
             "your previous tweet was {chars_over} chars too long"
             "previous attempt: {tweet}"
             "rewrite it to be strictly under 280 chars"
attempt 2: Claude tries again
  → repeat up to 5 times
  → if still failing after 5: truncate git_summary at word boundary + "..."
```

**Prompt strategy — first attempt vs retry:**
- First attempt: full creative prompt with tone, audience, hashtag rules, demo link logic
- Retry: minimal prompt focused only on fixing the length — shows the failed draft + exact overage

---

### `devpost/reddit_poster.py` — RedditPoster

**Purpose:** Generates 6 Reddit posts (one per subreddit) using community-specific persona prompts, then posts via PRAW.

**Connections:** Created by `agent.py` with both the OpenAI client and ConfigManager. Imports `display`.

**`SUBREDDIT_PERSONAS` dict** — the core of this module. Each subreddit entry has:
```python
{
    "audience": "who reads this subreddit",
    "tone": "how to write",
    "focus": "what aspect of the work to highlight",
    "title_style": "example title format",
    "depth": "word count target",
}
```

**Why 6 different prompts?** The same commit produces very different posts:
- `r/webdev` wants technical stack details and what broke
- `r/learnprogramming` wants the learning journey and struggles  
- `r/MachineLearning` wants precise ML terminology and metrics
- Same commits, same project, completely different angle

**PRAW init guard:** If `reddit_client_id` is `None` (placeholder or missing), `self.reddit = None` and no PRAW initialization happens. This allows `--dry-run` and tweet-only runs without Reddit credentials.

**Per-subreddit error isolation:** Each subreddit's API call is wrapped in try/except. One failure doesn't abort the rest — the failed subreddit gets `{"title": "[generation failed]", "body": ""}` and the loop continues.

---

### `devpost/agent.py` — DevPostAgent

**Purpose:** The central brain. Coordinates all other modules, manages state across the 7-step run, enforces the human-in-the-loop approval pattern.

**Connections:** Uses every other module. Created by `main.py`.

**State variables:**
```python
self.results: dict = {}        # filled during run, shown in final summary
self.anything_posted: bool = False  # gates whether post log gets updated
```

Both are reset at the **start** of every `run()` call — not in `__init__`. This ensures repeated calls in the same session don't accumulate stale state.

**The `newest_hash` invariant:** Captured from `commits[0]["full_hash"]` BEFORE the approval loop starts. This is intentional — if new commits arrive while the user is slowly approving posts, the hash still reflects what was shown, not what arrived later.

---

### `devpost/main.py` — CLI

**Purpose:** Thin Click wrapper. Maps CLI commands to agent/config/log operations.

**5 commands:**
| Command | What it does |
|---|---|
| `run` | Validates creds → creates agent → calls agent.run() |
| `setup` | Calls ConfigManager().setup_wizard() |
| `init` | Creates project_context.md template in cwd |
| `status` | Reads PostLog, renders Rich table |
| `reset` | Confirms → calls PostLog.clear_log() |

**Lazy import:** `from devpost.agent import DevPostAgent` is inside the `run()` function body, not at the top of the file. This prevents importing OpenAI and PRAW on every `devpost --help` or `devpost status` call.

---

## 6. Function-by-Function Analysis

---

```
FUNCTION: DevPostAgent.run()
FILE: devpost/agent.py
PURPOSE: Orchestrates the entire 7-step workflow for one devpost session
INPUT: project_path: str = ".", force: bool = False, dry_run: bool = False
OUTPUT: dict — results keyed by action ("tweet", "r/SideProject", etc.)
CALLED BY: main.py run() command
CALLS: display.*, PostLog.get_last_hash, GitReader (constructor + methods),
       TweetBuilder.generate, RedditPoster.generate_all,
       display.ask_tweet_approval, TweetBuilder.copy_to_clipboard,
       display.ask_reddit_approval, RedditPoster.post_to_subreddit,
       PostLog.save_last_hash
TRANSFORMATION: git commits → approved social media content → posted
SIDE EFFECTS: Reddit API calls, clipboard write, post_log.json update
PITFALLS: newest_hash must be captured BEFORE the approval loop.
          self.results and self.anything_posted must be reset at top of run().

STEP TRACE:
  Step 1: read project_context.md (or warn if missing)
  Step 2: check post log → decide hash-mode or time-mode → fetch commits
          if no commits → return {"status": "no_new_commits"}
  Step 3: generate tweet (or dry-run placeholder)
  Step 4: generate all 6 Reddit posts (or dry-run placeholders)
  Step 5: show tweet → ask approval → copy to clipboard
  Step 6: for each subreddit → show post → ask approval → post via PRAW
  Step 7: if anything_posted and not dry_run → save newest_hash to post log
          print final summary table
```

---

```
FUNCTION: TweetBuilder.generate()
FILE: devpost/tweet_builder.py
PURPOSE: Return a tweet ≤280 chars. Never returns over-limit to caller.
INPUT: git_summary: str, context: str
OUTPUT: tuple[str, int] — (tweet_text, char_count)
CALLED BY: DevPostAgent.run() at step 3
CALLS: self._build_prompt(), self.client.chat.completions.create(),
       display.print_thinking(), display.print_warning()
TRANSFORMATION: git summary + project context → valid tweet
SIDE EFFECTS: OpenAI API calls (1–5 depending on retries)
PITFALLS: On total failure (5 bad attempts), falls back to truncating
          git_summary — the fallback tweet is not AI-written, just raw
          commit text. Callers should be aware the tweet quality drops.

CODE SNIPPET:
  for attempt in range(1, self.max_retries + 1):
      response = self.client.chat.completions.create(...)
      tweet = response.choices[0].message.content.strip()
      count = len(tweet)
      if count <= 280:
          return tweet, count
      chars_over = count - 280
      previous_attempt = tweet  # sent back to Claude next attempt
  # fallback:
  fallback = git_summary[:270].rsplit(" ", 1)[0] + "..."
  return fallback[:280], len(fallback[:280])
```

---

```
FUNCTION: GitReader.get_commits_since_hash()
FILE: devpost/git_reader.py
PURPOSE: Return only commits newer than a saved hash (normal returning-user flow)
INPUT: last_hash: str — 7-char or full hash from post_log
OUTPUT: list[dict] — commits newer than last_hash, newest first
CALLED BY: DevPostAgent.run() step 2 when post log has an entry
CALLS: self.repo.iter_commits(), self._format_commit(),
       self.get_commits_last_hours() (rebase fallback only)
TRANSFORMATION: raw git Commit objects → list of dicts
SIDE EFFECTS: Prints warning if hash not found (rebase fallback triggered)
PITFALLS: Hash comparison uses both exact match and .startswith() to handle
          7-char short hashes saved by older runs. If you save a 7-char hash
          and the repo has two commits starting with those 7 chars (collision),
          it will stop at the first match — extremely rare but possible.

REBASE FALLBACK:
  If we walk the entire history and never find last_hash:
  → results is non-empty (repo has commits but not that hash)
  → print warning "hash not found, falling back to 24h"
  → return get_commits_last_hours(24)
  
  If results is empty (repo has zero commits):
  → return [] (no fallback needed, nothing to show)
```

---

```
FUNCTION: PostLog.save_last_hash()
FILE: devpost/post_log.py
PURPOSE: Record which commit was last posted for a given repo path
INPUT: repo_path: str, commit_hash: str (40-char full hash)
OUTPUT: None
CALLED BY: DevPostAgent.run() step 7, only when anything_posted=True
CALLS: self._normalize(), self._save()
TRANSFORMATION: Adds/updates one entry in self.log dict, trims if >50 entries
SIDE EFFECTS: Writes ~/.devpost/post_log.json to disk
PITFALLS: Always pass the full 40-char hash, not the 7-char short hash.
          The hash is later used in get_commits_since_hash() which does
          .startswith() matching — short hashes work but are collision-prone.
```

---

## 7. Full Data Flow Trace

Complete lifecycle of `devpost run` from keystroke to final summary:

```
USER: devpost run --path /projects/my-app

┌─ main.py ─────────────────────────────────────────────────────────┐
│  config = ConfigManager()                                          │
│  config._load() → reads ~/.devpost/config.json                     │
│  config.validate() → checks openai_api_key, reddit_* exist         │
│  agent = DevPostAgent(config)                                      │
│    agent.client = OpenAI(api_key="sk-...")                         │
│    agent.post_log = PostLog()  → loads ~/.devpost/post_log.json    │
│    agent.tweet_builder = TweetBuilder(client=agent.client)         │
│    agent.reddit_poster = RedditPoster(client=agent.client,         │
│                                       config=config)               │
│      → praw.Reddit(client_id=...) — initialized if creds present  │
└────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─ agent.run("/projects/my-app") ───────────────────────────────────┐
│                                                                    │
│  STEP 1: context = read_context("/projects/my-app")               │
│    → reads /projects/my-app/project_context.md                     │
│    → context = "# Project Context\n## Project Name\n..."           │
│                                                                    │
│  STEP 2: git_reader = GitReader("/projects/my-app")               │
│    repo_name = "my-app"                                            │
│    last_hash = post_log.get_last_hash("/projects/my-app")          │
│      → "a3f92b1abc123..." (from post_log.json)                     │
│                                                                    │
│    commits = git_reader.get_commits_since_hash("a3f92b1...")       │
│      → walks repo.iter_commits() newest-first                      │
│      → stops at a3f92b1...                                         │
│      → returns [                                                   │
│          {"hash": "db4cb96", "full_hash": "db4cb96...",            │
│           "message": "feat: add login", "author": "Dev",           │
│           "timestamp": "...", "files_changed": [...],              │
│           "insertions": 45, "deletions": 12},                      │
│          ...                                                       │
│        ]                                                           │
│                                                                    │
│    newest_hash = "db4cb96abc..."  ← captured HERE before approval  │
│    git_summary = GitReader.summarize_changes(commits)              │
│      → "Total commits: 3\n\nCommits (newest first):\n  - db4..."  │
│                                                                    │
│  STEP 3: tweet, char_count = tweet_builder.generate(              │
│              git_summary, context)                                 │
│    → _build_prompt(git_summary, context) → prompt string          │
│    → openai.chat.completions.create(model="gpt-4o-mini", ...)     │
│    → response.choices[0].message.content → "Built login today..."  │
│    → len("Built login today...") = 263 ≤ 280 ✓                    │
│    → returns ("Built login today...", 263)                         │
│                                                                    │
│  STEP 4: reddit_posts = reddit_poster.generate_all(               │
│              git_summary, context)                                 │
│    → for each of 6 subreddits:                                     │
│        build persona prompt → openai call → parse JSON             │
│        → {"title": "...", "body": "..."}                           │
│    → returns {                                                     │
│        "SideProject": {"title": "...", "body": "..."},             │
│        "webdev": {"title": "...", "body": "..."},                  │
│        ...6 entries total                                          │
│      }                                                             │
│                                                                    │
│  STEP 5: display.ask_tweet_approval(tweet, 263)                   │
│    → shows Rich panel with tweet + "263/280 characters"            │
│    → user presses "y"                                              │
│    → tweet_builder.copy_to_clipboard(tweet)                        │
│        → pyperclip.copy("Built login today...")                    │
│    → self.results["tweet"] = "copied"                              │
│    → self.anything_posted = True                                   │
│                                                                    │
│  STEP 6: for subreddit, post in reddit_posts.items():             │
│    → display.ask_reddit_approval(...) → user presses "y"           │
│    → reddit_poster.post_to_subreddit("SideProject", title, body)   │
│        → praw.subreddit("SideProject").submit(...)                 │
│        → returns "https://reddit.com/r/SideProject/comments/xyz"  │
│    → self.results["r/SideProject"] = "posted: https://..."        │
│    → self.anything_posted = True                                   │
│                                                                    │
│  STEP 7: anything_posted=True and not dry_run                     │
│    → post_log.save_last_hash("/projects/my-app", "db4cb96abc...")  │
│        → ~/.devpost/post_log.json updated                          │
│    → display.print_final_summary(self.results)                     │
│        → Rich table: tweet=copied, r/SideProject=posted, ...      │
└────────────────────────────────────────────────────────────────────┘
```

---

## 8. Agent Interaction Flow

DevPost is a **single-agent system** — there is one `DevPostAgent` orchestrating specialized modules as tools. It does not use multi-agent frameworks.

```
DevPostAgent (orchestrator)
    │
    ├── READS FROM:
    │     PostLog (memory)
    │     GitReader (environment sensor)
    │     ConfigManager (configuration)
    │     project_context.md (context file)
    │
    ├── DELEGATES TO:
    │     TweetBuilder.generate()   → OpenAI (external tool)
    │     RedditPoster.generate_all() → OpenAI × 6 (external tool)
    │
    ├── GETS HUMAN APPROVAL VIA:
    │     display.ask_tweet_approval()
    │     display.ask_reddit_approval()
    │
    └── ACTS ON APPROVAL:
          TweetBuilder.copy_to_clipboard()  → pyperclip (external tool)
          RedditPoster.post_to_subreddit()  → PRAW → Reddit API (external tool)
          PostLog.save_last_hash()          → disk (state mutation)
```

**The human is in the loop between generation and action.** The agent never takes an external action (post, clipboard write, log update) without explicit user approval. This is the Human-in-the-Loop pattern.

---

## 9. State & Memory Management

### In-memory state (lives only during one run)

| Variable | Location | Created | Reset | Destroyed |
|---|---|---|---|---|
| `agent.results` | `DevPostAgent` | `run()` start | `run()` start | process exit |
| `agent.anything_posted` | `DevPostAgent` | `run()` start | `run()` start | process exit |
| `config.config` | `ConfigManager` | `__init__` | never | process exit |
| `post_log.log` | `PostLog` | `__init__` | never | process exit |

### Persistent state (survives between runs)

| File | Location | Purpose | Format |
|---|---|---|---|
| `config.json` | `~/.devpost/config.json` | API keys and credentials | JSON object |
| `post_log.json` | `~/.devpost/post_log.json` | Last posted hash per repo | JSON object |

### State update invariant

The post log is **only updated when `anything_posted = True` AND `dry_run = False`**.

If the user approves nothing (presses `n` on everything), the log stays unchanged and the same commits will appear next run. This is intentional — it prevents accidentally "using up" commits you didn't actually share.

---

## 10. API / LLM / Tool Integrations

### OpenAI (GPT-4o-mini)

**Why:** Cheapest capable model. ~$0.001 per full run (7 API calls total: 1 tweet + 6 Reddit posts).

**How called in tweet_builder.py:**
```python
response = self.client.chat.completions.create(
    model="gpt-4o-mini",
    max_tokens=300,          # tweet is short
    messages=[{"role": "user", "content": prompt}],
    timeout=30.0,
)
tweet = response.choices[0].message.content.strip()
```

**How called in reddit_poster.py:**
```python
response = self.client.chat.completions.create(
    model="gpt-4o-mini",
    max_tokens=1024,         # Reddit posts are longer
    messages=[{"role": "user", "content": prompt}],
    timeout=30.0,
)
raw = response.choices[0].message.content.strip()
data = json.loads(raw)       # Claude returns JSON: {"title": ..., "body": ...}
```

**Alternatives:** Anthropic Claude (was the original — swapped to OpenAI for cost), Google Gemini, local Ollama models (would need `timeout` changes).

---

### PRAW (Python Reddit API Wrapper)

**Why:** Official Reddit API wrapper. Handles OAuth, rate limiting, and submission.

**How called:**
```python
submission = self.reddit.subreddit("SideProject").submit(
    title="I built X — here's what I learned",
    selftext="Body of the post..."
)
url = submission.url  # returned to agent for display
```

**Guard:** If `reddit_client_id` is `None`, `self.reddit = None` and `post_to_subreddit()` returns `None` immediately without crashing. This enables dry-run and tweet-only usage.

**Alternatives:** Direct Reddit REST API calls (more complex, same rate limits).

---

### Pyperclip (clipboard)

**Why:** Cross-platform clipboard access in 1 line. Works on Mac, Windows, Linux.

**How called:**
```python
pyperclip.copy(tweet_text)
```

**Failure handling:** Wrapped in try/except. On failure (some Linux environments without clipboard daemon), `copy_to_clipboard()` returns `False` and the tweet is printed to terminal for manual copy instead of crashing.

---

### GitPython

**Why:** Python library for reading git repositories. Parses commit history, file stats, authorship.

**How called:**
```python
repo = git.Repo(repo_path)          # opens the repo
for commit in repo.iter_commits():  # walk history newest-first
    commit.hexsha                   # full hash
    commit.message                  # commit message
    commit.authored_datetime        # timezone-aware datetime
    commit.stats.files              # {filename: {insertions, deletions}}
    commit.stats.total              # {insertions, deletions, files}
```

---

## 11. Framework Analysis

### Click

**Why:** Declarative CLI framework. Transforms Python functions into commands with options and help text automatically.

**How it works:**
```python
@click.group()
def cli(): ...          # creates the top-level "devpost" command group

@cli.command()
@click.option("--force", is_flag=True)
def run(force: bool): ...  # "devpost run --force" maps here automatically
```

**What it provides:** Argument parsing, `--help` generation, type coercion, error messages. Without Click, you'd write `argparse` or `sys.argv` parsing manually.

### Rich

**Why:** Beautiful terminal output with zero effort. Panels, tables, colored text, prompts.

**Key usage:**
- `Console.print("[bold cyan]text[/bold cyan]")` — colored output
- `Panel(content, title=..., border_style=...)` — boxed panels
- `Table(...)` — the final summary table
- `Confirm.ask("Post this?", default=False)` — interactive y/n prompts

**Single instance rule:** One `console = Console()` in `display.py`. All other modules import and call `display.function_name()` — they never create their own Console instances.

### pytest

**Why:** Standard Python testing framework. Fixtures, parametrize, monkeypatch.

**Key test patterns used:**
```python
# Shared fixture in conftest.py
@pytest.fixture
def tmp_devpost_dir(tmp_path):
    d = tmp_path / ".devpost"
    d.mkdir()
    return d

# Mocking OpenAI client
builder = TweetBuilder(client=MagicMock())
builder.client.chat.completions.create.return_value = mock_response

# Testing CLI
from click.testing import CliRunner
result = CliRunner().invoke(cli, ["status"])
assert result.exit_code == 0
```

---

## 12. Git Evolution Analysis

```
c3c99c1  docs: devpost agent design spec
b68c7e2  docs: devpost agent implementation plan

  → Project started with spec + plan before any code.
    Architecture was fully designed before implementation began.

abc1380  chore: initialize devpost project, dependencies, and package structure
6327b39  feat: config manager with first-run setup wizard
be9919f  fix: remove unused imports from test_config.py
f01c600  feat: post log — persistent commit tracking
b3cf8e5  feat: git reader — dual-mode commit fetching
9031ddd  fix: remove extra-scope methods from git_reader
55d2c1e  fix: improve git_reader quality

  → Built bottom-up: infrastructure modules first (config, log, git),
    each reviewed and fixed before moving to the next.
    Two fix commits on git_reader show the review process caught
    extra methods (get_repo_stats, validate_repo) that weren't in spec.

225124f  feat: display module
b86c393  feat: tweet builder with self-correction loop
f7114e7  feat: reddit poster — subreddit-specific generation
a5ad2cb  feat: agent brain — stateful orchestrator
6e0ff83  fix: remove unused Optional import, strengthen test

  → Core agent built last, after all tools were ready.
    Agent is the most complex file and benefits from stable dependencies.

b14301f  feat: CLI — run, setup, init, status, reset
2808137  docs: README
0da5b18  fix: defer Reddit praw init when credentials absent

  → CLI and docs added after all internals were complete.
    The praw fix was caught during final real-world testing:
    RedditPoster was crashing even in dry-run mode when creds missing.

b635162  feat: switch LLM from Anthropic → OpenAI (gpt-4o-mini)

  → Architecture pivot: swapped the LLM provider.
    Only 5 lines changed in production code (import, client init,
    model name, API call shape, response parsing).
    This demonstrates the value of the thin client injection pattern —
    DevPostAgent doesn't know or care which LLM is underneath.

f851ed7  fix: detect deployment links from commits and context
a182f7e  fix: only include demo link on major milestones
5e4ca8b  fix: blank repo name, tweet HF link, learnprogramming hallucination

  → Quality improvements from real-world usage testing.
    Prompt engineering fixes: blank repo name (Path resolve),
    context-aware link inclusion, hallucination prevention.
```

---

## 13. Design Patterns Used

### 1. Self-Correction Loop (`tweet_builder.py`)
Agent generates output → validates it → if invalid, feeds the failure back to the model as input → retries. The model sees its own mistake and corrects it. Used to enforce the 280-char limit.

### 2. Persistent State Between Runs (`post_log.py`)
Agent saves a "memory token" (latest commit hash) after each successful run. Next run, it reads the token and resumes from where it left off. Prevents duplicate posts across sessions.

### 3. Context Injection (`agent.py`)
`project_context.md` is read at run start and passed to every generation call. This grounds the LLM in project-specific knowledge — without it, the AI writes generic posts. The richer the context file, the better the output.

### 4. Tool Orchestration (`agent.py`)
`DevPostAgent` treats other modules as tools: `GitReader` is a sensor, `TweetBuilder` and `RedditPoster` are generators, `PostLog` is memory, `display` is the output interface. The orchestrator coordinates them without any module knowing about the others.

### 5. Human-in-the-Loop (`agent.py`)
Every external action (clipboard write, Reddit post) is gated behind explicit user approval. The agent generates but never acts autonomously. This is the pattern that prevents accidental posts.

### 6. Multi-Format Output (`reddit_poster.py`)
Same input (git commits + context) → multiple outputs tailored to different audiences. Each output uses a different persona prompt tuned to that community's culture.

### 7. Conditional Tool Selection (`agent.py`)
The agent selects between two git-reading strategies based on state: hash-mode if the post log has an entry, time-mode if it doesn't. The strategy is invisible to the rest of the system — both return the same `list[dict]`.

### 8. Dependency Injection
OpenAI client is created once in `DevPostAgent.__init__` and injected into `TweetBuilder` and `RedditPoster`. This makes swapping LLM providers trivial and makes testing clean (inject `MagicMock()` instead).

### 9. Facade Pattern (`display.py`)
All terminal output flows through a single module. The rest of the codebase sees simple functions like `print_error("msg")` — the Rich formatting complexity is hidden behind the facade.

---

## 14. Execution Lifecycle (Startup to Shutdown)

```
STARTUP
  1. Python interpreter loads devpost/main.py
  2. Click registers cli group and 5 command functions
  3. ConfigManager() loads ~/.devpost/config.json into memory
  4. Credential validation runs (or skipped for dry-run)

INITIALIZATION
  5. DevPostAgent created
     a. OpenAI client initialized (no network call yet)
     b. PostLog loaded from ~/.devpost/post_log.json
     c. TweetBuilder created with client reference
     d. RedditPoster created — praw.Reddit() called if creds present
        (praw validates format but doesn't auth yet)

EXECUTION (agent.run)
  6. project_context.md read from disk (or empty string)
  7. GitReader opens git repo (validates it's a real git dir)
  8. PostLog queried for last hash
  9. Git log walked — commits collected
  10. NETWORK CALL 1: OpenAI → generate tweet (1–5 calls, self-correction)
  11. NETWORK CALLS 2–7: OpenAI → generate 6 Reddit posts
  12. Display tweet → user input
  13. If approved: pyperclip.copy() → tweet in clipboard
  14. For each subreddit: display post → user input
  15. If approved: NETWORK CALL 8: PRAW → Reddit API → post submitted

TEARDOWN
  16. If anything posted: post_log.json written to disk
  17. Final summary table printed
  18. run() returns self.results dict to main.py
  19. main.py returns 0 to shell
  20. Python process exits, all in-memory state destroyed
```

---

## 15. Debugging Guide

**1. "Missing credentials" on startup**
→ Run `devpost setup`. Check `~/.devpost/config.json` exists and has `openai_api_key`. Or set `OPENAI_API_KEY` env var.

**2. "Not a git repository" error**
→ You ran `devpost run` in a folder that isn't a git repo. Use `--path /path/to/your/repo` or `cd` into the repo first.

**3. Tweet is raw git log text (not AI-written)**
→ OpenAI API key invalid or balance zero. The self-correction loop hit 5 failures and fell back to truncated git_summary. Check `~/.devpost/config.json` and your OpenAI billing at platform.openai.com.

**4. "No new commits" on every run**
→ Post log thinks nothing is new. Either: (a) no commits in last 24h, (b) post log hash is ahead of your commits. Run `devpost reset` to clear the log, then `devpost run --force`.

**5. Reddit posts all show "[generation failed]"**
→ OpenAI API error during Reddit post generation. Usually: invalid API key, rate limit, or network issue. Each subreddit fails independently — check the error messages printed inline.

**6. Tweet self-correction stuck in loop**
→ If you see "Generating tweet (attempt 1–5)... all too long", the prompt plus URL is too long to fit in 280 chars. Consider shortening the project context or removing the demo URL from context temporarily.

**7. Clipboard copy silent failure**
→ On some Linux setups, pyperclip fails silently. Check if `xclip` or `xsel` is installed (`apt install xclip`). On Mac this should never fail.

**8. Reddit posts succeed but `post_log.json` not updated**
→ Check `agent.anything_posted` logic. Only saves if `anything_posted=True` AND not `dry_run`. If you approved only Reddit posts (not tweet), log still saves — check `self.anything_posted = True` is set in the Reddit loop.

**9. Stale commits showing after rebase**
→ After `git rebase`, saved hashes may not exist in history anymore. DevPost detects this, prints a warning, and falls back to 24h mode. This is correct behavior. Run `devpost reset` to clean up.

**10. Tests failing after LLM provider change**
→ The mock response structure differs between providers. Anthropic uses `response.content[0].text`, OpenAI uses `response.choices[0].message.content`. Check `_make_response()` in `test_tweet_builder.py` and `test_reddit_poster.py` match the current provider.

---

## 16. Key Takeaways

**To confidently extend this project, understand these 6 things:**

**1. The dependency graph flows one way**
`main.py → agent.py → (tweet_builder, reddit_poster, git_reader, post_log, config, display)`. Nothing in the bottom layer knows about anything above it. Adding a new module: put it in the bottom layer, import it in `agent.py`.

**2. All output goes through `display.py`**
Never add a `print()` to any module. Add a function to `display.py` and call it. This keeps every file testable and the UI consistent.

**3. The OpenAI client is injected, not global**
`TweetBuilder(client=openai_client)` — the client is passed in. To swap to Anthropic, Gemini, or a local model, change 3 lines in `agent.py` and update the API call format in `tweet_builder.py` and `reddit_poster.py`. Nothing else changes.

**4. The post log hash is sacred**
`newest_hash` is captured before the approval loop. Never move that line after any approval check. If you do, the hash could reflect commits the user never actually approved posting about.

**5. Tests mock at the boundary**
OpenAI is mocked via `MagicMock()` injected as the client. PRAW is mocked via `patch("devpost.reddit_poster.praw.Reddit")`. Git is tested with real temp repos (not mocked) because the real behavior matters. Follow this pattern for new integrations.

**6. The dry-run flag must be honored everywhere**
If you add a new external action, gate it with `if not dry_run`. The dry-run contract is: generate and show everything, change nothing in the outside world (no API calls, no clipboard writes, no log updates).
