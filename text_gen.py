"""
text_gen.py — Text asset generation (tagline, blog intro, social posts).

WHY three separate functions instead of one big generate() call:
  Each asset has a different prompting technique and failure mode. Keeping them
  separate means the critique loop can regenerate just the failing asset without
  re-running the others, saving tokens and latency.
"""

import time
import json
from config import openrouter_client, TEXT_MODEL
from utils import get_content, clean, strip_fences, log_llm_call


# ─────────────────────────────────────────────────────────────────────────────
# Prompt 1: Campaign Tagline — Few-shot prompting
# ─────────────────────────────────────────────────────────────────────────────

TAGLINE_SYSTEM = """
You are a creative director. Generate ONE campaign tagline.
Match the brand tone exactly. Max 10 words. No hashtags.
"""

# WHY tone-bucketed examples: few-shot examples that match the requested tone
# prime the model to stay in that style. Generic examples produce generic output.
FEW_SHOT_EXAMPLES = {
    "playful": [
        {"product": "fizzy lemonade", "tagline": "Squeeze the day, one sip at a time."},
        {"product": "kids sneakers",  "tagline": "Run wild. Jump higher. Repeat."},
    ],
    "premium": [
        {"product": "luxury watch",   "tagline": "Time, perfected for those who demand more."},
        {"product": "silk skincare",  "tagline": "Where science meets the art of beauty."},
    ],
    "eco": [
        {"product": "bamboo toothbrush", "tagline": "Small swap. Big difference for our planet."},
        {"product": "organic coffee",    "tagline": "Good for you. Gentle on the earth."},
    ],
}

DEFAULT_EXAMPLES = [
    {"product": "smart speaker", "tagline": "Your home, smarter than ever before."},
    {"product": "fitness app",   "tagline": "Every rep counts. Every goal matters."},
]


