import os
import re
import tempfile
import threading
from pathlib import Path
from urllib.parse import urlparse

from flask import Flask, render_template, request, send_file, jsonify
import yt_dlp

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024  # URL form only, not video size

ALLOWED_HOSTS = {
    "youtube.com", "www.youtube.com", "m.youtube.com",
    "music.youtube.com", "youtu.be", "www.youtube-nocookie.com",
}
download_lock = threading.Lock()


def valid_youtube_url(raw_url):
    """Accept only ordinary YouTube URLs, not arbitrary URLs."""
    if not raw_url or len(raw_url) > 2000:
        return False
    try:
        parsed = urlparse(raw_url.strip())
        host = (parsed.hostname or "").lower()
        return parsed.scheme in ("http", "https") and host in ALLOWED_HOSTS
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
        return jsonify(error="Please enter a valid YouTube video URL."), 400

    # Free hosting has limited CPU, memory, disk and request time.
    # Keep this starter app single-download-at-a-time.
    if not download_lock.acquire(blocking=False):
        return jsonify(error="A download is already running. Please try again shortly."), 429

    temp_dir = tempfile.mkdtemp(prefix="yt-download-")
    output_template = os.path.join(temp_dir, "%(title).100s-%(id)s.%(ext)s")

    try:
        options = {
            "outtmpl": output_template,
            "noplaylist": True,
            "quiet": True,
            "no_warnings": True,
            "restrictfilenames": True,
            # Prefer MP4 up to 720p to keep free-hosting resource use reasonable.
            "format": "best[height<=720][ext=mp4]/best[height<=720]/best",
            "merge_output_format": "mp4",
            "socket_timeout": 20,
            "retries": 1,
            "fragment_retries": 1,
        }

        with yt_dlp.YoutubeDL(options) as ydl:
            info = ydl.extract_info(url, download=True)
            title = info.get("title") or "youtube-video"

        candidates = [
            Path(temp_dir) / name
            for name in os.listdir(temp_dir)
            if Path(temp_dir, name).is_file()
            and Path(temp_dir, name).suffix.lower() in {".mp4", ".mkv", ".webm", ".mov"}
        ]
        if not candidates:
            import shutil
            shutil.rmtree(temp_dir, ignore_errors=True)
            download_lock.release()
            return jsonify(error="The video could not be prepared. Try another video."), 422

        video_path = max(candidates, key=lambda p: p.stat().st_size)
        safe_title = re.sub(r"[^A-Za-z0-9._ -]", "", title).strip(" .")[:80] or "youtube-video"
        download_name = safe_title + video_path.suffix

        response = send_file(
            video_path,
            as_attachment=True,
            download_name=download_name,
            conditional=True,
        )

        # Remove temporary files once the response finishes streaming.
        @response.call_on_close
        def cleanup():
            import shutil
            shutil.rmtree(temp_dir, ignore_errors=True)
            download_lock.release()

        return response

    except Exception:
        import shutil
        shutil.rmtree(temp_dir, ignore_errors=True)
        download_lock.release()
        app.logger.exception("Video download failed")
        return jsonify(
            error="Download failed. The video may be unavailable, restricted, or the downloader may need an update."
        ), 502


@app.get("/health")
def health():
    return {"status": "ok"}


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "5000")), debug=False)
