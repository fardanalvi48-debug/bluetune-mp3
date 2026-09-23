import yt_dlp
import os

try:
    import imageio_ffmpeg
    FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()
except Exception:
    FFMPEG = None

print("yt-dlp version:", yt_dlp.version.__version__)

clients = ["default", "android", "ios", "mweb", "tv_embedded", "android_vr", "web_embedded"]

for client in clients:
    opts = {
        "quiet": True,
        "no_warnings": True,
        "format": "bestaudio/best",
        "outtmpl": "downloads/test_dl.%(ext)s",
        "postprocessors": [
            {"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "128"}
        ],
    }
    if FFMPEG:
        opts["ffmpeg_location"] = FFMPEG
    if client != "default":
        opts["extractor_args"] = {"youtube": {"player_client": [client]}}

    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl.download(["https://www.youtube.com/watch?v=jNQXAC9IVRw"])
        files = [f for f in os.listdir("downloads") if f.startswith("test_dl")]
        print(f"{client}: OK - {files}")
        for f in files:
            try:
                os.remove(os.path.join("downloads", f))
            except Exception:
                pass
        break
    except Exception as e:
        print(f"{client}: FAIL - {str(e)[:150]}")
        for f in os.listdir("downloads"):
            if f.startswith("test_dl"):
                try:
                    os.remove(os.path.join("downloads", f))
                except Exception:
                    pass
