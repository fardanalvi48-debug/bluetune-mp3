import os
import re
import json
import threading
import time
import yt_dlp

try:
    import imageio_ffmpeg
    FFMPEG_PATH = imageio_ffmpeg.get_ffmpeg_exe()
except Exception:
    FFMPEG_PATH = None

from flask import Flask, request, send_file, jsonify

app = Flask(__name__)

DOWNLOAD_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "downloads")
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

VIDEO_ID_RE = re.compile(
    r"(?:youtube\.com/watch\?v=|youtu\.be/|youtube\.com/shorts/|youtube\.com/embed/)([\w-]{11})"
)

jobs = {}

ALLOWED_ORIGINS = "*"


def _cors(resp):
    resp.headers["Access-Control-Allow-Origin"] = ALLOWED_ORIGINS
    resp.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    resp.headers["Access-Control-Allow-Headers"] = "Content-Type"
    return resp


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
        "thumbnail": info.get("thumbnail")
        or f"https://img.youtube.com/vi/{video_id}/mqdefault.jpg",
        "uploader": info.get("uploader", ""),
        "videoId": video_id,
    }


def convert_audio(job_id, video_id, quality, title):
    url = f"https://www.youtube.com/watch?v={video_id}"
    out_path = os.path.join(DOWNLOAD_DIR, f"{job_id}.mp3")
    abr = {"128": "128", "192": "192", "320": "320"}.get(str(quality), "192")

    opts = {
        "quiet": True,
        "no_warnings": True,
        "format": "bestaudio/best",
        "outtmpl": os.path.join(DOWNLOAD_DIR, f"{job_id}.%(ext)s"),
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": abr,
            }
        ],
    }
    if FFMPEG_PATH:
        opts["ffmpeg_location"] = FFMPEG_PATH

    try:
        jobs[job_id]["status"] = "downloading"
        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl.download([url])

        if os.path.exists(out_path):
            jobs[job_id]["status"] = "done"
            jobs[job_id]["file"] = out_path
            jobs[job_id]["title"] = title
        else:
            jobs[job_id]["status"] = "error"
            jobs[job_id]["error"] = "File not created"
    except Exception as e:
        jobs[job_id]["status"] = "error"
        jobs[job_id]["error"] = str(e)


@app.after_request
def after_request(response):
    return _cors(response)


@app.route("/api/info", methods=["POST", "OPTIONS"])
def api_info():
    if request.method == "OPTIONS":
        return _cors(app.response_class(status=204))

    data = request.get_json(force=True, silent=True) or {}
    url = data.get("url", "")
    vid = extract_video_id(url)
    if not vid:
        return jsonify({"error": "Invalid YouTube URL"}), 400

    try:
        info = get_info(vid)
        return jsonify(info)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/convert", methods=["POST", "OPTIONS"])
def api_convert():
    if request.method == "OPTIONS":
        return _cors(app.response_class(status=204))

    data = request.get_json(force=True, silent=True) or {}
    url = data.get("url", "")
    quality = data.get("quality", "192")
    title = data.get("title", "")

    vid = extract_video_id(url)
    if not vid:
        return jsonify({"error": "Invalid YouTube URL"}), 400

    if not title:
        try:
            title = get_info(vid)["title"]
        except Exception:
            title = vid

    job_id = f"{vid}_{quality}_{int(time.time())}"
    jobs[job_id] = {"status": "starting", "videoId": vid, "title": title}

    t = threading.Thread(
        target=convert_audio, args=(job_id, vid, quality, title), daemon=True
    )
    t.start()

    return jsonify({"jobId": job_id, "status": "starting"})


@app.route("/api/status/<job_id>", methods=["GET"])
def api_status(job_id):
    job = jobs.get(job_id)
    if not job:
        return jsonify({"error": "Job not found"}), 404
    resp = {"status": job["status"]}
    if job["status"] == "error":
        resp["error"] = job.get("error", "Unknown error")
    return jsonify(resp)


@app.route("/api/download/<job_id>", methods=["GET"])
def api_download(job_id):
    job = jobs.get(job_id)
    if not job or job.get("status") != "done":
        return jsonify({"error": "File not ready"}), 404

    file_path = job.get("file")
    if not file_path or not os.path.exists(file_path):
        return jsonify({"error": "File not found"}), 404

    title = job.get("title", job_id)
    safe = re.sub(r'[\\/*?:"<>|]', "", title)[:80] or job_id

    resp = send_file(file_path, mimetype="audio/mpeg", as_attachment=True,
                     download_name=f"{safe}.mp3")

    try:
        os.remove(file_path)
        del jobs[job_id]
    except Exception:
        pass

    return resp


@app.route("/", defaults={"path": ""})
@app.route("/<path:path>", methods=["GET"])
def static_files(path):
    if not path:
        path = "index.html"
    file_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), path)
    if os.path.isfile(file_path):
        return send_file(file_path)
    return jsonify({"error": "Not found"}), 404


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    app.run(host="0.0.0.0", port=port)
