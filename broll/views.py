"""
Django API views for B-roll job management.
"""
import json
import os
import threading
import uuid
from pathlib import Path

from django.conf import settings
from django.http import JsonResponse, FileResponse, Http404
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator

from broll.models import Job
from broll.runner import run_broll_job

JOBS_DIR = Path(settings.MEDIA_ROOT) / "jobs"


def _get_srt_path(srt_id: str) -> Path | None:
    """Return the stored SRT path for a valid opaque UUID."""
    try:
        normalized_id = str(uuid.UUID(srt_id))
    except (ValueError, AttributeError, TypeError):
        return None
    return JOBS_DIR / f"{normalized_id}.srt"


def _validate_segments(value) -> tuple[list[dict] | None, str | None]:
    """Validate and normalize user-confirmed segment edits."""
    if not isinstance(value, list) or not value:
        return None, "segments must be a non-empty JSON array"
    if len(value) > 50:
        return None, "segments cannot contain more than 50 items"

    normalized = []
    for index, item in enumerate(value, 1):
        if not isinstance(item, dict):
            return None, f"Segment {index} must be an object"

        segment = str(item.get("segment", "")).strip()
        query = str(item.get("query", "")).strip()
        start_time = str(item.get("start_time", "")).strip()

        if not segment:
            return None, f"Segment {index} description is required"
        if not query:
            return None, f"Segment {index} search query is required"
        if len(segment) > 500:
            return None, f"Segment {index} description is too long"
        if len(query) > 200:
            return None, f"Segment {index} search query is too long"
        if len(start_time) > 20:
            return None, f"Segment {index} start time is too long"

        normalized.append({
            "segment": segment,
            "query": query,
            "start_time": start_time,
        })

    return normalized, None


def _run_job_thread(job_id: str, srt_path: str, output_zip: str, params: dict, segments: list | None):
    """Background thread: run the pipeline and update Job status."""
    from django.db import connection
    connection.close()

    def log(msg: str):
        from broll.models import Job
        job = Job.objects.get(id=job_id)
        job.log_text = job.log_text + msg + "\n"
        job.save(update_fields=["log_text", "updated_at"])

    try:
        Job.objects.filter(id=job_id).update(status=Job.STATUS_RUNNING)
        run_broll_job(
            srt_path=srt_path,
            output_zip=output_zip,
            split_level=params["split"],
            media_type=params["media_type"],
            ratio=params["ratio"],
            quality=params["quality"],
            sources=params["sources"],
            log=log,
            segments=segments,
        )
        Job.objects.filter(id=job_id).update(
            status=Job.STATUS_DONE,
            zip_path=output_zip,
        )
    except Exception as exc:
        log(f"\n❌ Error: {exc}")
        Job.objects.filter(id=job_id).update(
            status=Job.STATUS_FAILED,
            error=str(exc),
        )
    finally:
        try:
            Path(srt_path).unlink(missing_ok=True)
        except Exception:
            pass


@method_decorator(csrf_exempt, name="dispatch")
class AnalyzeView(View):
    """
    POST /api/analyze/
    Upload SRT + params → run AI segmentation → return segments for user review.
    Synchronous (waits for AI response before returning).
    """

    def post(self, request):
        srt_file = request.FILES.get("srt_file")
        existing_srt_id = request.POST.get("srt_id")
        if not srt_file and not existing_srt_id:
            return JsonResponse({"error": "srt_file or srt_id is required"}, status=400)

        split = request.POST.get("split", "medium")
        media_type = request.POST.get("media_type", "video")
        if split not in {"low", "medium", "high"}:
            return JsonResponse({"error": "Invalid split value"}, status=400)
        if media_type not in {"video", "image"}:
            return JsonResponse({"error": "Invalid media_type value"}, status=400)

        JOBS_DIR.mkdir(parents=True, exist_ok=True)
        created_srt = bool(srt_file)
        if created_srt:
            srt_id = str(uuid.uuid4())
            srt_path = JOBS_DIR / f"{srt_id}.srt"
            with open(srt_path, "wb") as f:
                for chunk in srt_file.chunks():
                    f.write(chunk)
        else:
            srt_id = existing_srt_id
            srt_path = _get_srt_path(srt_id)
            if srt_path is None or not srt_path.is_file():
                return JsonResponse({"error": "SRT file not found. Please re-upload."}, status=400)

        try:
            from broll.ai_analyzer import parse_srt, generate_broll_segments
            ai_model = os.environ.get("OPENROUTER_MODEL", "openai/gpt-4o-mini")
            script_text, subtitles = parse_srt(str(srt_path))
            segments = generate_broll_segments(
                script_text, split, media_type,
                subtitles=subtitles, model=ai_model,
            )
            segments, segment_error = _validate_segments(segments)
            if segment_error:
                raise ValueError(f"AI returned invalid segments: {segment_error}")
        except Exception as e:
            if created_srt:
                srt_path.unlink(missing_ok=True)
            return JsonResponse({"error": str(e)}, status=500)

        # Keep the SRT on disk so the confirm step can reference it
        return JsonResponse({"srt_id": srt_path.stem, "segments": segments})


