# DevPost Agent

> One command. Your new Git commits → Reddit posts + Tweet to clipboard.
> Smart enough to never post about the same commits twice.

## What It Does

DevPost reads only your NEW Git commits since the last post, uses Claude AI
to write platform-specific content for 6 subreddits and a tweet, shows you
everything for approval, then posts to Reddit and copies the tweet to clipboard.

**The smart part:** A post log tracks which commits have been posted. Running
`devpost run` 3 hours after a previous run will only include the 3 hours of new
commits — never redundant content.

## Agent Patterns In This Code

| Pattern | File | What It Teaches |
|---|---|---|
| Self-correction loop | tweet_builder.py | Agent retries until output is valid |
| Persistent state | post_log.py | Agent memory between runs |
| Context injection | agent.py | Grounding agent in real project info |
| Tool orchestration | agent.py | Coordinating multiple tools |
| Human-in-the-loop | agent.py | Approval before external actions |
| Multi-format output | reddit_poster.py | Same data → different audiences |
| Conditional tool selection | agent.py | Hash-mode vs time-mode based on state |

## Setup

### 1. Install

```bash
git clone <your-repo>
cd devpost
pip install -e .
```

### 2. Get Credentials

- **Anthropic API key:** https://console.anthropic.com
- **Reddit API:** reddit.com/prefs/apps → create app → choose "script"

### 3. Configure

```bash
devpost setup
```

### 4. Initialize your project

```bash
cd your-project-folder
devpost init
# fill in project_context.md
```

### 5. Run after a coding session

```bash
devpost run              # only new commits since last post
devpost run --force      # ignore log, use last 24h (for first run or reset)
devpost run --dry-run    # preview everything, change nothing
devpost status           # see what's been tracked across all projects
devpost reset            # clear log for current project
```

## How the Post Log Works

```
First run:
  No log entry → fetch last 24h of commits → post → save newest hash

Second run (2 hours later):
  Log has hash abc1234 → fetch only commits newer than abc1234
  → 2 new commits found → post → update log to newest hash

Third run (30 min later, no new commits):
  Log has hash → fetch since hash → 0 new commits
  → "Nothing new to post — write some code first!" → exit
  → Log unchanged

Run with --force:
  Ignore log → fetch last 24h → show all recent commits
  → useful for reposting or after a rebase
```

## Cost

- Reddit API: **free**
- Anthropic API: ~$0.01–0.03 per run (`claude-sonnet-4-6`, ~1000 tokens)
- Everything else: **free**
