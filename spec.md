# Content Engine Pro — Specification

**Course:** GenAI & Agentic AI Engineering — Student Programme  
**Assignment:** Day 3 Homework — Production Upgrade  
**Status:** Implemented

---

## Overview

Content Engine Pro is a Streamlit application that generates a full marketing campaign from a product brief. The user provides a product name, target audience, and brand tone; the app produces a tagline, blog introduction, social media posts, a hero image, and a promotional video.

This spec documents the three additions that upgrade the lab prototype to a production-grade tool: a self-critique loop, voiceover generation, and multi-channel adaptation.

---

## Architecture

### Tech Stack

| Layer | Tool |
|---|---|
| UI | Streamlit |
| Text generation | OpenRouter → DeepSeek R1 (`deepseek/deepseek-r1`) |
| Image generation | OpenRouter → Seedream 4.5 (`bytedance-seed/seedream-4.5`) |
| Video generation | OpenRouter → Wan 2.6 (`alibaba/wan-2.6`) |
| TTS | OpenAI directly → `tts-1` (OpenRouter does not proxy audio) |
| Config | `python-dotenv`, `.env` file |

### Environment Variables

| Variable | Purpose |
|---|---|
| `OPENROUTER_API_KEY` | Text, image, and video calls via OpenRouter |
| `IMAGE_API_KEY` | Image generation key (falls back to `OPENROUTER_API_KEY`) |
| `OPENAI_API_KEY` | TTS audio generation via OpenAI directly |

### File Structure

```
app.py            — Streamlit UI, orchestration, rendering
config.py         — API keys, model names, client instances
text_gen.py       — Tagline, blog intro, social posts generation
image_gen.py      — Hero image generation
video_gen.py      — Promotional video generation
critique.py       — Addition 1: self-critique loop
voiceover.py      — Addition 2: voiceover generation
adapt.py          — Addition 3: multi-channel adaptation
requirements.txt  — streamlit, openai, python-dotenv, httpx
```

---

## Core Generation Pipeline

Triggered when the user clicks **Generate Campaign** with all three sidebar fields filled.

### Inputs (Sidebar)

| Field | Placeholder | Validation |
|---|---|---|
| Product name | "e.g. Sparkling Mango Juice" | Required, non-empty |
| Target audience | "e.g. health-conscious millennials" | Required, non-empty |
| Brand tone | "e.g. playful / premium / eco" | Required, non-empty |

If any field is empty, a warning is shown and generation stops.

### Generation Steps (in order)

1. **Tagline** — few-shot prompting, max 10 words, no hashtags
2. **Blog Introduction** — role-based prompting, ~200 words, weaves in tagline
3. **Social Posts** — structured JSON output: `twitter` (280), `instagram` (2200), `linkedin` (700 chars)
4. **Hero Image** — image prompt formula via Seedream 4.5
5. **Promo Video** — image-to-video from hero image via Wan 2.6 (skipped if image failed)

Each step fails gracefully — an error in one step does not block subsequent steps.

### Prompting Techniques

| Asset | Technique |
|---|---|
| Tagline | Few-shot examples, tone-matched (playful / premium / eco / default) |
| Blog intro | Role-based system prompt as a content strategist |
| Social posts | Structured output — JSON with enforced character limits |
| Hero image | Image prompt formula |
| Voiceover script | Script adapter prompt — adds pause cues, removes visual references |
| Critic | LLM-as-critic with JSON verdict output |
| Channel adaptation | Channel-aware rewriting with tone rules per channel |

---

## Addition 1 — Self-Critique Loop

**File:** `critique.py`  
**Runs:** Automatically after core generation, before output is displayed.

### Behaviour

1. A critic LLM examines the tagline, blog intro, and social posts against the original brief.
2. The critic returns a JSON verdict:
   ```json
   {
     "tagline": { "pass": true/false, "issue": "string or null" },
     "blog":    { "pass": true/false, "issue": "string or null" },
     "social":  { "pass": true/false, "issue": "string or null" }
   }
   ```
3. Any failing asset is regenerated with the critic's issue injected as feedback into the prompt.
4. Maximum **2 retry rounds**. After 2 rounds, the loop stops regardless.
5. A final critic pass runs after all retries to produce the displayed verdict.

### Failure Criteria (Critic)

The critic fails an asset if any of these apply:
- Tone does not match the specified brand tone
- Target audience is ignored
- Character/length limit exceeded
- Product description contradicted

### UI Panel

Displayed below the main campaign output with the heading **🔍 Self-Critique Verdict**.

