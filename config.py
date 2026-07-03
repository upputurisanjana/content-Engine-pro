import os
from pathlib import Path
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv(Path(__file__).parent / ".env")

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
IMAGE_API_KEY      = os.getenv("IMAGE_API_KEY", OPENROUTER_API_KEY)
OPENAI_API_KEY     = os.getenv("OPENAI_API_KEY")          # needed only for TTS

# ── Models ──────────────────────────────────────────────────────────────
TEXT_MODEL  = "deepseek/deepseek-r1"
IMAGE_MODEL = "bytedance-seed/seedream-4.5"
VIDEO_MODEL = "alibaba/wan-2.6"          # cheapest image-to-video on OpenRouter
TTS_MODEL   = "tts-1"                    # OpenAI TTS — called directly (not via OpenRouter)

# ── Clients ─────────────────────────────────────────────────────────────
# Text generation (OpenRouter)
openrouter_client = OpenAI(
    api_key=OPENROUTER_API_KEY,
    base_url="https://openrouter.ai/api/v1",
)

# Image / video generation (OpenRouter, same key)
image_client = OpenAI(
    api_key=IMAGE_API_KEY,
    base_url="https://openrouter.ai/api/v1",
)

# TTS — use OpenRouter if no dedicated OPENAI_API_KEY is set
_tts_key     = OPENAI_API_KEY or OPENROUTER_API_KEY
_tts_base    = None if OPENAI_API_KEY else "https://openrouter.ai/api/v1"
tts_client = OpenAI(
    api_key=_tts_key,
    **({"base_url": _tts_base} if _tts_base else {}),
)
