# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# AGENT PATTERN: Stateful Orchestrator with Memory
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# This agent has persistent memory (post_log.py) that changes
# its behaviour across runs. It's not the same each time —
# it remembers what it already posted and adapts.
#
# Patterns demonstrated:
# 1. PERSISTENT STATE: post log consulted before any work
# 2. CONDITIONAL TOOL SELECTION: hash-mode vs time-mode git fetch
# 3. CONTEXT INJECTION: project_context.md grounds generation
# 4. TOOL ORCHESTRATION: coordinates 5 modules as tools
# 5. HUMAN-IN-THE-LOOP: pauses before every external action
# 6. SAFE STATE UPDATE: log only saved if something was posted
#
# Full data flow:
# PostLog.get_last_hash(repo)
#   → if hash: GitReader.get_commits_since_hash(hash)
#   → if none: GitReader.get_commits_last_hours(24)
#   → if empty commits: exit with friendly message
#   → GitReader.summarize_changes(commits)
#   → TweetBuilder.generate(summary, context) [self-correction loop inside]
#   → RedditPoster.generate_all(summary, context)
#   → display each for approval
#   → on approval: post/copy
#   → if anything_posted: PostLog.save_last_hash(repo, newest_hash)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
from pathlib import Path

from openai import OpenAI

from devpost import display
from devpost.config import ConfigManager
from devpost.git_reader import GitReader
from devpost.post_log import PostLog
from devpost.reddit_poster import RedditPoster, SUBREDDIT_PERSONAS
from devpost.tweet_builder import TweetBuilder


class DevPostAgent:
    def __init__(self, config: ConfigManager) -> None:
        self.config = config
        self.client = OpenAI(api_key=config.get("openai_api_key"))
        self.post_log = PostLog()
        self.tweet_builder = TweetBuilder(client=self.client)
        self.reddit_poster = RedditPoster(client=self.client, config=config)
        self.results: dict = {}
        self.anything_posted: bool = False

    def read_context(self, project_path: str) -> str:
        ctx_file = Path(project_path) / "project_context.md"
        if ctx_file.exists():
            return ctx_file.read_text()
        display.print_warning(
            "No project_context.md found. Run 'devpost init' to create one. "
            "Generation will be less specific without context."
        )
        return ""

    def run(self, project_path: str = ".", force: bool = False, dry_run: bool = False) -> dict:
        self.results = {}
        self.anything_posted = False

        display.print_header()

        # Step 1/7 — Read project context
        display.print_step(1, 7, "Reading project context...")
        context = self.read_context(project_path)

        # Step 2/7 — Check post log and fetch commits
        display.print_step(2, 7, "Checking post log and fetching commits...")
        try:
            git_reader = GitReader(project_path)
        except ValueError as e:
            display.print_error(str(e))
            return {"status": "error", "message": str(e)}

        repo_name = Path(project_path).resolve().name
        last_hash = self.post_log.get_last_hash(project_path)

        if force or last_hash is None:
            display.print_post_log_status(False, None, repo_name)
            commits = git_reader.get_commits_last_hours(24)
        else:
            display.print_post_log_status(True, last_hash, repo_name)
            commits = git_reader.get_commits_since_hash(last_hash)

        if not commits:
            if last_hash:
                display.print_no_new_commits(repo_name, last_hash)
            else:
                display.print_warning("No commits found in the last 24 hours. Write some code first!")
            return {"status": "no_new_commits"}

        newest_hash = GitReader.get_newest_hash(commits)
        git_summary = GitReader.summarize_changes(commits)
        display.print_git_summary(git_summary)

        # Step 3/7 — Generate tweet
        display.print_step(3, 7, "Generating tweet...")
        display.print_thinking("Sending Git activity to Claude for tweet generation...")
        if dry_run:
            tweet = f"[DRY RUN] {git_summary[:60]}..."
            char_count = len(tweet)
        else:
            tweet, char_count = self.tweet_builder.generate(git_summary, context)

        # Step 4/7 — Generate Reddit posts
        display.print_step(4, 7, "Generating Reddit posts for 6 subreddits...")
        reddit_enabled = self.reddit_poster.reddit is not None
        if not reddit_enabled and not dry_run:
            display.print_warning(
                "Reddit credentials not configured — skipping Reddit posts. "
                "Run 'devpost setup' to add them."
            )
            reddit_posts = {}
        elif dry_run:
            display.print_thinking("Writing unique posts for each community...")
            reddit_posts = {s: {"title": f"[DRY RUN] r/{s}", "body": "[DRY RUN]"} for s in SUBREDDIT_PERSONAS}
        else:
            display.print_thinking("Writing unique posts for each community...")
            reddit_posts = self.reddit_poster.generate_all(git_summary, context)

        # Step 5/7 — Tweet approval
        display.print_step(5, 7, "Tweet review...")
        if dry_run:
            display.print_tweet_draft(tweet, char_count)
            display.print_thinking("[DRY RUN] Skipping clipboard copy")
            self.results["tweet"] = "dry-run skipped"
        elif display.ask_tweet_approval(tweet, char_count):
            if self.tweet_builder.copy_to_clipboard(tweet):
                display.print_success("Tweet copied to clipboard — paste it on X!")
                self.results["tweet"] = "copied"
                self.anything_posted = True
            else:
                display.print_error("Clipboard copy failed — tweet shown above, copy manually")
                self.results["tweet"] = "failed"
        else:
            display.print_warning("Tweet skipped")
            self.results["tweet"] = "skipped"

        # Step 6/7 — Reddit approval and posting
        display.print_step(6, 7, "Reddit posts review...")
        if not reddit_posts and not dry_run:
            display.print_thinking("No Reddit posts to review.")
        for i, (subreddit, post) in enumerate(reddit_posts.items(), 1):
            if dry_run:
                display.print_reddit_draft(subreddit, post["title"], post["body"], i, len(reddit_posts))
                display.print_thinking(f"[DRY RUN] Skipping post to r/{subreddit}")
                self.results[f"r/{subreddit}"] = "dry-run skipped"
                continue

            if display.ask_reddit_approval(subreddit, post["title"], post["body"], i, len(reddit_posts)):
                display.print_thinking(f"Posting to r/{subreddit}...")
                url = self.reddit_poster.post_to_subreddit(subreddit, post["title"], post["body"])
                if url:
                    display.print_success(f"Posted → {url}")
                    self.results[f"r/{subreddit}"] = f"posted: {url}"
                    self.anything_posted = True
                else:
                    self.results[f"r/{subreddit}"] = "failed"
            else:
                self.results[f"r/{subreddit}"] = "skipped"

        # Step 7/7 — Save post log
        display.print_step(7, 7, "Wrapping up...")
        if self.anything_posted and newest_hash and not dry_run:
            self.post_log.save_last_hash(project_path, newest_hash)
            display.print_post_log_saved(newest_hash)
        elif dry_run:
            display.print_thinking("[DRY RUN] Post log unchanged.")
        else:
            display.print_thinking(
                "Nothing was posted — post log unchanged. Same commits will appear next run."
            )

        display.print_final_summary(self.results)
        return self.results
