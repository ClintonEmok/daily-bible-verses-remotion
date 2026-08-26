"""
YouTube Data API v3 uploader for Bible Shorts.

Uses OAuth2 web-server (authorization code) flow via google-api-python-client.
Unlike the device flow, this works with "Web application" OAuth credentials
and avoids the 401 invalid_client errors that plague TV/device credential types.

Scopes required:
  https://www.googleapis.com/auth/youtube.upload

One-time setup:
  1. Create a project at https://console.cloud.google.com
  2. Enable the YouTube Data API v3
  3. Go to APIs & Services → Credentials → Create Credentials → OAuth client ID
     → choose "Web application"
  4. Add an Authorized Redirect URI, e.g. http://localhost:8080
  5. Note your Client ID and Client Secret
  6. Run: python -m bible_shorts youtube auth --client-id YOUR_ID --client-secret YOUR_SECRET
     (prints an OAuth consent link, then stores the refresh token)
  7. Done — subsequent calls use the stored refresh token automatically

Config in settings.json:
  "youtube": {
    "client_id": "...",
    "client_secret": "...",
    "refresh_token": "...",    # set automatically after first auth
    "access_token": "...",
    "token_expiry": 0.0,
    "upload_playlist": "..."
  }
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlencode, quote

import requests

# -----------------------------------------------------------------------------
# google-api-python-client (installed separately: pip install google-api-python-client)
# -----------------------------------------------------------------------------


def _build_video_body(
    title: str,
    description: str,
    tags: list[str],
    category_id: str = "22",  # 22 = People & Blogs
    privacy: str = "public",
) -> dict[str, Any]:
    snippet = {
        "title": title[:100],
        "description": description[:5000],
        "tags": [t[:500] for t in (tags or [])],
        "categoryId": category_id,
    }
    status = {
        "privacyStatus": privacy,
        "selfDeclaredMadeForKids": False,
    }
    return {"snippet": snippet, "status": status}


# -----------------------------------------------------------------------------
# Exceptions
# -----------------------------------------------------------------------------


class YouTubeError(RuntimeError):
    """Base exception for YouTube upload failures."""


class YouTubeAuthError(YouTubeError):
    """OAuth2 token fetch or refresh failed."""


class YouTubeUploadError(YouTubeError):
    """Video upload was rejected by the API."""


# -----------------------------------------------------------------------------
# Config helpers
# -----------------------------------------------------------------------------


YOUTUBE_API_BASE = "https://www.googleapis.com/youtube/v3"
YOUTUBE_UPLOAD_BASE = "https://www.googleapis.com/upload/youtube/v3"
TOKEN_URL = "https://oauth2.googleapis.com/token"
AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
SCOPE = "https://www.googleapis.com/auth/youtube.upload https://www.googleapis.com/auth/youtube https://www.googleapis.com/auth/youtube.force-ssl"
REDIRECT_URI = "http://localhost:8080"


@dataclass
class YouTubeConfig:
    """Holds YouTube OAuth2 credentials and tokens, persisted to settings."""

    client_id: str = ""
    client_secret: str = ""
    refresh_token: str = ""
    access_token: str = ""
    token_expiry: float = 0.0  # unix timestamp
    upload_playlist: str = ""

    @classmethod
    def from_settings(cls, settings) -> "YouTubeConfig":
        yt = settings.data.get("youtube", {})
        return cls(
            client_id=yt.get("client_id", ""),
            client_secret=yt.get("client_secret", ""),
            refresh_token=yt.get("refresh_token", ""),
            access_token=yt.get("access_token", ""),
            token_expiry=yt.get("token_expiry", 0.0),
            upload_playlist=yt.get("upload_playlist", ""),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "refresh_token": self.refresh_token,
            "access_token": self.access_token,
            "token_expiry": self.token_expiry,
            "upload_playlist": self.upload_playlist,
        }

    def is_complete(self) -> bool:
        return bool(self.client_id and self.client_secret and self.refresh_token)

    def save_to_settings(self, settings) -> None:
        """Persist current token state back to settings object (caller saves)."""
        if "youtube" not in settings.data:
            settings.data["youtube"] = {}
        settings.data["youtube"].update(self.to_dict())


# -----------------------------------------------------------------------------
# OAuth2 Web-Server (Authorization Code) Flow
# -----------------------------------------------------------------------------


def build_auth_url(client_id: str, redirect_uri: str = REDIRECT_URI) -> str:
    """
    Build the Google OAuth2 authorization URL.
    The user visits this URL, approves access, and gets redirected with a code.
    """
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "scope": SCOPE,
        "response_type": "code",
        "access_type": "offline",
        "prompt": "consent",  # force consent screen so we get a refresh token
    }
    query = urlencode(params, quote_via=quote)
    return f"{AUTH_URL}?{query}"


def exchange_code_for_tokens(
    client_id: str, client_secret: str, code: str, redirect_uri: str = REDIRECT_URI
) -> dict[str, Any]:
    """
    Exchange an authorization code for access + refresh tokens.
    Returns the full token response dict.
    """
    resp = requests.post(
        TOKEN_URL,
        data={
            "client_id": client_id,
            "client_secret": client_secret,
            "code": code,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        },
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    if "error" in data:
        raise YouTubeAuthError(
            f"Token exchange failed: {data.get('error_description', data['error'])}"
        )
    return data


def refresh_access_token(
    client_id: str, client_secret: str, refresh_token: str
) -> tuple[str, float]:
    """
    Exchange a refresh token for a new access token.
    Returns (access_token, expiry_timestamp).
    """
    resp = requests.post(
        TOKEN_URL,
        data={
            "client_id": client_id,
            "client_secret": client_secret,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        },
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    if "error" in data:
        raise YouTubeAuthError(
            f"Token refresh failed: {data.get('error_description', data['error'])}"
        )
    access_token = data["access_token"]
    expires_in = int(data.get("expires_in", 3600))
    # 60-second buffer to avoid edge-case expiry during upload
    expiry = datetime.timestamp(datetime.now(timezone.utc)) + expires_in - 60
    return access_token, expiry


# -----------------------------------------------------------------------------
# Authenticated request helpers
# -----------------------------------------------------------------------------


def _get_access_token(cfg: YouTubeConfig) -> str:
    """Return a valid access token, refreshing if necessary."""
    import time

    if cfg.access_token and time.time() < cfg.token_expiry:
        return cfg.access_token

    if not cfg.refresh_token:
        raise YouTubeAuthError(
            "No refresh token. Run: python -m bible_shorts youtube auth\n"
            "to complete one-time OAuth2 setup."
        )

    access_token, expiry = refresh_access_token(
        cfg.client_id, cfg.client_secret, cfg.refresh_token
    )
    cfg.access_token = access_token
    cfg.token_expiry = expiry
    return access_token


def _api_headers(access_token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }


def api_get(endpoint: str, params: dict[str, Any], cfg: YouTubeConfig) -> dict[str, Any]:
    access_token = _get_access_token(cfg)
    url = f"{YOUTUBE_API_BASE}/{endpoint}"
    resp = requests.get(
        url, headers=_api_headers(access_token), params=params, timeout=30
    )
    resp.raise_for_status()
    return resp.json()


# -----------------------------------------------------------------------------
# Video upload (multipart, using google-api-python-client if available)
# -----------------------------------------------------------------------------


def _get_googleapiclient():
    """Try to import googleapiclient, return None if not installed."""
    try:
        from googleapiclient.discovery import build
        from googleapiclient.http import MediaFileUpload
        from googleapiclient.errors import HttpError

        return build, MediaFileUpload, HttpError
    except ImportError:
        return None


def upload_video(
    video_path: str | Path,
    title: str,
    description: str,
    tags: list[str],
    cfg: YouTubeConfig,
    category_id: str = "22",
    privacy: str = "public",
    notify_subscribers: bool = True,
) -> dict[str, Any]:
    """
    Upload a video to YouTube.

    Uses google-api-python-client if installed (recommended), otherwise falls
    back to a manual multipart upload implementation.

    Returns the API response dict with videoId, snippet, etc.
    Raises YouTubeUploadError on failure.
    """
    video_path = Path(video_path)
    if not video_path.exists():
        raise FileNotFoundError(f"Video file not found: {video_path}")

    # Prefer google-api-python-client
    googleapiclient = _get_googleapiclient()
    if googleapiclient is not None:
        return _upload_video_googleapiclient(
            video_path, title, description, tags, cfg, category_id, privacy, notify_subscribers
        )
    else:
        return _upload_video_manual(
            video_path, title, description, tags, cfg, category_id, privacy
        )


def _upload_video_googleapiclient(
    video_path: Path,
    title: str,
    description: str,
    tags: list[str],
    cfg: YouTubeConfig,
    category_id: str,
    privacy: str,
    notify_subscribers: bool,
) -> dict[str, Any]:
    """
    Upload using google-api-python-client.
    Handles token refresh internally using the refresh_token.
    """
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload
    from googleapiclient.errors import HttpError

    import time

    # Build credentials dict with refresh token — google-api-python-client
    # will auto-refresh when it detects an expired access token
    credentials = {
        "token": cfg.access_token,
        "refresh_token": cfg.refresh_token,
        "client_id": cfg.client_id,
        "client_secret": cfg.client_secret,
        "token_uri": TOKEN_URL,
        "expiry": datetime.fromtimestamp(cfg.token_expiry, tz=timezone.utc).isoformat()
        if cfg.token_expiry
        else None,
    }

    # Use the native OAuth2 credentials object if possible
    try:
        from google.oauth2.credentials import Credentials
        creds = Credentials(
            token=cfg.access_token if cfg.access_token and time.time() < cfg.token_expiry else None,
            refresh_token=cfg.refresh_token,
            client_id=cfg.client_id,
            client_secret=cfg.client_secret,
            token_uri=TOKEN_URL,
        )
    except ImportError:
        # Fall back: build YouTube service with manually managed access token
        creds = None

    if creds is not None:
        youtube = build("youtube", "v3", credentials=creds, static_discovery=False)
    else:
        # No google.oauth2 — manage token manually
        access_token = _get_access_token(cfg)

        class _TokenProvider:
            def __init__(self, token):
                self.token = token

        youtube = build(
            "youtube",
            "v3",
            static_discovery=False,
            developerKey=None,
        )
        # Attach token to the http object manually
        import googleapiclient.http
        http = googleapiclient.http.Http()
        http.headers["Authorization"] = f"Bearer {access_token}"
        youtube._http = http

    body = _build_video_body(title, description, tags, category_id, privacy)
    body["status"]["notifySubscribers"] = notify_subscribers

    media = MediaFileUpload(
        str(video_path),
        chunksize=-1,  # resumable, upload all at once
        resumable=True,
    )

    try:
        request = youtube.videos().insert(
            part=",".join(body.keys()),
            body=body,
            media_body=media,
        )
        # Execute with automatic media chunking
        result = request.execute()
        video_id = result.get("id")
        print(f"  Upload complete! Video ID: {video_id}")
        return result
    except HttpError as e:
        raise YouTubeUploadError(
            f"YouTube API rejected upload (HTTP {e.resp.status}): {e.content.decode()[:500]}"
        )


def _upload_video_manual(
    video_path: Path,
    title: str,
    description: str,
    tags: list[str],
    cfg: YouTubeConfig,
    category_id: str,
    privacy: str,
) -> dict[str, Any]:
    """
    Manual multipart upload without google-api-python-client.
    Used as fallback when the library isn't installed.
    """
    import base64
    import time

    access_token = _get_access_token(cfg)
    video_body = _build_video_body(title, description, tags, category_id, privacy)

    boundary = "".join(
        format(int.from_bytes(os.urandom(8), "big"), "02x") for _ in range(8)
    )
    boundary = f"==============={boundary}=="

    video_bytes = video_path.read_bytes()
    video_size = len(video_bytes)
    content_type = "application/octet-stream"

    metadata_encoded = json.dumps(video_body, separators=(",", ":")).encode("utf-8")

    parts_clean: list[bytes] = []

    # Part 1: metadata
    parts_clean.append(f"--{boundary}\r\n".encode("utf-8"))
    parts_clean.append(b"Content-Type: application/json; charset=UTF-8\r\n")
    parts_clean.append(b"Content-Transfer-Encoding: 8bit\r\n")
    parts_clean.append(f"Content-ID: <metadata>\r\n\r\n".encode("utf-8"))
    parts_clean.append(metadata_encoded)
    parts_clean.append(b"\r\n")

    # Part 2: video binary
    parts_clean.append(f"--{boundary}\r\n".encode("utf-8"))
    parts_clean.append(f"Content-Type: {content_type}\r\n".encode("utf-8"))
    parts_clean.append(b"Content-Transfer-Encoding: binary\r\n")
    parts_clean.append(f"Content-ID: <video-data>\r\n\r\n".encode("utf-8"))
    parts_clean.append(video_bytes)
    parts_clean.append(f"\r\n--{boundary}--\r\n".encode("utf-8"))

    body_bytes = b"".join(parts_clean)

    upload_headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": f"multipart/related; boundary={boundary}",
        "X-Upload-Content-Type": content_type,
        "X-Upload-Content-Length": str(video_size),
    }

    init_url = f"{YOUTUBE_UPLOAD_BASE}/videos?uploadType=multipart&part=snippet,status"
    resp = requests.post(
        init_url,
        headers=upload_headers,
        data=body_bytes,
        timeout=(60, 300),
    )

    if resp.status_code == 401:
        # Token expired mid-upload; refresh and retry once
        cfg.access_token = ""
        access_token = _get_access_token(cfg)
        upload_headers["Authorization"] = f"Bearer {access_token}"
        resp = requests.post(
            init_url,
            headers=upload_headers,
            data=body_bytes,
            timeout=(60, 300),
        )

    if resp.status_code not in (200, 201):
        try:
            err_body = resp.json()
            error_msg = err_body.get("error", {}).get("message", resp.text[:500])
        except Exception:
            error_msg = resp.text[:500]
        raise YouTubeUploadError(
            f"YouTube API rejected upload (HTTP {resp.status_code}): {error_msg}"
        )

    result = resp.json()
    video_id = result.get("id")
    print(f"  Upload complete! Video ID: {video_id}")
    return result


# -----------------------------------------------------------------------------
# Playlist helpers
# -----------------------------------------------------------------------------


def _detect_caption_language(srt_path: str | Path) -> str:
    """Detect the language code of an SRT file. Returns 'en' as default."""
    try:
        with open(srt_path, encoding="utf-8") as f:
            sample = f.read(500)
        return "en"
    except Exception:
        return "en"


def add_to_playlist(
    cfg: YouTubeConfig, playlist_id: str, video_id: str
) -> dict[str, Any]:
    """Add an uploaded video to a specified playlist."""
    access_token = _get_access_token(cfg)

    body = {
        "snippet": {
            "playlistId": playlist_id,
            "resourceId": {"kind": "youtube#video", "videoId": video_id},
        }
    }

    resp = requests.post(
        f"{YOUTUBE_API_BASE}/playlistItems",
        headers=_api_headers(access_token),
        json=body,
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


# -----------------------------------------------------------------------------
# Channel / account info
# -----------------------------------------------------------------------------


def get_channel(cfg: YouTubeConfig) -> dict[str, Any]:
    """Fetch the authenticated user's default channel info."""
    return api_get(
        "channels", {"mine": "true", "part": "snippet,contentDetails"}, cfg
    )