@method_decorator(csrf_exempt, name="dispatch")
class JobListView(View):
    """
    POST /api/jobs/
    Accept srt_id (from /api/analyze/) + confirmed/edited segments + params.
    Starts background download job.
    """

    def post(self, request):
        srt_id = request.POST.get("srt_id")
        if not srt_id:
            return JsonResponse({"error": "srt_id is required"}, status=400)

        srt_path = _get_srt_path(srt_id)
        if srt_path is None or not srt_path.is_file():
            return JsonResponse({"error": "SRT file not found. Please re-upload."}, status=400)

        segments_raw = request.POST.get("segments")
        try:
            segments_value = json.loads(segments_raw) if segments_raw else None
        except json.JSONDecodeError:
            return JsonResponse({"error": "Invalid segments JSON"}, status=400)
        segments, segment_error = _validate_segments(segments_value)
        if segment_error:
            return JsonResponse({"error": segment_error}, status=400)

        sources_raw = request.POST.getlist("sources")
        params = {
            "split": request.POST.get("split", "medium"),
            "media_type": request.POST.get("media_type", "video"),
            "ratio": request.POST.get("ratio", "16:9"),
            "quality": request.POST.get("quality", "1080p"),
            "sources": sources_raw if sources_raw else ["pexels"],
        }
        if params["split"] not in {"low", "medium", "high"}:
            return JsonResponse({"error": "Invalid split value"}, status=400)
        if params["media_type"] not in {"video", "image"}:
            return JsonResponse({"error": "Invalid media_type value"}, status=400)
        if params["ratio"] not in {"16:9", "9:16"}:
            return JsonResponse({"error": "Invalid ratio value"}, status=400)
        if params["quality"] not in {"4k", "1080p", "720p", "480p", "360p"}:
            return JsonResponse({"error": "Invalid quality value"}, status=400)
        if not set(params["sources"]).issubset({"pexels", "pixabay"}):
            return JsonResponse({"error": "Invalid sources value"}, status=400)

        job = Job.objects.create(params=params, srt_path=str(srt_path))
        output_zip = str(JOBS_DIR / f"{job.id}.zip")

        thread = threading.Thread(
            target=_run_job_thread,
            args=(str(job.id), str(srt_path), output_zip, params, segments),
            daemon=True,
        )
        thread.start()

        return JsonResponse({"job_id": str(job.id)}, status=201)


@method_decorator(csrf_exempt, name="dispatch")
class JobDetailView(View):
    """GET /api/jobs/<job_id>/ — poll job status and logs."""

    def get(self, request, job_id):
        try:
            job = Job.objects.get(id=job_id)
        except Job.DoesNotExist:
            return JsonResponse({"error": "Job not found"}, status=404)

        return JsonResponse({
            "job_id": str(job.id),
            "status": job.status,
            "logs": job.log_text.splitlines(),
            "error": job.error,
            "created_at": job.created_at.isoformat(),
        })


class JobDownloadView(View):
    """GET /api/jobs/<job_id>/download/ — download the resulting ZIP."""

    def get(self, request, job_id):
        try:
            job = Job.objects.get(id=job_id)
        except Job.DoesNotExist:
            raise Http404

        if job.status != Job.STATUS_DONE or not job.zip_path:
            return JsonResponse({"error": "ZIP not ready"}, status=400)

        zip_path = Path(job.zip_path)
        if not zip_path.is_file():
            raise Http404

        return FileResponse(
            open(zip_path, "rb"),
            content_type="application/zip",
            as_attachment=True,
            filename=zip_path.name,
        )
