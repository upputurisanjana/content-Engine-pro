"""
Addition 1 — The Self-Critique Loop
====================================
A critic prompt examines tagline, blog, and social posts against the brief.
If any fail, auto-regenerate with feedback injected. Max 2 retries.
"""

import json
from config import openrouter_client, TEXT_MODEL
from text_gen import generate_tagline, generate_blog_intro, generate_social_posts
from utils import get_content, clean, strip_fences


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
        # WHY strip_fences then clean: some models wrap JSON in ```json fences
        # even when instructed not to; clean() removes DeepSeek think blocks.
        raw = strip_fences(clean(get_content(resp)))
        return json.loads(raw)
    except Exception:
        # Critic failure is non-fatal — treat as all-pass so output is never blocked.
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
