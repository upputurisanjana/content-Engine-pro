"""
utils.py — Shared helpers used across all modules.

WHY this file exists:
  _get_content and _clean were copy-pasted into text_gen, critique, voiceover,
  and adapt. A single source of truth prevents drift if the DeepSeek response
  format changes again — fix it here once, fixed everywhere.
"""

import re
import time
import logging
import json
from typing import Any

# ── Structured logger ────────────────────────────────────────────────────────
# WHY structured JSON logs: makes it trivial to grep/aggregate by model, cost,
# or status in any log pipeline (CloudWatch, Datadog, local jq queries).
logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",   # raw JSON lines — parsed by log aggregators
)
_logger = logging.getLogger("content_engine")

# ── Estimated cost table (USD per 1k tokens) ────────────────────────────────
# WHY approximate: OpenRouter prices change; these are conservative estimates
# so we never under-report cost to the user.
_COST_PER_1K = {
    "deepseek/deepseek-r1":          {"input": 0.0005, "output": 0.002},
    "bytedance-seed/seedream-4.5":   {"input": 0.0,    "output": 0.04},   # per image
    "alibaba/wan-2.6":               {"input": 0.0,    "output": 0.15},   # per video
    "tts-1":                         {"input": 0.015,  "output": 0.0},    # per 1k chars
}
_DEFAULT_COST = {"input": 0.001, "output": 0.002}


def estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    """Return estimated USD cost for a completion call."""
    rates = _COST_PER_1K.get(model, _DEFAULT_COST)
    return (input_tokens * rates["input"] + output_tokens * rates["output"]) / 1000


# ── Call registry (in-memory, per Streamlit session) ────────────────────────
# WHY a module-level list: Streamlit reruns the whole script on every interaction,
# but module-level state persists across reruns within a session, giving us
# a running total without a database.
_call_log: list[dict] = []


def log_llm_call(
    model: str,
    operation: str,
    input_tokens: int,
    output_tokens: int,
    latency_ms: float,
    status: str = "ok",
    error: str | None = None,
) -> dict:
    """
    Record one LLM/TTS call and return the log entry.

    WHY we log tokens + latency + cost together:
      Latency alone tells you if it's slow. Tokens alone tell you if it's expensive.
      Having all three in one record lets you find the calls that are both slow AND
      expensive — the ones worth optimising first.
    """
    cost = estimate_cost(model, input_tokens, output_tokens)
    entry = {
        "ts":            time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "model":         model,
        "operation":     operation,
        "input_tokens":  input_tokens,
        "output_tokens": output_tokens,
        "total_tokens":  input_tokens + output_tokens,
        "latency_ms":    round(latency_ms, 1),
        "cost_usd":      round(cost, 6),
        "status":        status,
        "error":         error,
    }
    _call_log.append(entry)
    _logger.info(json.dumps(entry))
    return entry


def get_call_log() -> list[dict]:
    """Return all logged calls for this session."""
    return list(_call_log)


def get_session_totals() -> dict:
    """
    Aggregate totals across all calls.

    WHY return a dict not a dataframe: keeps utils.py dependency-free
    (no pandas needed here); callers convert to whatever they need.
    """
    total_tokens = sum(e["total_tokens"] for e in _call_log)
    total_cost   = sum(e["cost_usd"]     for e in _call_log)
    total_calls  = len(_call_log)
    return {
        "calls":        total_calls,
        "total_tokens": total_tokens,
        "total_cost":   round(total_cost, 4),
    }


def clear_call_log() -> None:
    """Reset the call log (called at the start of a new generation run)."""
    _call_log.clear()


# ── Response extraction ──────────────────────────────────────────────────────

def get_content(resp: Any) -> str:
    """
    Safely extract text from a chat completion response.

    WHY the reasoning_content fallback:
      DeepSeek-R1 via OpenRouter sometimes returns content=None and places the
      actual answer in message.reasoning_content instead. Without this fallback
      every DeepSeek call would raise a ValueError.
    """
    msg  = resp.choices[0].message
    text = msg.content
    if not text:
        text = getattr(msg, "reasoning_content", None)
    if not text:
        raise ValueError("Model returned an empty response (both content and reasoning_content are None).")
    return text


def clean(text: str) -> str:
    """
    Strip DeepSeek <think>...</think> reasoning blocks.

    WHY: DeepSeek-R1 prepends its chain-of-thought wrapped in <think> tags.
    Leaving them in corrupts JSON parsing and clutters displayed output.
    """
    return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()


def strip_fences(text: str) -> str:
    """
    Remove markdown code fences (```json ... ```) that some models add
    even when explicitly told not to.

    WHY: json.loads() fails on fenced text. Stripping here means every
    caller can safely call json.loads() without its own fence-removal logic.
    """
    text = text.strip()
    if text.startswith("```"):
        parts = text.split("```")
        # parts[1] is the content between the first pair of fences
        text = parts[1] if len(parts) > 1 else text
        if text.startswith("json"):
            text = text[4:]
        text = text.strip()
    return text


# ── Input sanitisation ───────────────────────────────────────────────────────

# WHY these patterns: prompt injection attacks typically try to override the
# system prompt by inserting meta-instructions. Blocking the most common
# phrases at the boundary prevents the LLM from ever seeing them.
_INJECTION_PATTERNS = re.compile(
    r"(ignore (previous|all|prior|above) (instructions?|prompts?|context)|"
    r"you are now|forget (everything|your instructions?)|"
    r"system prompt|<\|.*?\|>|###\s*instruction|"
    r"act as (a |an )?(?!the\b)\w+\s*(AI|assistant|bot|model|GPT|LLM)?)",
    re.IGNORECASE,
)

MAX_FIELD_LENGTH = 200   # chars — enough for any real product name or audience


def sanitise_input(value: str, field_name: str = "input") -> str:
    """
    Validate and sanitise a user text field.

    Checks:
      1. Not empty after stripping whitespace.
      2. Does not exceed MAX_FIELD_LENGTH characters.
      3. Does not contain prompt injection patterns.

    WHY raise ValueError instead of returning None:
      The caller (app.py) wraps this in a try/except and shows the user a
      friendly message. A ValueError with a descriptive message is more useful
      than a silent None that causes a confusing downstream failure.
    """
    value = value.strip()

    if not value:
        raise ValueError(f"{field_name} cannot be empty.")

    if len(value) > MAX_FIELD_LENGTH:
        raise ValueError(
            f"{field_name} is too long ({len(value)} chars). "
            f"Maximum is {MAX_FIELD_LENGTH} characters."
        )

    if _INJECTION_PATTERNS.search(value):
        raise ValueError(
            f"{field_name} contains disallowed content. "
            "Please describe your product, audience, or tone naturally."
        )

    return value
