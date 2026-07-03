import base64
import time
import httpx
from config import IMAGE_API_KEY, VIDEO_MODEL

MOTION_PROMPT = (
    "Slow cinematic push-in. "
    "Soft light shifts gently. "
    "Background mostly still."
)


def generate_promo_video(image_bytes: bytes) -> bytes:
    """Submit image to OpenRouter image-to-video. Returns raw mp4 bytes."""
    b64 = base64.b64encode(image_bytes).decode("utf-8")
    headers = {
        "Authorization": f"Bearer {IMAGE_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": VIDEO_MODEL,
        "prompt": MOTION_PROMPT,
        "frame_images": [
            {
                "type": "image_url",
                "image_url": {"url": f"data:image/png;base64,{b64}"},
                "frame_type": "first_frame",
            }
        ],
        "resolution": "720p",
        "aspect_ratio": "16:9",
        "duration": 5,
    }

    for attempt in range(2):
        try:
            resp = httpx.post(
                "https://openrouter.ai/api/v1/videos",
                headers=headers, json=payload, timeout=30,
            )
            resp.raise_for_status()
            job = resp.json()
            polling_url = job["polling_url"]

            while True:
                time.sleep(15)
                poll = httpx.get(polling_url, headers=headers, timeout=30).json()
                if poll["status"] == "completed":
                    return httpx.get(poll["unsigned_urls"][0], headers=headers, timeout=60).content
                elif poll["status"] == "failed":
                    raise RuntimeError(f"Video job failed: {poll.get('error')}")
        except RuntimeError:
            raise
        except Exception as e:
            if attempt == 1:
                raise RuntimeError(f"Video generation failed: {e}")