| State | Display |
|---|---|
| All passed first attempt | Green success: "✅ All assets passed critique on first attempt." |
| Retries were needed | Yellow warning: "⚠️ N regeneration round(s) performed before passing." |
| Each asset | Individual pass ✅ / fail ❌ card with issue description |
| Critic could not run | Info message: "Critique could not run (missing blog or social assets)." |

### Error Handling

If the critic call itself fails (network error, parse error), it returns an all-pass verdict so the output is never blocked.

---

## Addition 2 — Voiceover Generation

**File:** `voiceover.py`  
**Runs:** Automatically after core generation if a blog intro was produced.

### Pipeline

**Step 1 — Script Adaptation**  
The blog intro is rewritten as a TTS-friendly script:
- Commas added for breath pauses; ellipses (`...`) for dramatic pauses
- Max 15 words per sentence
- Visual references removed ("as you can see", "shown here", etc.)
- Plain text output — no stage directions, no labels

**Step 2 — TTS Audio Generation**  
The adapted script is sent to OpenAI's `tts-1` model (voice: `alloy`) and returns raw MP3 bytes.

> Note: OpenAI TTS is called directly (not via OpenRouter) because OpenRouter does not proxy audio endpoints. Requires `OPENAI_API_KEY` in `.env`.

### Output

- **Audio:** Playable in the app via `st.audio()` (MP3 format)
- **Script:** Viewable via an expander: "View voiceover script"

### UI Panel

Displayed with the heading **🎙️ Voiceover**.

| State | Display |
|---|---|
| Audio generated | Audio player widget + script expander |
| Audio unavailable | Info: "Voiceover not available (blog intro required)." |

---

## Addition 3 — Multi-Channel Adaptation

**File:** `adapt.py`  
**Runs:** On demand, triggered by clicking **Adapt for this channel**.

### Supported Channels

| Channel | Tone Rules |
|---|---|
| B2B LinkedIn | Professional, insight-led, minimal emoji, industry language |
| Gen-Z TikTok | Casual, punchy, heavy emoji, slang, short sentences, high energy |
| Parents Facebook | Warm, reassuring, community tone, moderate emoji, clear benefits |

### Behaviour

- The user selects a channel from the dropdown and clicks **Adapt for this channel**.
- The LLM rewrites all three text assets (tagline, blog intro, social posts) for the selected channel.
- **Image and video assets are not regenerated** — they remain unchanged.
- Character limits are enforced on adapted social posts (same as originals).

### Output Format

The model returns a JSON object:
```json
{
  "tagline": "...",
  "blog": "...",
  "social": {
    "twitter": "... (max 280)",
    "instagram": "... (max 2200)",
    "linkedin": "... (max 700)"
  }
}
```

### UI Panel

Displayed with the heading **📢 Multi-Channel Adaptation**.

| State | Display |
|---|---|
| Campaign generated | Dropdown + Adapt button visible |
| After adaptation | Two-column layout: adapted text (left), unchanged hero image (right) |
| No campaign yet | Info: "Generate a campaign first to enable channel adaptation." |

---

## Input Validation & Error Handling

| Scenario | Handling |
|---|---|
| Empty product / audience / tone | `st.warning` shown, generation stops |
| Any generation step fails | `st.error` on that step, pipeline continues |
| Critique loop errors | `st.warning`, output kept as-is |
| Voiceover fails | `st.warning`, voiceover panel shows unavailable message |
| Channel adaptation fails | `st.error` with error message |
| Critic returns unparseable JSON | Treated as all-pass to avoid blocking output |
| TTS / script adaptation fails after 2 attempts | `RuntimeError` raised, caught by `st.warning` in app |

---

## Submission Requirements

- [x] Extended code with comments marking each addition
- [ ] Two captured runs: critic verdicts, voiceover audio, at least one channel adaptation
- [ ] One-paragraph reflection: hardest addition and how RAG (Day 4) or agents (Day 6) would improve it

---

## Stretch Goals (Not Yet Implemented)

| Feature | Description |
|---|---|
| A/B Testing with LLM-as-judge | Generate two versions of each text asset; a separate LLM picks the better one |
| Campaign Brief PDF | Export the full campaign suite as a formatted PDF deck |
| Cost Tracker | Log token counts and estimated costs per API call; display a running total |
| Multilingual | Regenerate all text assets in a user-selected language |

---

## Running the App

```bash
# Install dependencies
pip install -r requirements.txt

# Set environment variables
cp .env.example .env
# Edit .env and fill in OPENROUTER_API_KEY and OPENAI_API_KEY

# Run
streamlit run app.py
```

### `.env` keys required

```
OPENROUTER_API_KEY=sk-or-...
OPENAI_API_KEY=sk-...
```
