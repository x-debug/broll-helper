import json
import tempfile
import zipfile
from pathlib import Path
from unittest.mock import Mock, patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase

from broll.models import Job
from broll.runner import run_broll_job
from broll.views import _validate_segments


VALID_SEGMENTS = [
    {
        "start_time": "00:00:01",
        "segment": "A person walking through a city",
        "query": "person city walking",
    }
]


class SegmentValidationTests(TestCase):
    def test_normalizes_confirmed_segments(self):
        segments, error = _validate_segments([
            {"start_time": " 00:00:01 ", "segment": " Scene ", "query": " city "}
        ])

        self.assertIsNone(error)
        self.assertEqual(segments, [
            {"start_time": "00:00:01", "segment": "Scene", "query": "city"}
        ])

    def test_rejects_empty_search_query(self):
        segments, error = _validate_segments([
            {"start_time": "00:00:01", "segment": "Scene", "query": " "}
        ])

        self.assertIsNone(segments)
        self.assertIn("search query is required", error)


class ConfirmationFlowTests(TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.jobs_dir = Path(self.temp_dir.name)
        self.jobs_dir_patch = patch("broll.views.JOBS_DIR", self.jobs_dir)
        self.jobs_dir_patch.start()

    def tearDown(self):
        self.jobs_dir_patch.stop()
        self.temp_dir.cleanup()

    @patch("broll.ai_analyzer.generate_broll_segments", return_value=VALID_SEGMENTS)
    @patch("broll.ai_analyzer.parse_srt", return_value=("script", []))
    def test_analyze_only_returns_preview_and_does_not_create_job(self, _parse, _generate):
        upload = SimpleUploadedFile(
            "example.srt",
            b"1\n00:00:00,000 --> 00:00:02,000\nHello\n",
            content_type="application/x-subrip",
        )

        response = self.client.post("/api/analyze/", {
            "srt_file": upload,
            "split": "medium",
            "media_type": "video",
        })

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["segments"], VALID_SEGMENTS)
        self.assertTrue((self.jobs_dir / f'{body["srt_id"]}.srt').is_file())
        self.assertEqual(Job.objects.count(), 0)

    @patch("broll.ai_analyzer.generate_broll_segments", return_value=VALID_SEGMENTS)
    @patch("broll.ai_analyzer.parse_srt", return_value=("script", []))
    def test_regenerate_reuses_uploaded_srt(self, _parse, generate):
        upload = SimpleUploadedFile("example.srt", b"subtitle")
        first = self.client.post("/api/analyze/", {
            "srt_file": upload,
            "split": "low",
            "media_type": "video",
        }).json()

        response = self.client.post("/api/analyze/", {
            "srt_id": first["srt_id"],
            "split": "high",
            "media_type": "image",
        })

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["srt_id"], first["srt_id"])
        self.assertEqual(generate.call_count, 2)
        self.assertEqual(generate.call_args.kwargs["model"] is not None, True)
        self.assertEqual(generate.call_args.args[1:3], ("high", "image"))

    @patch("broll.views.threading.Thread")
    def test_confirm_creates_job_and_starts_pipeline(self, thread_class):
        srt_id = "129ef5ef-bda2-44d8-9fc9-e886129ed38a"
        (self.jobs_dir / f"{srt_id}.srt").write_text("subtitle", encoding="utf-8")
        thread = Mock()
        thread_class.return_value = thread

        response = self.client.post("/api/jobs/", {
            "srt_id": srt_id,
            "segments": json.dumps(VALID_SEGMENTS),
            "split": "medium",
            "media_type": "video",
            "ratio": "16:9",
            "quality": "1080p",
            "sources": ["pexels"],
        })

        self.assertEqual(response.status_code, 201)
        self.assertEqual(Job.objects.count(), 1)
        thread.start.assert_called_once_with()
        args = thread_class.call_args.kwargs["args"]
        self.assertEqual(args[-1], VALID_SEGMENTS)

    @patch("broll.views.threading.Thread")
    def test_confirm_rejects_invalid_segments_before_starting(self, thread_class):
        srt_id = "129ef5ef-bda2-44d8-9fc9-e886129ed38a"
        (self.jobs_dir / f"{srt_id}.srt").write_text("subtitle", encoding="utf-8")

        response = self.client.post("/api/jobs/", {
            "srt_id": srt_id,
            "segments": json.dumps([{"segment": "Scene", "query": ""}]),
        })

        self.assertEqual(response.status_code, 400)
        self.assertEqual(Job.objects.count(), 0)
        thread_class.assert_not_called()


class ConfirmedRunnerTests(TestCase):
    @patch.dict("os.environ", {"PEXELS_API_KEY": "test-key"})
    @patch("broll.runner.requests.get")
    @patch("broll.runner.PexelsClient")
    def test_confirmed_segments_skip_ai_and_complete_package(self, client_class, get):
        client_class.return_value.search_videos.return_value = [{
            "source": "pexels",
            "filename": "clip.mp4",
            "url": "https://example.test/clip.mp4",
        }]
        response = Mock()
        response.headers = {"content-length": "4"}
        response.iter_content.return_value = [b"data"]
        get.return_value = response

        with tempfile.TemporaryDirectory() as temp_dir:
            output_zip = str(Path(temp_dir) / "result.zip")
            run_broll_job(
                srt_path=str(Path(temp_dir) / "unused.srt"),
                output_zip=output_zip,
                split_level="medium",
                media_type="video",
                ratio="16:9",
                quality="1080p",
                sources=["pexels"],
                log=Mock(),
                segments=VALID_SEGMENTS,
            )

            with zipfile.ZipFile(output_zip) as archive:
                manifest = archive.read("manifest.txt").decode("utf-8")
                self.assertIn("medium (1 segments)", manifest)
                self.assertIn('person city walking', manifest)
