import base64
import httpx
from config import IMAGE_API_KEY, IMAGE_MODEL

TONE_STYLES = {
    "playful":   "bright flat illustration, vibrant colours",
    "premium":   "photorealistic, studio lighting, luxury aesthetic",
    "eco":       "watercolour, natural earthy tones, soft light",
    "bold":      "high contrast graphic design, bold colours",
    "minimal":   "clean minimalist photography, white background",
    "retro":     "vintage film photography, warm grain",
}


def build_image_prompt(product: str, tagline: str, tone: str) -> str:
    style = TONE_STYLES.get(tone.lower(), "clean modern photography")
    return (
        f"A {style} hero image of {product}. "
        f"Campaign theme: {tagline}. "
        "Centred composition, shallow depth of field, 16:9 aspect ratio. "
        "No text, no logos, no watermarks."
    )


def generate_hero_image(product: str, tagline: str, tone: str) -> bytes:
    """Returns raw image bytes."""
    prompt = build_image_prompt(product, tagline, tone)
    headers = {
        "Authorization": f"Bearer {IMAGE_API_KEY}",
        "Content-Type": "application/json",
    }
    for attempt in range(2):
        try:
            resp = httpx.post(
                "https://openrouter.ai/api/v1/images",
                headers=headers,
                json={"model": IMAGE_MODEL, "prompt": prompt},
                timeout=60,
            )
            resp.raise_for_status()
            data = resp.json()["data"][0]
            if "b64_json" in data:
                return base64.b64decode(data["b64_json"])
            # fallback: URL response
            return httpx.get(data["url"], timeout=30).content
        except Exception as e:
            if attempt == 1:
                raise RuntimeError(f"Hero image generation failed: {e}")