def generate_tagline(
    product: str,
    audience: str,
    tone: str,
    feedback: str | None = None,
) -> str:
    """
    Generate a single campaign tagline using few-shot prompting.

    WHY accept `feedback`: the critique loop calls this function again with the
    critic's issue injected — one function handles both first-pass and retry
    without duplicating prompt logic.
    """
    examples = FEW_SHOT_EXAMPLES.get(tone.lower(), DEFAULT_EXAMPLES)
    shots = "\n".join(
        f'Product: {e["product"]}\nTagline: {e["tagline"]}' for e in examples
    )
    user_prompt = (
        f"{shots}\n\n"
        f"Product: {product}\n"
        f"Audience: {audience}\n"
        f"Tone: {tone}\n"
    )
    if feedback:
        user_prompt += f"\nCritic feedback to address: {feedback}\n"
    user_prompt += "Tagline:"

    for attempt in range(2):
        t0 = time.time()
        try:
            resp = openrouter_client.chat.completions.create(
                model=TEXT_MODEL,
                messages=[
                    {"role": "system", "content": TAGLINE_SYSTEM},
                    {"role": "user",   "content": user_prompt},
                ],
                max_tokens=50,
            )
            latency = (time.time() - t0) * 1000
            # WHY log usage even on success: token counts let us estimate monthly
            # cost before it becomes a surprise on the bill.
            usage = resp.usage or type("u", (), {"prompt_tokens": 0, "completion_tokens": 0})()
            log_llm_call(
                model=TEXT_MODEL,
                operation="tagline",
                input_tokens=getattr(usage, "prompt_tokens", 0),
                output_tokens=getattr(usage, "completion_tokens", 0),
                latency_ms=latency,
            )
            return clean(get_content(resp)).strip('"')
        except Exception as e:
            log_llm_call(
                model=TEXT_MODEL, operation="tagline",
                input_tokens=0, output_tokens=0,
                latency_ms=(time.time() - t0) * 1000,
                status="error", error=str(e),
            )
            if attempt == 1:
                raise RuntimeError(f"Tagline generation failed: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# Prompt 2: Blog Introduction — Role-based prompting
# ─────────────────────────────────────────────────────────────────────────────

def generate_blog_intro(
    product: str,
    audience: str,
    tone: str,
    tagline: str,
    feedback: str | None = None,
) -> str:
    """
    Generate a ~200-word blog introduction using role-based prompting.

    WHY role-based for blog (vs few-shot for tagline): blog intros need sustained
    persona consistency across 200 words. A system-level role ("you are a content
    strategist writing for X") maintains that better than in-context examples.
    """
    system = (
        f"You are a content strategist writing for {audience}. "
        f"Write a 200-word blog intro for {product}. "
        f'Weave in the campaign tagline: "{tagline}". '
        f"Tone: {tone}. "
        "Output exactly 200 words of prose. No headings, no lists."
    )
    user_msg = "Write the 200-word blog introduction now."
    if feedback:
        user_msg += f"\n\nCritic feedback to address: {feedback}"

    for attempt in range(2):
        t0 = time.time()
        try:
            resp = openrouter_client.chat.completions.create(
                model=TEXT_MODEL,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user",   "content": user_msg},
                ],
                max_tokens=350,
            )
            latency = (time.time() - t0) * 1000
            usage = resp.usage or type("u", (), {"prompt_tokens": 0, "completion_tokens": 0})()
            log_llm_call(
                model=TEXT_MODEL, operation="blog_intro",
                input_tokens=getattr(usage, "prompt_tokens", 0),
                output_tokens=getattr(usage, "completion_tokens", 0),
                latency_ms=latency,
            )
            return clean(get_content(resp))
        except Exception as e:
            log_llm_call(
                model=TEXT_MODEL, operation="blog_intro",
                input_tokens=0, output_tokens=0,
                latency_ms=(time.time() - t0) * 1000,
                status="error", error=str(e),
            )
            if attempt == 1:
                raise RuntimeError(f"Blog intro generation failed: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# Prompt 3: Social Posts — Structured JSON output
# ─────────────────────────────────────────────────────────────────────────────

# WHY JSON output for social posts: we need to enforce per-platform character
# limits programmatically. A prose response would require fragile parsing.
# Asking for JSON upfront gives us a reliable dict to truncate against limits.
SOCIAL_SYSTEM = """
Generate social posts for {product}.
Return ONLY JSON:
{{
  "twitter": string (max 280 chars),
  "instagram": string (max 2200 chars),
  "linkedin": string (max 700 chars)
}}
Tone: {tone}. No markdown fences. Each platform's copy must be distinct in style and length.
"""

CHAR_LIMITS = {"twitter": 280, "instagram": 2200, "linkedin": 700}


def generate_social_posts(
    product: str,
    tone: str,
    feedback: str | None = None,
) -> dict:
    """
    Generate platform-specific social posts as a JSON dict.

    WHY hard-enforce char limits after parsing (not just in the prompt):
      LLMs don't count characters reliably. The prompt sets intent; the
      truncation here is the safety net that prevents Twitter over-length posts.
    """
    system = SOCIAL_SYSTEM.format(product=product, tone=tone)
    user_msg = "Generate the social posts now."
    if feedback:
        user_msg += f"\n\nCritic feedback to address: {feedback}"

    for attempt in range(2):
        t0 = time.time()
        try:
            resp = openrouter_client.chat.completions.create(
                model=TEXT_MODEL,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user",   "content": user_msg},
                ],
                max_tokens=400,
            )
            latency = (time.time() - t0) * 1000
            usage = resp.usage or type("u", (), {"prompt_tokens": 0, "completion_tokens": 0})()
            log_llm_call(
                model=TEXT_MODEL, operation="social_posts",
                input_tokens=getattr(usage, "prompt_tokens", 0),
                output_tokens=getattr(usage, "completion_tokens", 0),
                latency_ms=latency,
            )
            raw  = strip_fences(clean(get_content(resp)))
            data = json.loads(raw)
            # Hard-enforce character limits — LLMs can't count chars reliably
            for platform, limit in CHAR_LIMITS.items():
                if platform in data:
                    data[platform] = data[platform][:limit]
            return data
        except json.JSONDecodeError as e:
            log_llm_call(
                model=TEXT_MODEL, operation="social_posts",
                input_tokens=0, output_tokens=0,
                latency_ms=(time.time() - t0) * 1000,
                status="error", error=str(e),
            )
            if attempt == 1:
                raise RuntimeError(f"Social post JSON parse failed: {e}")
        except Exception as e:
            log_llm_call(
                model=TEXT_MODEL, operation="social_posts",
                input_tokens=0, output_tokens=0,
                latency_ms=(time.time() - t0) * 1000,
                status="error", error=str(e),
            )
            if attempt == 1:
                raise RuntimeError(f"Social post generation failed: {e}")