def get_upload_playlist_id(cfg: YouTubeConfig) -> str:
    """Get the 'Uploads' playlist ID for the authenticated channel."""
    data = get_channel(cfg)
    items = data.get("items", [])
    if not items:
        raise YouTubeError("Could not fetch channel info. Check OAuth2 permissions.")
    return items[0]["contentDetails"]["relatedPlaylists"]["uploads"]


# -----------------------------------------------------------------------------
# Upload a Bible Short from its metadata JSON
# -----------------------------------------------------------------------------


@dataclass
class UploadResult:
    video_id: str
    title: str
    mp4_path: str
    meta_path: str
    uploaded_at: str
    playlist_url: str | None = None
    watch_url: str | None = None


def upload_from_meta(
    meta_path: str | Path,
    cfg: YouTubeConfig,
    privacy: str = "public",
) -> UploadResult:
    """
    Upload a Bible Short video given its metadata JSON.

    Extracts title, description, and hashtags from the metadata and
    constructs a YouTube-ready title and description.

    Args:
        meta_path: Path to the .json metadata file next to the MP4
        cfg: YouTubeConfig with valid credentials
        privacy: 'public', 'unlisted', or 'private'

    Returns UploadResult with video_id, URLs, etc.

    The metadata JSON is expected to have:
      - verse.reference
      - script.title
      - script.description
      - script.hashtags
      - script.caption
      - mp4_path (path to the video file)
    """
    meta_path = Path(meta_path)
    with open(meta_path) as f:
        meta = json.load(f)

    verse_ref = meta["verse"]["reference"]
    script = meta.get("script", {})

    # Build title: "Verse: John 2:2 | Daily Bible Short"
    short_title = script.get("title", verse_ref)
    title = f"{short_title} | {verse_ref}"

    # Build description
    caption = script.get("caption", "")
    hashtags = script.get("hashtags", [])
    hashtags_line = " ".join(
        f"#{t}" if not t.startswith("#") else t for t in hashtags
    )

    description_parts = [
        caption,
        "",
        "Today's Scripture",
        f'{script.get("scripture", meta["verse"].get("text", ""))}',
        "",
        "About this channel",
        script.get(
            "description", "A daily Bible Short to encourage your faith."
        ),
        "",
    ]
    if hashtags_line:
        description_parts.append(hashtags_line)

    description = "\n".join(description_parts)

    # Tags from hashtags (YouTube ignores hashtags in description tags for Shorts)
    tags = [h.lstrip("#") for h in hashtags[:15]]  # max 15 tags

    mp4_path = meta.get("mp4_path", meta_path.with_suffix(".mp4"))
    if not Path(mp4_path).exists():
        # Try sibling MP4
        sibling = meta_path.with_suffix(".mp4")
        if sibling.exists():
            mp4_path = str(sibling)
        else:
            raise FileNotFoundError(
                f"Video file not found at {mp4_path} (or sibling {sibling})"
            )

    print(f"Uploading: {title}")
    print(f"  Privacy: {privacy}")

    result = upload_video(
        video_path=mp4_path,
        title=title,
        description=description,
        tags=tags,
        cfg=cfg,
        privacy=privacy,
    )

    video_id = result["id"]
    watch_url = f"https://youtu.be/{video_id}"

    # Add to uploads playlist (the channel's main uploads list)
    playlist_url: str | None = None
    if cfg.upload_playlist:
        try:
            add_to_playlist(cfg, cfg.upload_playlist, video_id)
            playlist_url = f"https://www.youtube.com/playlist?list={cfg.upload_playlist}"
        except Exception as e:
            print(f"  Warning: could not add to playlist: {e}")

    # Update metadata JSON with upload info
    meta["youtube"] = {
        "video_id": video_id,
        "watch_url": watch_url,
        "uploaded_at": datetime.now(timezone.utc).isoformat(),
        "privacy": privacy,
        "playlist_url": playlist_url,
    }
    meta_path.write_text(
        json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    return UploadResult(
        video_id=video_id,
        title=title,
        mp4_path=str(mp4_path),
        meta_path=str(meta_path),
        uploaded_at=meta["youtube"]["uploaded_at"],
        playlist_url=playlist_url,
        watch_url=watch_url,
    )


# -----------------------------------------------------------------------------
# Batch upload: upload all ready-for-upload MP4s in a directory
# -----------------------------------------------------------------------------


def upload_batch(
    directory: str | Path,
    cfg: YouTubeConfig,
    privacy: str = "public",
) -> list[UploadResult]:
    """
    Find all .json metadata files in a directory and upload their videos.

    Only processes files with status == "ready_for_upload" that haven't
    already been uploaded (no youtube.video_id in metadata).
    """
    directory = Path(directory)
    results: list[UploadResult] = []
    meta_files = sorted(directory.rglob("*.json"))

    if not meta_files:
        print(f"No metadata JSON files found in {directory}")
        return results

    # Filter to files that need uploading
    pending: list[Path] = []
    for mf in meta_files:
        if mf.name.endswith("_batch_manifest.json"):
            continue
        with open(mf) as f:
            meta = json.load(f)
        if meta.get("status") != "ready_for_upload":
            continue
        youtube_info = meta.get("youtube")
        if isinstance(youtube_info, dict) and youtube_info.get("video_id"):
            print(f"Skipping {mf.name} — already uploaded")
            continue
        pending.append(mf)

    if not pending:
        print("No videos pending upload.")
        return results

    print(f"\nBatch upload: {len(pending)} video(s)\n")
    print(f"{'Index':<6} {'Title':<50} {'Reference'}")
    print("-" * 80)
    for i, mf in enumerate(pending, 1):
        with open(mf) as f:
            meta = json.load(f)
        script = meta.get("script", {})
        verse_ref = meta.get("verse", {}).get("reference", "?")
        title = (script.get("title", mf.stem)[:48]) if script else mf.stem[:48]
        print(f"  {i:<4} {title:<50} {verse_ref}")

    print()
    try:
        confirm = input("Upload all? [Y/n]: ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        confirm = "n"

    if confirm in ("n", "no"):
        print("Cancelled.")
        return results

    for mf in pending:
        print(f"\n[{len(results) + 1}/{len(pending)}] Uploading {mf.name}")
        try:
            result = upload_from_meta(mf, cfg, privacy=privacy)
            results.append(result)
        except Exception as e:
            print(f"  FAILED: {e}")
            continue

    return results


# -----------------------------------------------------------------------------
# CLI commands (authorization code flow)
# -----------------------------------------------------------------------------


def _load_google_credentials(raw: str) -> tuple[str, str]:
    """
    If 'raw' looks like a JSON string or points to a JSON file, parse it and
    return (client_id, client_secret). Otherwise return (raw, "") as-is.
    Handles two shapes:
      1. The full Google OAuth JSON file:     {"client_id": ..., "client_secret": ...}
      2. A JSON string with just the values:  {"client_id": "...", "client_secret": "..."}
    Also accepts a bare file path to a Google OAuth JSON — tries to load it
    from disk if the string is not valid JSON and the file exists.
    """
    if not raw:
        return "", ""

    text = raw.strip()
    try:
        obj = json.loads(text)
        if isinstance(obj, dict):
            cid = obj.get("client_id", "")
            sec = obj.get("client_secret", "")
            if cid or sec:
                return cid, sec
    except json.JSONDecodeError:
        pass

    # Treat as a file path — try to read from disk
    path = Path(text)
    if path.is_file():
        obj = json.loads(path.read_text())
        inner = obj.get("installed", obj.get("web", obj))
        cid = inner.get("client_id", "")
        sec = inner.get("client_secret", "")
        if cid or sec:
            return cid, sec

    return text, ""


def cmd_auth(settings, client_id: str, client_secret: str) -> None:
    """
    One-time OAuth2 web-server (authorization code) flow.
    Prints the consent link so it can be opened manually, then exchanges the code for tokens.
    """
    cfg = YouTubeConfig.from_settings(settings)

    # Support raw values, JSON strings, or paths to Google's OAuth JSON file
    client_id_from_arg, secret_from_arg = _load_google_credentials(
        client_id or ""
    ), _load_google_credentials(client_secret or "")[0]

    if not client_id:
        client_id = cfg.client_id or os.getenv("YOUTUBE_CLIENT_ID", "")
    if not client_secret:
        client_secret = (
            cfg.client_secret
            or os.getenv("YOUTUBE_CLIENT_SECRET", "")
            or secret_from_arg
        )

    if not client_id or not client_secret:
        raise YouTubeAuthError(
            "client_id and client_secret are required.\n"
            "Pass them as --client-id and --client-secret,\n"
            "or pass a path to Google's OAuth JSON file for both at once,\n"
            "or set YOUTUBE_CLIENT_ID and YOUTUBE_CLIENT_SECRET env vars,\n"
            "or add them to settings.json under youtube.client_id / youtube.client_secret.\n\n"
            "Get credentials at: https://console.cloud.google.com\n"
            "→ APIs & Services → Credentials\n"
            "→ Create Credentials → OAuth client ID → Web application\n"
            "→ Add redirect URI: http://localhost:8080"
        )

    cfg.client_id = client_id
    cfg.client_secret = client_secret

    # Build auth URL and print it for manual browser opening
    auth_url = build_auth_url(client_id)
    print("=" * 60)
    print("YouTube OAuth2 Authorization")
    print("=" * 60)
    print("\nOpen this link in your browser:\n")
    print(f"{auth_url}\n")
    print("After approving access, you'll be redirected to localhost.")
    print("Copy the 'code' parameter from the URL (the part after '?code=').")
    print("Then paste it below and press Enter.\n")
    print("-" * 60)

    # Wait for the user to paste the authorization code
    try:
        code = input("Paste the authorization code here: ").strip()
    except (EOFError, KeyboardInterrupt):
        print("\nCancelled.")
        return

    if not code:
        raise YouTubeAuthError("No authorization code provided. Cancelled.")

    # Exchange code for tokens
    print("\nExchanging code for tokens...")
    token_data = exchange_code_for_tokens(client_id, client_secret, code)
    cfg.refresh_token = token_data["refresh_token"]
    cfg.access_token = token_data["access_token"]
    expires_in = int(token_data.get("expires_in", 3600))
    import time

    cfg.token_expiry = time.time() + expires_in - 60

    # Verify it works
    channel = get_channel(cfg)
    snippet = channel.get("items", [{}])[0].get("snippet", {})
    channel_title = snippet.get("title", "unknown")
    print(f"\nAuthenticated successfully as YouTube channel: {channel_title}")

    # Auto-detect uploads playlist
    uploads_playlist = get_upload_playlist_id(cfg)
    cfg.upload_playlist = uploads_playlist
    print(f"Uploads playlist ID: {uploads_playlist}")

    # Save
    cfg.save_to_settings(settings)
    settings.save()

    print("\n✓ Credentials saved to settings.json")
    print("  Run 'bible-shorts youtube upload' to start uploading videos.")


def cmd_upload(
    settings,
    path: str | Path | None,
    privacy: str = "public",
    skip_playlist: bool = False,
) -> None:
    """Upload a single video or batch from a directory."""
    cfg = YouTubeConfig.from_settings(settings)
    if not cfg.is_complete():
        raise YouTubeAuthError(
            "YouTube credentials not configured. Run first:\n"
            "  python -m bible_shorts youtube auth\n"
        )

    if skip_playlist:
        cfg.upload_playlist = ""

    if path:
        meta_path = Path(path)
        if meta_path.is_dir():
            results = upload_batch(meta_path, cfg, privacy=privacy)
            print(f"\nBatch complete: {len(results)} video(s) uploaded.")
        elif meta_path.is_file() and meta_path.suffix == ".json":
            result = upload_from_meta(meta_path, cfg, privacy=privacy)
            print(f"\nUpload complete!")
            print(f"  Watch: {result.watch_url}")
        else:
            raise ValueError(
                f"Expected a .json metadata file or a directory, got: {path}"
            )
    else:
        output_dir = settings.resolve(settings.paths["output_dir"])
        results = upload_batch(output_dir, cfg, privacy=privacy)
        print(f"\nBatch complete: {len(results)} video(s) uploaded.")
