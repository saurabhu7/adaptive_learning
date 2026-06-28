from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from project_settings import YOUTUBE_API_KEY


def extract_playlist_id(url: str) -> str:
    value = (url or "").strip()
    if not value:
        return ""
    parsed = urllib.parse.urlparse(value)
    query = urllib.parse.parse_qs(parsed.query)
    if "list" in query and query["list"]:
        return query["list"][0]
    return ""


def extract_video_id(url: str) -> str:
    value = (url or "").strip()
    if not value:
        return ""
    parsed = urllib.parse.urlparse(value)
    query = urllib.parse.parse_qs(parsed.query)
    if "v" in query and query["v"]:
        return query["v"][0]
    return ""


def _api_get(url: str) -> dict[str, Any] | None:
    try:
        with urllib.request.urlopen(url, timeout=20) as response:
            return json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError):
        return None


def fetch_playlist_lectures(playlist_url: str) -> list[dict[str, str]]:
    playlist_id = extract_playlist_id(playlist_url)
    if not playlist_id or not YOUTUBE_API_KEY:
        return []

    lectures: list[dict[str, str]] = []
    page_token = ""
    for _ in range(6):
        params = {
            "part": "snippet,contentDetails",
            "playlistId": playlist_id,
            "maxResults": "50",
            "key": YOUTUBE_API_KEY,
        }
        if page_token:
            params["pageToken"] = page_token
        url = (
            "https://www.googleapis.com/youtube/v3/playlistItems?"
            + urllib.parse.urlencode(params)
        )
        payload = _api_get(url)
        if not payload:
            break
        for item in payload.get("items", []):
            snippet = item.get("snippet") or {}
            title = str(snippet.get("title", "")).strip()
            resource = snippet.get("resourceId") or {}
            video_id = str(resource.get("videoId", "")).strip()
            if not video_id:
                details = item.get("contentDetails") or {}
                video_id = str(details.get("videoId", "")).strip()
            if not video_id:
                continue
            lectures.append(
                {
                    "title": title or f"Lecture {len(lectures) + 1}",
                    "video_url": f"https://www.youtube.com/watch?v={video_id}",
                }
            )
        page_token = str(payload.get("nextPageToken", "")).strip()
        if not page_token:
            break
    return lectures
