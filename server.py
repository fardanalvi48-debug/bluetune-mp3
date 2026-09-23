import http.server
import socketserver
import json
import os
import re
import threading
import time
import urllib.parse
import yt_dlp

try:
    import imageio_ffmpeg
    _FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()
except Exception:
    _FFMPEG = None

PORT = int(os.environ.get("PORT", 8080))
DOWNLOAD_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "downloads")
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

VIDEO_ID_RE = re.compile(r"(?:youtube\.com/watch\?v=|youtu\.be/|youtube\.com/shorts/|youtube\.com/embed/)([\w-]{11})")

# Track active jobs
jobs = {}


def extract_video_id(url):
    m = VIDEO_ID_RE.search(url)
    return m.group(1) if m else None


def get_info(video_id):
    url = f"https://www.youtube.com/watch?v={video_id}"
    opts = {"quiet": True, "no_warnings": True, "skip_download": True}
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)
    return {
        "title": info.get("title", "Unknown"),
        "duration": info.get("duration", 0),
        "thumbnail": info.get("thumbnail") or f"https://img.youtube.com/vi/{video_id}/mqdefault.jpg",
        "uploader": info.get("uploader", ""),
    }


def convert_audio(job_id, video_id, quality):
    """Download and convert to MP3 in background thread."""
    url = f"https://www.youtube.com/watch?v={video_id}"
    out_path = os.path.join(DOWNLOAD_DIR, f"{job_id}.mp3")

    # Map quality to yt-dlp format
    abr = {"128": "128", "192": "192", "320": "320"}.get(quality, "192")

    opts = {
        "quiet": True,
        "no_warnings": True,
        "format": "bestaudio/best",
        "outtmpl": os.path.join(DOWNLOAD_DIR, f"{job_id}.%(ext)s"),
        if _FFMPEG:
        opts["ffmpeg_location"] = _FFMPEG
    opts["postprocessors"] = [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": abr,
            }
        ],
    }

    try:
        jobs[job_id]["status"] = "downloading"
        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl.download([url])

        if os.path.exists(out_path):
            jobs[job_id]["status"] = "done"
            jobs[job_id]["file"] = out_path
        else:
            jobs[job_id]["status"] = "error"
            jobs[job_id]["error"] = "Conversion file not found"
    except Exception as e:
        jobs[job_id]["status"] = "error"
        jobs[job_id]["error"] = str(e)


class Handler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def send_json(self, data, status=200):
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length)
        try:
            data = json.loads(raw)
        except Exception:
            self.send_json({"error": "Invalid JSON"}, 400)
            return

        parsed = urllib.parse.urlparse(self.path)

        if parsed.path == "/api/info":
            url = data.get("url", "")
            vid = extract_video_id(url)
            if not vid:
                self.send_json({"error": "Invalid YouTube URL"}, 400)
                return
            try:
                info = get_info(vid)
                info["videoId"] = vid
                self.send_json(info)
            except Exception as e:
                self.send_json({"error": str(e)}, 500)

        elif parsed.path == "/api/convert":
            url = data.get("url", "")
            quality = data.get("quality", "192")
            title = data.get("title", "")
            vid = extract_video_id(url)
            if not vid:
                self.send_json({"error": "Invalid YouTube URL"}, 400)
                return

            if not title:
                try:
                    title = get_info(vid)["title"]
                except Exception:
                    title = vid

            job_id = f"{vid}_{quality}_{int(time.time())}"
            jobs[job_id] = {"status": "starting", "videoId": vid, "title": title}

            t = threading.Thread(target=convert_audio, args=(job_id, vid, quality), daemon=True)
            t.start()

            self.send_json({"jobId": job_id, "status": "starting"})

        else:
            self.send_json({"error": "Not found"}, 404)

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)

        # Job status
        if parsed.path.startswith("/api/status/"):
            job_id = parsed.path.split("/api/status/")[1]
            job = jobs.get(job_id)
            if not job:
                self.send_json({"error": "Job not found"}, 404)
                return
            resp = {"status": job["status"]}
            if job["status"] == "error":
                resp["error"] = job.get("error", "Unknown error")
            self.send_json(resp)

        # Download file
        elif parsed.path.startswith("/api/download/"):
            job_id = parsed.path.split("/api/download/")[1]
            job = jobs.get(job_id)
            if not job or job["status"] != "done":
                self.send_json({"error": "File not ready"}, 404)
                return
            file_path = job.get("file")
            if not file_path or not os.path.exists(file_path):
                self.send_json({"error": "File not found"}, 404)
                return

            # Get title for filename
            title = jobs[job_id].get("title", job_id)
            safe = re.sub(r'[\\/*?:"<>|]', "", title)[:80] or job_id

            self.send_response(200)
            self.send_header("Content-Type", "audio/mpeg")
            self.send_header("Content-Disposition", f'attachment; filename="{safe}.mp3"')
            self.send_header("Content-Length", str(os.path.getsize(file_path)))
            self.end_headers()
            with open(file_path, "rb") as f:
                self.wfile.write(f.read())

            # Cleanup after download
            try:
                os.remove(file_path)
                del jobs[job_id]
            except Exception:
                pass

        # Serve static files
        else:
            if parsed.path == "/":
                self.path = "/index.html"
            super().do_GET()


class ThreadedServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


if __name__ == "__main__":
    print(f"BlueTune server running at http://localhost:{PORT}")
    server = ThreadedServer(("0.0.0.0", PORT), Handler)
    server.serve_forever()

