# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# AGENT PATTERN: Context-Aware Multi-Output Generation
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Same Git commits → 6 different Reddit posts.
# Each uses a subreddit-specific persona prompt that tells
# Claude the community's culture and expectations.
#
# Data flow:
# git_summary + project_context → for each subreddit:
#   persona prompt → Claude → {title, body} JSON
#   → display for approval → PRAW post → URL returned
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
import json
from typing import Optional

import praw
from openai import OpenAI

from devpost import display
from devpost.config import ConfigManager

SUBREDDIT_PERSONAS: dict[str, dict[str, str]] = {
    "SideProject": {
        "audience": "makers and indie developers who love seeing what others are building",
        "tone": "excited but genuine, share what you built and why",
        "focus": "the product, the idea, the progress milestone",
        "title_style": "I built [X] today — here's what I learned",
        "depth": "medium — 150-250 words",
    },
    "webdev": {
        "audience": "web developers interested in technical implementation",
        "tone": "technical but approachable, share the stack and decisions",
        "focus": "technical choices, what worked, what didn't",
        "title_style": "Built [feature] with [tech] — ran into [problem], here's how I solved it",
        "depth": "technical — 200-300 words with some code context",
    },
    "learnprogramming": {
        "audience": "students and beginners learning to code",
        "tone": "honest about struggles, encouraging, share what you learned not just what you built",
        "focus": "the learning journey, mistakes made, concepts understood",
        "title_style": "Day [X] of learning — finally understood [concept]",
        "depth": "personal — 150-200 words, mention specific things you struggled with",
    },
    "coding": {
        "audience": "general programmers who enjoy seeing coding projects",
        "tone": "casual and friendly, like talking to a fellow dev",
        "focus": "what you coded, interesting problems, progress update",
        "title_style": "Working on [project] — made good progress on [feature] today",
        "depth": "casual — 100-200 words",
    },
    "artificial": {
        "audience": "AI enthusiasts interested in projects using AI/ML",
        "tone": "technically curious, focus on the AI aspect if any",
        "focus": "any AI/ML components, APIs used, interesting behaviors observed",
        "title_style": "Using [AI tool/API] to build [thing] — interesting results",
        "depth": "technical and curious — 200-250 words",
    },
    "MachineLearning": {
        "audience": "ML researchers and practitioners, more technical crowd",
        "tone": "precise and technical, respect the audience's expertise",
        "focus": "technical architecture, model choices, data handling, results",
        "title_style": "[Technical description of what you built or experimented with]",
        "depth": "detailed technical — 250-350 words, use proper ML terminology",
    },
}


class RedditPoster:
    def __init__(self, client: OpenAI, config: ConfigManager) -> None:
        self.client = client
        self.model = "gpt-4o-mini"
        client_id = config.get("reddit_client_id")
        if client_id is None:
            # No credentials present — defer reddit init (e.g. dry-run mode)
            self.reddit = None
            return
        try:
            self.reddit = praw.Reddit(
                client_id=client_id,
                client_secret=config.get("reddit_client_secret"),
                username=config.get("reddit_username"),
                password=config.get("reddit_password"),
                user_agent=config.get("reddit_user_agent", "devpost-agent/0.1"),
            )
        except Exception as e:
            display.print_error(f"Reddit initialization failed: {e}")
            raise

    def validate_credentials(self) -> bool:
        if self.reddit is None:
            return False
        try:
            self.reddit.user.me()
            return True
        except Exception:
            return False

    def _generate_post(self, subreddit: str, git_summary: str, context: str) -> dict:
        persona = SUBREDDIT_PERSONAS[subreddit]
        prompt = (
            f"Write a Reddit post for r/{subreddit}.\n\n"
            f"Audience: {persona['audience']}\n"
            f"Tone: {persona['tone']}\n"
            f"Focus: {persona['focus']}\n"
            f"Title style: {persona['title_style']}\n"
            f"Depth: {persona['depth']}\n\n"
            f"Project context:\n{context}\n\n"
            f"Git activity:\n{git_summary}\n\n"
            f"Author is a student developer learning in public. Be genuine, not corporate.\n\n"
            f'Return ONLY a JSON object: {{"title": "...", "body": "..."}}\n'
            f"No markdown fences, no explanation — raw JSON only."
        )
        response = self.client.chat.completions.create(
            model=self.model,
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
            timeout=30.0,
        )
        raw = response.choices[0].message.content.strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1].rsplit("```", 1)[0].strip()
        data = json.loads(raw)
        return {"title": data["title"], "body": data["body"]}

    def generate_all(self, git_summary: str, context: str) -> dict[str, dict]:
        results: dict[str, dict] = {}
        for subreddit in SUBREDDIT_PERSONAS:
            display.print_thinking(f"Generating post for r/{subreddit}...")
            try:
                results[subreddit] = self._generate_post(subreddit, git_summary, context)
            except Exception as e:
                display.print_error(f"Failed to generate post for r/{subreddit}: {e}")
                results[subreddit] = {"title": "[generation failed]", "body": ""}
        return results

    def post_to_subreddit(self, subreddit: str, title: str, body: str) -> Optional[str]:
        if self.reddit is None:
            display.print_error(f"Reddit not initialized — cannot post to r/{subreddit}")
            return None
        try:
            submission = self.reddit.subreddit(subreddit).submit(title=title, selftext=body)
            return submission.url
        except Exception as e:
            display.print_error(f"Failed to post to r/{subreddit}: {e}")
            return None
