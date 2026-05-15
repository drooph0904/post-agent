# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# AGENT PATTERN: Self-Correction Loop
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Claude generates a tweet → code checks character count →
# if over 280: sends draft BACK to Claude with the error
# and exact overage → Claude retries → repeat until valid.
#
# The user never sees an over-limit tweet. The loop is
# invisible to them — they only see the final valid draft.
#
# Data flow:
# git_summary + project_context
#   → Claude (attempt 1) → tweet draft
#   → count chars → if >280: chars_over = count - 280
#   → Claude (attempt 2) with previous draft + chars_over
#   → repeat up to 5 times
#   → valid tweet returned to agent.py
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
from typing import Optional

import pyperclip
from openai import OpenAI

from devpost import display


class TweetBuilder:
    def __init__(self, client: OpenAI) -> None:
        self.client = client
        self.max_retries = 5
        self.model = "gpt-4o-mini"

    def _count_chars(self, text: str) -> int:
        return len(text)

    def _build_prompt(
        self,
        git_summary: str,
        context: str,
        previous_attempt: Optional[str] = None,
        chars_over: Optional[int] = None,
    ) -> str:
        if previous_attempt is not None and chars_over is not None:
            return (
                f"Your previous tweet was {chars_over} characters too long "
                f"({len(previous_attempt)} total).\n\n"
                f"Previous attempt:\n{previous_attempt}\n\n"
                f"Rewrite it to be STRICTLY under 280 characters.\n"
                f"Strategies: shorten phrases, cut one hashtag, simplify wording.\n"
                f"Keep the core message. Return ONLY the new tweet text."
            )
        return (
            "You are writing a tweet for a student developer sharing daily coding progress.\n\n"
            "Tone: honest, learning in public, curious, not corporate or hype-y.\n"
            "Show real progress and real struggles — not marketing language.\n\n"
            f"Project context:\n{context}\n\n"
            f"What was built/changed (from Git):\n{git_summary}\n\n"
            "Write ONE tweet that:\n"
            "- Is STRICTLY under 280 characters (count every character)\n"
            "- Shares what was actually built or learned\n"
            "- Feels genuine, like a real student developer talking\n"
            "- If there is a deployment/live URL anywhere in the project context or git commits (huggingface.co, vercel.app, netlify.app, railway.app, render.com, fly.io, GitHub Pages, or any https:// link that looks like a hosted app), include it ONLY when the commits represent a major milestone: new deployment, big feature, or project completion — not for bug fixes or minor changes\n"
            "- Ends with 2-3 relevant hashtags from: #buildinpublic #learntocode "
            "#100daysofcode #webdev #coding #AI #ML #sideproject\n"
            "- Does NOT use em dashes, ellipsis, or overly formal language\n\n"
            "Return ONLY the tweet text. Nothing else."
        )

    def generate(self, git_summary: str, context: str) -> tuple[str, int]:
        previous_attempt: Optional[str] = None
        chars_over: Optional[int] = None

        for attempt in range(1, self.max_retries + 1):
            display.print_thinking(f"Generating tweet (attempt {attempt}/{self.max_retries})...")
            prompt = self._build_prompt(git_summary, context, previous_attempt, chars_over)
            try:
                response = self.client.chat.completions.create(
                    model=self.model,
                    max_tokens=300,
                    messages=[{"role": "user", "content": prompt}],
                    timeout=30.0,
                )
                tweet = response.choices[0].message.content.strip()
            except Exception as e:
                display.print_warning(f"OpenAI API error on attempt {attempt}: {e}")
                continue

            count = self._count_chars(tweet)
            if count <= 280:
                display.print_thinking(f"Tweet valid: {count}/280 chars")
                return tweet, count

            chars_over = count - 280
            display.print_thinking(f"Tweet too long: {count} chars ({chars_over} over). Retrying...")
            previous_attempt = tweet

        # Fallback: truncate at word boundary
        fallback = git_summary[:270].rsplit(" ", 1)[0] + "..."
        return fallback[:280], len(fallback[:280])

    def copy_to_clipboard(self, tweet: str) -> bool:
        try:
            pyperclip.copy(tweet)
            return True
        except Exception as e:
            display.print_warning(f"Clipboard copy failed: {e}\n\nTweet:\n{tweet}")
            return False
