
import os
import shutil
import tempfile
import threading
from pathlib import Path
from urllib.parse import urlparse

import yt_dlp
from flask import Flask, jsonify, render_template, request, send_file

app = Flask(__name__)

# Make Deno installed by Render's build command discoverable.
BASE_DIR = Path(__file__).resolve().parent
DENO_BIN = BASE_DIR / ".deno" / "bin"

if DENO_BIN.is_dir():
    os.environ["PATH"] = (
        str(DENO_BIN) + os.pathsep + os.environ.get("PATH", "")
    )

DENO_PATH = shutil.which("deno")

# Prevent multiple simultaneous downloads on this small public service.
DOWNLOAD_LOCK = threading.Lock()

ALLOWED_HOSTS = {
    "youtube.com",
    "www.youtube.com",
    "m.youtube.com",
    "music.youtube.com",
    "youtu.be",
    "www.youtube-nocookie.com",
    "youtube-nocookie.com",
}


def valid_youtube_url(url):
    """Allow YouTube URLs only."""
    if not isinstance(url, str) or not url.strip():
        return False

    try:
        parsed = urlparse(url.strip())
        hostname = (parsed.hostname or "").lower()

        return (
            parsed.scheme in ("http", "https")
            and hostname in ALLOWED_HOSTS
        )
    except (ValueError, TypeError):
        return False


def get_ffmpeg_path():
    """Use the bundled FFmpeg executable when installed."""
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except (ImportError, RuntimeError):
        return None


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/health")
def health():
    """Check that Flask, yt-dlp, and Deno are available."""
    return jsonify({
        "status": "ok",
        "yt_dlp_version": yt_dlp.version.__version__,
        "deno_found": DENO_PATH is not None,
        "ffmpeg_found": get_ffmpeg_path() is not None,
    })


@app.route("/api/download", methods=["POST"])
def download_video():
    data = request.get_json(silent=True) or {}
    url = (data.get("url") or "").strip()

    if not valid_youtube_url(url):
        return jsonify({
            "error": "Please enter a valid YouTube video URL."
        }), 400

    # Avoid letting public requests queue up unlimited downloads.
    if not DOWNLOAD_LOCK.acquire(blocking=False):
        return jsonify({
            "error": "A download is already in progress. Please try again shortly."
        }), 429

    temp_dir = None

    try:
        temp_dir = tempfile.TemporaryDirectory(prefix="yt_download_")
        output_dir = Path(temp_dir.name)

        options = {
            "format": (
                "bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/"
                "best[height<=720][ext=mp4]/"
                "best[height<=720]"
            ),
            "outtmpl": str(output_dir / "%(id)s.%(ext)s"),
            "merge_output_format": "mp4",
            "noplaylist": True,
            "retries": 3,
            "fragment_retries": 3,
            "socket_timeout": 30,
            "quiet": True,
            "no_warnings": False,
            "restrictfilenames": True,
        }

        # Explicitly configure Deno if it is installed on Render.
        if DENO_PATH:
            options["js_runtimes"] = {
                "deno": {"path": DENO_PATH}
            }

        # FFmpeg is needed to combine separate audio and video streams.
        ffmpeg_path = get_ffmpeg_path()
        if ffmpeg_path:
            options["ffmpeg_location"] = ffmpeg_path

        with yt_dlp.YoutubeDL(options) as ydl:
            ydl.extract_info(url, download=True)

        # Find the final downloaded media file, excluding temporary files.
        ignored_suffixes = {
            ".part", ".ytdl", ".json", ".jpg", ".jpeg",
            ".png", ".webp", ".description", ".vtt", ".srt",
        }

        files = [
            path for path in output_dir.iterdir()
            if path.is_file()
            and path.suffix.lower() not in ignored_suffixes
            and path.stat().st_size > 0
        ]

        if not files:
            raise RuntimeError(
                "Download finished without producing a media file. "
                "Check whether FFmpeg is available."
            )

        # Prefer a video file if the directory contains other files.
        files.sort(
            key=lambda path: (
                path.suffix.lower() in {".mp4", ".mkv", ".webm"},
                path.stat().st_size,
            ),
            reverse=True,
        )
        video_file = files[0]

        response = send_file(
            video_file,
            as_attachment=True,
            download_name=video_file.name,
        )

        # Keep the temporary directory alive until the response is sent.
        response.call_on_close(temp_dir.cleanup)
        return response

    except yt_dlp.utils.DownloadError as exc:
        app.logger.warning("yt-dlp download failed: %s", str(exc)[:1200])

        if temp_dir:
            temp_dir.cleanup()

        return jsonify({
            "error": (
                "YouTube could not provide this video. "
                "It may require additional verification or be unavailable. "
                "Please try again later."
            )
        }), 502

    except Exception:
        app.logger.exception("Unexpected download error")

        if temp_dir:
            temp_dir.cleanup()

        return jsonify({
            "error": (
                "The download failed unexpectedly. "
                "Please check the server logs and try again."
            )
        }), 500

    finally:
        DOWNLOAD_LOCK.release()


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", "5000")),
        debug=False,
    )
