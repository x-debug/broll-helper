"""
B-Roll AI search clients for Pexels and Pixabay.
"""
import os
import requests


PEXELS_BASE = "https://api.pexels.com"
PIXABAY_BASE = "https://pixabay.com/api"

QUALITY_MAP = {
    "4k": {"min_width": 3840},
    "1080p": {"min_width": 1920},
    "720p": {"min_width": 1280},
    "480p": {"min_width": 854},
    "360p": {"min_width": 640},
}

ORIENTATION_MAP = {
    "16:9": "landscape",
    "9:16": "portrait",
}


class PexelsClient:
    def __init__(self, api_key: str):
        self.session = requests.Session()
        self.session.headers.update({"Authorization": api_key})

    def search_videos(self, query: str, orientation: str, min_width: int, per_page: int = 3) -> list[dict]:
        """Search videos and return list of {url, filename}."""
        resp = self.session.get(
            f"{PEXELS_BASE}/videos/search",
            params={
                "query": query,
                "orientation": orientation,
                "per_page": per_page,
            },
            timeout=30,
        )
        resp.raise_for_status()
        results = []
        for video in resp.json().get("videos", []):
            # Pick the best file that meets quality threshold
            files = sorted(video.get("video_files", []), key=lambda f: f.get("width", 0), reverse=True)
            chosen = None
            for f in files:
                if f.get("width", 0) >= min_width:
                    chosen = f
                    break
            if chosen is None and files:
                chosen = files[0]  # fallback to best available
            if chosen:
                results.append({
                    "url": chosen["link"],
                    "filename": f"pexels_{video['id']}.mp4",
                    "source": "pexels",
                })
        return results

    def search_photos(self, query: str, orientation: str, per_page: int = 3) -> list[dict]:
        resp = self.session.get(
            f"{PEXELS_BASE}/v1/search",
            params={
                "query": query,
                "orientation": orientation,
                "per_page": per_page,
            },
            timeout=30,
        )
        resp.raise_for_status()
        results = []
        for photo in resp.json().get("photos", []):
            results.append({
                "url": photo["src"]["original"],
                "filename": f"pexels_{photo['id']}.jpg",
                "source": "pexels",
            })
        return results


class PixabayClient:
    def __init__(self, api_key: str):
        self.api_key = api_key

    def search_videos(self, query: str, orientation: str, min_width: int, per_page: int = 3) -> list[dict]:
        orientation_map = {"landscape": "horizontal", "portrait": "vertical"}
        # Pixabay requires per_page >= 3
        per_page = max(3, per_page)
        resp = requests.get(
            f"{PIXABAY_BASE}/videos/",
            params={
                "key": self.api_key,
                "q": query,
                "orientation": orientation_map.get(orientation, "horizontal"),
                "per_page": per_page,
            },
            timeout=30,
        )
        resp.raise_for_status()
        results = []
        for hit in resp.json().get("hits", []):
            videos = hit.get("videos", {})
            # Pick best quality available
            for quality in ("large", "medium", "small", "tiny"):
                v = videos.get(quality)
                if v and v.get("width", 0) >= min_width:
                    results.append({
                        "url": v["url"],
                        "filename": f"pixabay_{hit['id']}.mp4",
                        "source": "pixabay",
                    })
                    break
            else:
                # fallback: pick largest regardless
                for quality in ("large", "medium", "small", "tiny"):
                    v = videos.get(quality)
                    if v:
                        results.append({
                            "url": v["url"],
                            "filename": f"pixabay_{hit['id']}.mp4",
                            "source": "pixabay",
                        })
                        break
        return results

    def search_photos(self, query: str, orientation: str, per_page: int = 3) -> list[dict]:
        orientation_map = {"landscape": "horizontal", "portrait": "vertical"}
        # Pixabay requires per_page >= 3
        per_page = max(3, per_page)
        resp = requests.get(
            f"{PIXABAY_BASE}/",
            params={
                "key": self.api_key,
                "q": query,
                "orientation": orientation_map.get(orientation, "horizontal"),
                "per_page": per_page,
                "image_type": "photo",
            },
            timeout=30,
        )
        resp.raise_for_status()
        results = []
        for hit in resp.json().get("hits", []):
            results.append({
                "url": hit["largeImageURL"],
                "filename": f"pixabay_{hit['id']}.jpg",
                "source": "pixabay",
            })
        return results
