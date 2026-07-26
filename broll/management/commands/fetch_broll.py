"""
Django management command: fetch_broll

Usage:
    uv run python manage.py fetch_broll <srt_file> [options]
"""
import os
from pathlib import Path
from django.core.management.base import BaseCommand, CommandError
from tqdm import tqdm

from broll.runner import run_broll_job
from broll.api_clients import QUALITY_MAP, ORIENTATION_MAP
from broll.ai_analyzer import SPLIT_COUNTS

VALID_QUALITIES = list(QUALITY_MAP.keys())
VALID_RATIOS = list(ORIENTATION_MAP.keys())


class Command(BaseCommand):
    help = "Fetch B-roll media for a video script (SRT) and package into a ZIP file."

    def add_arguments(self, parser):
        parser.add_argument("srt_file", type=str, help="Path to the SRT subtitle/script file.")
        parser.add_argument("--split", choices=["low", "medium", "high"], default="medium",
                            help="B-roll split density: low=5, medium=10, high=15 segments (default: medium).")
        parser.add_argument("--type", dest="media_type", choices=["video", "image"], default="video",
                            help="Media type to search for: video or image (default: video).")
        parser.add_argument("--ratio", choices=VALID_RATIOS, default="16:9",
                            help="Aspect ratio: 16:9 or 9:16 (default: 16:9).")
        parser.add_argument("--quality", choices=VALID_QUALITIES, default="1080p",
                            help=f"Minimum video quality: {', '.join(VALID_QUALITIES)} (default: 1080p).")
        parser.add_argument("--output", type=str, default=None,
                            help="Output ZIP file path (default: broll_<srt_stem>.zip).")
        parser.add_argument("--sources", nargs="+", choices=["pexels", "pixabay"], default=["pexels"],
                            help="Which sources to search (default: pexels). Tried in order; first result wins.")

    def handle(self, *args, **options):
        srt_path = options["srt_file"]
        split_level = options["split"]
        media_type = options["media_type"]
        ratio = options["ratio"]
        quality = options["quality"]
        output_path = options["output"]
        sources = options["sources"]

        if not os.environ.get("OPENROUTER_API_KEY"):
            raise CommandError("OPENROUTER_API_KEY is not set. Please add it to your .env file.")
        if "pexels" in sources and not os.environ.get("PEXELS_API_KEY"):
            raise CommandError("PEXELS_API_KEY is not set.")
        if "pixabay" in sources and not os.environ.get("PIXABAY_API_KEY"):
            raise CommandError("PIXABAY_API_KEY is not set.")
        if not Path(srt_path).is_file():
            raise CommandError(f"SRT file not found: {srt_path}")

        if not output_path:
            output_path = str(Path.cwd() / f"broll_{Path(srt_path).stem}.zip")

        def log(msg):
            self.stdout.write(msg)

        try:
            run_broll_job(
                srt_path=srt_path,
                output_zip=output_path,
                split_level=split_level,
                media_type=media_type,
                ratio=ratio,
                quality=quality,
                sources=sources,
                log=log,
            )
        except Exception as e:
            raise CommandError(str(e))

        self.stdout.write(self.style.SUCCESS(f"\n   ZIP saved to: {output_path}\n"))
