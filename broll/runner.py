"""
Core B-roll fetch pipeline, shared by the management command and the API.
"""
import os
import zipfile
import tempfile
import requests
from pathlib import Path
from typing import Callable

from broll.ai_analyzer import parse_srt, generate_broll_segments, SPLIT_COUNTS
from broll.api_clients import PexelsClient, PixabayClient, QUALITY_MAP, ORIENTATION_MAP


def run_broll_job(
    srt_path: str,
    output_zip: str,
    split_level: str,
    media_type: str,
    ratio: str,
    quality: str,
    sources: list[str],
    log: Callable[[str], None],
    segments: list[dict] | None = None,  # pre-confirmed segments; skips parse + AI when provided
) -> None:
    """
    Run the full B-roll fetch pipeline.
    If `segments` is provided, skips SRT parsing and AI segmentation.
    """
    pexels_key = os.environ.get("PEXELS_API_KEY")
    pixabay_key = os.environ.get("PIXABAY_API_KEY")
    ai_model = os.environ.get("OPENROUTER_MODEL", "openai/gpt-4o-mini")

    orientation = ORIENTATION_MAP[ratio]
    min_width = QUALITY_MAP[quality]["min_width"]

    pexels = PexelsClient(pexels_key) if "pexels" in sources and pexels_key else None
    pixabay = PixabayClient(pixabay_key) if "pixabay" in sources and pixabay_key else None

    if segments is None:
        # --- Step 1: Parse SRT ---
        log("📄 Parsing SRT file...")
        script_text, subtitles = parse_srt(srt_path)
        log(f"   {len(subtitles)} subtitles, {len(script_text.split())} words")

        # --- Step 2: AI segmentation ---
        count = SPLIT_COUNTS[split_level]
        log(f"🤖 Generating {count} B-roll segments (split={split_level}) via AI...")
        segments = generate_broll_segments(
            script_text, split_level, media_type,
            subtitles=subtitles, model=ai_model,
        )
        log(f"   Generated {len(segments)} segments")
    else:
        log(f"✅ Using {len(segments)} confirmed segments")

    count = len(segments)
    log("分镜列表:")
    for i, seg in enumerate(segments, 1):
        start = seg.get("start_time", "")
        prefix = f"[{start}] " if start else ""
        log(f"   [{i:02d}] {prefix}{seg.get('segment', '')} → \"{seg.get('query', '')}\"")

    # --- Step 3: Search APIs ---
    log(f"🔍 Searching {media_type} ({ratio}, {quality})...")
    all_media = []
    for i, seg in enumerate(segments, 1):
        query = seg.get("query", "")
        log(f"   [{i:02d}] \"{query}\"")
        found = None
        for source in sources:
            try:
                if source == "pexels" and pexels:
                    items = (
                        pexels.search_videos(query, orientation, min_width, per_page=3)
                        if media_type == "video"
                        else pexels.search_photos(query, orientation, per_page=3)
                    )
                elif source == "pixabay" and pixabay:
                    items = (
                        pixabay.search_videos(query, orientation, min_width, per_page=3)
                        if media_type == "video"
                        else pixabay.search_photos(query, orientation, per_page=3)
                    )
                else:
                    continue
                if items:
                    found = items[0]
                    found["segment_index"] = i
                    found["start_time"] = seg.get("start_time", "")
                    found["filename"] = f"seg{i:02d}_" + found["filename"]
                    break
            except Exception as e:
                log(f"      ⚠ {source} error: {e}")

        if found:
            log(f"      ✓ [{found['source']}] {found['filename']}")
            all_media.append(found)
        else:
            log(f"      ⚠ No result for: \"{query}\"")

    if not all_media:
        raise RuntimeError("No media found. Check API keys and network connection.")

    log(f"\n   Total: {len(all_media)} files to download")

    # --- Step 4: Download and ZIP ---
    log("📦 Downloading and packaging...")
    manifest_lines = [
        "B-Roll Manifest",
        "=" * 60,
        f"Split      : {split_level} ({count} segments)",
        f"Media Type : {media_type}",
        f"Ratio      : {ratio}",
        f"Quality    : {quality}",
        "",
        "Segments:",
    ]
    for i, seg in enumerate(segments, 1):
        start = seg.get("start_time", "")
        prefix = f"[{start}] " if start else ""
        manifest_lines.append(f"  [{i:02d}] {prefix}{seg.get('segment', '')} → \"{seg.get('query', '')}\"")
    manifest_lines += ["", "Files (filename | source | segment | start_time):"]

    downloaded = 0
    failed = 0
    seen: set[str] = set()

    Path(output_zip).parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as tmpdir, zipfile.ZipFile(output_zip, "w", zipfile.ZIP_DEFLATED) as zf:
        for item in all_media:
            url = item["url"]
            base_name = item["filename"]

            name = base_name
            counter = 1
            while name in seen:
                stem, ext = os.path.splitext(base_name)
                name = f"{stem}_{counter}{ext}"
                counter += 1
            seen.add(name)

            dest = Path(tmpdir) / name
            try:
                resp = requests.get(url, stream=True, timeout=120)
                resp.raise_for_status()
                total = int(resp.headers.get("content-length", 0))
                size_str = f"{total / 1024 / 1024:.1f} MB" if total else "? MB"
                log(f"   ↓ {name} ({size_str})")
                with open(dest, "wb") as f:
                    for chunk in resp.iter_content(chunk_size=65536):
                        f.write(chunk)
                zf.write(dest, arcname=name)
                start_time = item.get("start_time", "")
                time_col = f" @ {start_time}" if start_time else ""
                manifest_lines.append(f"  {name} | {item['source']} | seg {item['segment_index']:02d}{time_col}")
                downloaded += 1
                log(f"      ✓ downloaded")
            except Exception as e:
                log(f"      ⚠ Failed: {e}")
                failed += 1

        zf.writestr("manifest.txt", "\n".join(manifest_lines))

    log(f"\n✅ Done! {downloaded} downloaded, {failed} failed.")
