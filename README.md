# TubeDrop: Python YouTube downloader website

A beginner-friendly Flask website with a responsive mobile-first interface and a Python `yt-dlp` backend.

## Important notes

- Use only for videos you own, have permission to download, or are otherwise permitted to save. Follow YouTube's terms and applicable law.
- This is a learning/demo project, not a production-ready public service.
- Free hosting has limited CPU, RAM, request duration, outbound bandwidth and temporary disk. Large or long downloads may fail.
- Render's free filesystem is ephemeral. This app creates temporary files and attempts to delete them after sending the response.
- `yt-dlp` compatibility can change as YouTube changes. If downloads fail, check the latest `yt-dlp` release and logs.
- Do not expose this as an unrestricted public downloader without abuse prevention, request limits, monitoring and a stronger job/download architecture.

## Run locally

1. Install Python 3.10+.
2. Open a terminal in this folder.
3. Create and activate a virtual environment (recommended).
4. Install dependencies:

   ```bash
   pip install -r requirements.txt
   ```

5. Start the server:

   ```bash
   python app.py
   ```

6. Open `http://127.0.0.1:5000`.

## Deploy to Render (free web service)

1. Create a GitHub repository and upload the contents of this folder (not the ZIP itself).
2. In Render, choose **New → Web Service** and connect that repository.
3. Render can read `render.yaml`; or configure manually:
   - Build command: `pip install -r requirements.txt`
   - Start command: `gunicorn app:app --workers 1 --threads 2 --timeout 300`
   - Plan: Free
4. Deploy, then open the generated `https://....onrender.com` address.

Free Render services may sleep after inactivity and take time to wake. Temporary files do not persist across restarts/redeploys.

## How the save location works

The Python service prepares a temporary file on the server. Flask sends it to the browser as an attachment. The browser manages the destination on the user's device; the website cannot silently choose any arbitrary folder on the phone or computer.

## Project structure

```text
yt_web_downloader/
├── app.py
├── requirements.txt
├── render.yaml
├── README.md
├── templates/
│   └── index.html
└── static/
    ├── style.css
    └── app.js
```
