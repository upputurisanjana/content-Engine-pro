"""
Addition 3 — Multi-Channel Adaptation
=======================================
Rewrites tagline, blog intro, and social posts for a selected audience channel.
Image and video assets are NOT regenerated — only text is adapted.

Supported channels:
  - B2B LinkedIn
  - Gen-Z TikTok
  - Parents Facebook
"""

import re
import json
from config import openrouter_client, TEXT_MODEL

CHANNELS = ["B2B LinkedIn", "Gen-Z TikTok", "Parents Facebook"]


def _get_content(resp) -> str:
    msg = resp.choices[0].message
    text = msg.content
    if not text:
        text = getattr(msg, "reasoning_content", None)
    if not text:
        raise ValueError("Model returned an empty response.")
    return text


def _clean(text: str) -> str:
    """Strip DeepSeek <think>...</think> reasoning blocks if present."""
    return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()


ADAPT_SYSTEM = """
You are a copywriter adapting a campaign for a new channel.
Rewrite the three assets below for: {channel}

Rules:
- Adapt tone, vocabulary, sentence length, and emoji use to match {channel}.
- B2B LinkedIn: professional, insight-led, minimal emoji, industry language.
- Gen-Z TikTok: casual, punchy, heavy emoji, slang, short sentences, energy.
- Parents Facebook: warm, reassuring, community tone, moderate emoji, clear benefits.
- Keep the product name and core message intact — only style changes.
- Return ONLY valid JSON with exactly these three keys, no markdown fences:
{{
  "tagline": string,
  "blog": string,
  "social": {{
    "twitter": string (max 280 chars),
    "instagram": string (max 2200 chars),
    "linkedin": string (max 700 chars)
  }}
}}
"""

CHAR_LIMITS = {"twitter": 280, "instagram": 2200, "linkedin": 700}


def adapt_for_channel(
    channel: str,
    tagline: str,
    blog_text: str,
    social_json: dict,
) -> dict:
    """
    Rewrite text assets for the given channel.

    Args:
        channel    — one of CHANNELS
        tagline    — current campaign tagline
        blog_text  — current blog introduction
        social_json — current social posts dict (twitter/instagram/linkedin)

    Returns dict with keys: tagline, blog, social (same structure as inputs)
    """
    system = ADAPT_SYSTEM.format(channel=channel)
    user_msg = (
        f"Channel: {channel}\n\n"
        f"1. Tagline:\n{tagline}\n\n"
        f"2. Blog intro:\n{blog_text}\n\n"
        f"3. Social posts:\n{json.dumps(social_json, indent=2)}\n\n"
        "Rewrite all three for this channel now."
    )

    for attempt in range(2):
        try:
            resp = openrouter_client.chat.completions.create(
                model=TEXT_MODEL,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user",   "content": user_msg},
                ],
                max_tokens=1200,
            )
            raw = _clean(_get_content(resp))
            # Strip markdown fences if model adds them
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
                raw = raw.strip()
            data = json.loads(raw)
            # Enforce character limits on adapted social posts
            if "social" in data:
                for platform, limit in CHAR_LIMITS.items():
                    if platform in data["social"]:
                        data["social"][platform] = data["social"][platform][:limit]
            return data
        except json.JSONDecodeError as e:
            if attempt == 1:
                raise RuntimeError(f"Channel adaptation JSON parse failed: {e}")
        except Exception as e:
            if attempt == 1:
                raise RuntimeError(f"Channel adaptation failed: {e}")
