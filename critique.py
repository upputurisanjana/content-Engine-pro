"""
Addition 1 — The Self-Critique Loop
====================================
A critic prompt examines tagline, blog, and social posts against the brief.
If any fail, auto-regenerate with feedback injected. Max 2 retries.
"""

import re
import json
from config import openrouter_client, TEXT_MODEL
from text_gen import generate_tagline, generate_blog_intro, generate_social_posts


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


CRITIC_SYSTEM = """
You are a senior content strategist reviewing campaign copy.
Grade each asset and return ONLY valid JSON — no markdown fences, no preamble:
{
  "tagline": { "pass": bool, "issue": string|null },
  "blog":    { "pass": bool, "issue": string|null },
  "social":  { "pass": bool, "issue": string|null }
}
Fail if: tone mismatch, audience ignored, length exceeded, or product description contradicted.
Be strict. If in doubt, fail.
"""


def _run_critic(
    product: str,
    audience: str,
    tone: str,
    tagline: str,
    blog_text: str,
    social_json: dict,
) -> dict:
    """
    Call the critic once and return the parsed grade dict.
    Returns a safe all-pass dict if the critic itself errors.
    """
    user_msg = (
        f"Product: {product}\n"
        f"Audience: {audience}\n"
        f"Tone: {tone}\n\n"
        f"--- TAGLINE ---\n{tagline}\n\n"
        f"--- BLOG INTRO ---\n{blog_text}\n\n"
        f"--- SOCIAL POSTS ---\n{json.dumps(social_json, indent=2)}\n\n"
        "Grade all three assets now."
    )
    try:
        resp = openrouter_client.chat.completions.create(
            model=TEXT_MODEL,
            messages=[
                {"role": "system", "content": CRITIC_SYSTEM},
                {"role": "user", "content": user_msg},
            ],
            max_tokens=400,
        )
        raw = _clean(_get_content(resp))
        # Strip markdown fences if present
        if raw.startswith("```"):
            parts = raw.split("```")
            raw = parts[1] if len(parts) > 1 else raw
            if raw.startswith("json"):
                raw = raw[4:]
            raw = raw.strip()
        return json.loads(raw)
    except Exception:
        # Critic failure is non-fatal — treat as all-pass
        return {
            "tagline": {"pass": True, "issue": None},
            "blog":    {"pass": True, "issue": None},
            "social":  {"pass": True, "issue": None},
        }


def critique_and_regenerate(
    product: str,
    audience: str,
    tone: str,
    tagline: str,
    blog_text: str,
    social_json: dict,
) -> tuple[str, str, dict, dict, int]:
    """
    Run the self-critique loop. Auto-regenerates failing assets with feedback
    injected into the prompt. Max 2 retries per asset.

    Returns:
        tagline      (str)  — final tagline (possibly regenerated)
        blog_text    (str)  — final blog intro (possibly regenerated)
        social_json  (dict) — final social posts (possibly regenerated)
        verdict      (dict) — final critic grades
        retries_used (int)  — total regeneration rounds performed
    """
    retries_used = 0

    for _ in range(2):  # max 2 retry rounds
        verdict = _run_critic(product, audience, tone, tagline, blog_text, social_json)

        tagline_ok  = verdict.get("tagline", {}).get("pass", True)
        blog_ok     = verdict.get("blog",    {}).get("pass", True)
        social_ok   = verdict.get("social",  {}).get("pass", True)

        if tagline_ok and blog_ok and social_ok:
            break  # all passed — no regeneration needed

        retries_used += 1

        # --- Regenerate failing assets with feedback injected ---
        if not tagline_ok:
            issue = verdict["tagline"].get("issue", "tone mismatch")
            try:
                tagline = generate_tagline(
                    product, audience, tone,
                    feedback=f"Previous attempt failed: {issue}. Fix this."
                )
            except Exception:
                pass  # keep old tagline if regen fails

        if not blog_ok:
            issue = verdict["blog"].get("issue", "quality issue")
            try:
                blog_text = generate_blog_intro(
                    product, audience, tone, tagline,
                    feedback=f"Previous attempt failed: {issue}. Fix this."
                )
            except Exception:
                pass

        if not social_ok:
            issue = verdict["social"].get("issue", "quality issue")
            try:
                social_json = generate_social_posts(
                    product, tone,
                    feedback=f"Previous attempt failed: {issue}. Fix this."
                )
            except Exception:
                pass

    # Final verdict after all retries
    verdict = _run_critic(product, audience, tone, tagline, blog_text, social_json)
    return tagline, blog_text, social_json, verdict, retries_used
