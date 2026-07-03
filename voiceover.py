"""
Addition 2 — Voiceover Generation
===================================
Step 1: SCRIPT_ADAPTER rewrites the blog intro as a TTS-ready voiceover script
        (breath pauses, short sentences, no visual references).
Step 2: OpenAI TTS (tts-1 via OpenRouter) converts the script to mp3 bytes.
"""

import re
from config import openrouter_client, tts_client, TEXT_MODEL, TTS_MODEL


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


SCRIPT_ADAPTER = """
Rewrite this blog intro as a voiceover script.
- Add commas for breath pauses, ellipses (...) for dramatic pauses.
- Short sentences — max 15 words each.
- Remove any visual references (e.g. "as you can see", "shown here").
- Output plain text only. No stage directions, no labels.
"""


def adapt_script(blog_text: str) -> str:
    """
    Convert blog intro prose into a TTS-friendly voiceover script.
    Returns plain text with pause cues.
    """
    for attempt in range(2):
        try:
            resp = openrouter_client.chat.completions.create(
                model=TEXT_MODEL,
                messages=[
                    {"role": "system", "content": SCRIPT_ADAPTER},
                    {"role": "user",   "content": blog_text},
                ],
                max_tokens=600,
            )
            return _clean(_get_content(resp))
        except Exception as e:
            if attempt == 1:
                raise RuntimeError(f"Script adaptation failed: {e}")


def generate_voiceover(blog_text: str) -> tuple[bytes, str]:
    """
    Full voiceover pipeline:
      1. Adapt blog intro to voiceover script.
      2. Generate TTS audio (mp3).

    Returns:
        audio_bytes (bytes) — raw mp3 audio
        script      (str)   — the adapted voiceover script (for display)
    """
    # Step 1: adapt script
    script = adapt_script(blog_text)

    # Step 2: TTS — calls OpenAI directly (OpenRouter does not support audio endpoints)
    for attempt in range(2):
        try:
            response = tts_client.audio.speech.create(
                model=TTS_MODEL,
                voice="alloy",       # neutral, clear voice
                input=script,
                response_format="mp3",
            )
            audio_bytes = response.content if hasattr(response, "content") else response.read()
            return audio_bytes, script
        except Exception as e:
            if attempt == 1:
                raise RuntimeError(f"Voiceover TTS failed: {e}")
