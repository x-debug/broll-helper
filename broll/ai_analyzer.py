"""
AI-powered SRT analyzer: parses SRT subtitles and generates B-roll search terms.
"""
import json
import os
import srt
from openai import OpenAI


def get_openrouter_client() -> OpenAI:
    """Build an OpenAI-compatible client pointing at OpenRouter, with optional proxy."""
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        raise ValueError("OPENROUTER_API_KEY is not set.")

    # Support HTTP proxy (e.g. for regions that need a proxy to reach OpenRouter)
    proxy = os.environ.get("https_proxy") or os.environ.get("HTTPS_PROXY") \
            or os.environ.get("http_proxy") or os.environ.get("HTTP_PROXY")

    import httpx
    http_client = httpx.Client(proxy=proxy) if proxy else None

    return OpenAI(
        api_key=api_key,
        base_url="https://openrouter.ai/api/v1",
        http_client=http_client,
        default_headers={
            "HTTP-Referer": os.environ.get("OPENROUTER_SITE_URL", "https://github.com/broll-helper"),
            "X-Title": os.environ.get("OPENROUTER_APP_NAME", "broll-helper"),
        },
    )

SPLIT_COUNTS = {
    "low": 5,
    "medium": 10,
    "high": 15,
}


def parse_srt(path: str) -> tuple[str, list]:
    """Read an SRT file and return (plain text, subtitle list)."""
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    subtitles = list(srt.parse(content))
    text = " ".join(sub.content.strip() for sub in subtitles)
    return text, subtitles


def _format_subtitles_for_prompt(subtitles: list) -> str:
    """Format subtitles as numbered lines with timestamps for the AI prompt."""
    lines = []
    for sub in subtitles:
        start = str(sub.start).split(".")[0]  # HH:MM:SS
        lines.append(f"[{sub.index}][{start}] {sub.content.strip()}")
    return "\n".join(lines)


def generate_broll_segments(
    script_text: str,
    split_level: str,
    media_type: str,
    subtitles: list | None = None,
    model: str | None = None,
) -> list[dict]:
    """
    Use AI to split the script into B-roll segments and generate search terms.
    Returns a list of dicts: [{segment, query, start_time}, ...]
    """
    count = SPLIT_COUNTS[split_level]
    media_hint = "stock video footage" if media_type == "video" else "stock photo"

    if subtitles:
        script_block = _format_subtitles_for_prompt(subtitles)
        timing_instruction = (
            '- "start_time": the timestamp (HH:MM:SS) of the first subtitle line in this segment\n'
        )
        timing_example = ', "start_time": "00:00:05"'
    else:
        script_block = script_text
        timing_instruction = ""
        timing_example = ""

    prompt = f"""You are a professional video editor assistant. I have a video script below.

Your task:
1. Divide the script into exactly {count} B-roll segments. Each segment should group subtitle lines that share a strong visual theme — prioritize segments with the most vivid, concrete imagery.
2. For each segment, generate a short English search query (2–5 words) optimized for finding {media_hint} on stock libraries like Pexels and Pixabay.

Return ONLY a valid JSON array with exactly {count} objects, each with:
- "segment": a brief summary of the script portion (max 20 words)
- "query": the English stock library search query
{timing_instruction}
Example format:
[
  {{"segment": "Person walking in a busy city", "query": "busy city street walking"{timing_example}}},
  ...
]

Script:
{script_block}"""

    client = get_openrouter_client()
    model = model or os.environ.get("OPENROUTER_MODEL", "openai/gpt-4o-mini")
    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.7,
    )

    raw = response.choices[0].message.content

    # Strip markdown code fences if the model wraps the JSON
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        lines = cleaned.splitlines()
        cleaned = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])

    parsed = json.loads(cleaned)

    # The model may wrap the array in a key
    if isinstance(parsed, dict):
        for v in parsed.values():
            if isinstance(v, list):
                parsed = v
                break

    if not isinstance(parsed, list):
        raise ValueError(f"Unexpected AI response format: {raw}")

    return parsed
