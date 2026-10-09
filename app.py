
import os
import re
import shutil
import tempfile
import threading
from pathlib import Path
from urllib.parse import urlparse

from flask import Flask, render_template, request, send_file, jsonify
import yt_dlp

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024

ALLOWED_HOSTS = {
    "youtube.com",
    "www.youtube.com",
    "m.youtube.com",
    "music.youtube.com",
    "youtu.be",
    "www.youtube-nocookie.com",
}

download_lock = threading.Lock()


def valid_youtube_url(raw_url):
    if not raw_url or len(raw_url) > 2000:
        return False

    try:
        parsed = urlparse(raw_url.strip())
        host = (parsed.hostname or "").lower()

        return (
            parsed.scheme in ("http", "https")
            and host in ALLOWED_HOSTS
        )
    except ValueError:
        return False


@app.get("/")
def home():
    return render_template("index.html")


@app.post("/api/download")
def download():
    data = request.get_json(silent=True) or request.form
    url = (data.get("url") or "").strip()

    if not valid_youtube_url(url):
        return jsonify(
            error="Please enter a valid YouTube video URL."
        ), 400

    if not download_lock.acquire(blocking=False):
        return jsonify(
            error="A download is already running. Try again shortly."
        ), 429

    temp_dir = tempfile.mkdtemp(prefix="yt-download-")
    output_template = os.path.join(
        temp_dir, "%(title).100s-%(id)s.%(ext)s"
    )

    try:
        options = {
            "outtmpl": output_template,
            "noplaylist": True,
            "quiet": True,
            "no_warnings": True,
            "restrictfilenames": True,
            "format": (
                "best[height<=720][ext=mp4]"
                "/best[height<=720]/best"
            ),
            "merge_output_format": "mp4",
            "socket_timeout": 30,
            "retries": 1,
            "fragment_retries": 1,
            "extractor_args": {
                "youtube": {
                    "player_client": ["tv"]
                }
            },
        }

        app.logger.info(
            "Starting download with yt-dlp version %s",
            yt_dlp.version.__version__,
        )

        with yt_dlp.YoutubeDL(options) as ydl:
            info = ydl.extract_info(url, download=True)
            title = info.get("title") or "youtube-video"

        candidates = [
            Path(temp_dir) / name
            for name in os.listdir(temp_dir)
            if (Path(temp_dir) / name).is_file()
            and (Path(temp_dir) / name).suffix.lower()
            in {".mp4", ".mkv", ".webm", ".mov"}
        ]

        if not candidates:
            raise RuntimeError(
                "No video file was produced by the downloader."
            )

        video_path = max(
            candidates,
            key=lambda path: path.stat().st_size,
        )

        safe_title = re.sub(
            r"[^A-Za-z0-9._ -]", "", title
        ).strip(" .")[:80] or "youtube-video"

        download_name = safe_title + video_path.suffix

        response = send_file(
            video_path,
            as_attachment=True,
            download_name=download_name,
        )

        def cleanup():
            shutil.rmtree(temp_dir, ignore_errors=True)
            if download_lock.locked():
                download_lock.release()

        response.call_on_close(cleanup)
        return response

    except yt_dlp.utils.DownloadError:
        app.logger.exception("yt-dlp download failed")

        shutil.rmtree(temp_dir, ignore_errors=True)
        download_lock.release()

        return jsonify(
            error=(
                "YouTube could not provide this video. "
                "Check the server logs for the underlying error."
            )
        ), 502

    except Exception:
        app.logger.exception("Unexpected download error")

        shutil.rmtree(temp_dir, ignore_errors=True)
        download_lock.release()

        return jsonify(
            error="The download failed. Please try again later."
        ), 500


@app.get("/health")
def health():
    return {
        "status": "ok",
        "yt_dlp_version": yt_dlp.version.__version__,
    }


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", "5000")),
        debug=False,
    )
