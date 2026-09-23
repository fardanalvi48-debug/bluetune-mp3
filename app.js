let selectedQuality = "192";
let currentData = null;
let pollTimer = null;

function selectQuality(btn) {
    document.querySelectorAll(".q-btn").forEach((b) => b.classList.remove("active"));
    btn.classList.add("active");
    selectedQuality = btn.dataset.quality;
}

function showError(msg) {
    const el = document.getElementById("errorMsg");
    el.textContent = msg;
    el.style.display = "block";
    document.getElementById("resultBox").style.display = "none";
    setTimeout(() => (el.style.display = "none"), 7000);
}

function isValidYouTube(url) {
    const regex = /^(https?:\/\/)?(www\.)?(youtube\.com\/(watch\?v=|shorts\/|embed\/)|youtu\.be\/)[\w-]+/;
    return regex.test(url);
}

function fmtDuration(sec) {
    if (!sec) return "";
    const h = Math.floor(sec / 3600);
    const m = Math.floor((sec % 3600) / 60);
    const s = sec % 60;
    if (h > 0) return `${h}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
    return `${m}:${String(s).padStart(2, "0")}`;
}

function filenameFromDisposition(cd) {
    if (!cd) return null;
    const m = cd.match(/filename="?([^";]+)"?/i);
    return m ? m[1] : null;
}

async function convert() {
    const url = document.getElementById("urlInput").value.trim();
    const btn = document.getElementById("convertBtn");
    const loader = document.getElementById("loader");
    const btnText = btn.querySelector(".btn-text");

    document.getElementById("errorMsg").style.display = "none";

    if (!url) {
        showError("Please paste a YouTube link first.");
        return;
    }
    if (!isValidYouTube(url)) {
        showError("Invalid YouTube URL. Please paste a valid link.");
        return;
    }

    btnText.style.display = "none";
    loader.style.display = "block";
    btn.disabled = true;

    try {
        const res = await fetch("/api/info", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ url }),
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || "Failed to fetch video info");

        currentData = { ...data, url };

        document.getElementById("thumbImg").src = data.thumbnail;
        document.getElementById("videoTitle").textContent = data.title;
        document.getElementById("videoDuration").textContent =
            `${data.uploader} • ${fmtDuration(data.duration)}`;

        resetDownloadBtn();
        document.getElementById("resultBox").style.display = "block";
        document.getElementById("altLinks").innerHTML = "";
    } catch (err) {
        showError(err.message || "Something went wrong. Check your connection.");
    } finally {
        btnText.style.display = "inline";
        loader.style.display = "none";
        btn.disabled = false;
    }
}

function resetDownloadBtn() {
    const btn = document.getElementById("downloadBtn");
    btn.onclick = startConvert;
    btn.innerHTML = "⬇ Convert &amp; Download MP3";
    btn.style.pointerEvents = "auto";
    btn.style.opacity = "1";
}

async function startConvert() {
    if (!currentData) return;

    const btn = document.getElementById("downloadBtn");
    btn.onclick = null;
    btn.innerHTML = "⏳ Converting... Please wait (10-30 sec)";
    btn.style.pointerEvents = "none";
    btn.style.opacity = "0.7";

    try {
        const res = await fetch("/api/convert", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                url: currentData.url,
                quality: selectedQuality,
                title: currentData.title || "",
            }),
        });

        if (!res.ok) {
            let msg = "Conversion failed";
            try {
                const err = await res.json();
                msg = err.error || msg;
            } catch (e) {}
            throw new Error(msg);
        }

        const blob = await res.blob();
        const filename =
            filenameFromDisposition(res.headers.get("Content-Disposition")) ||
            `${currentData.title || "audio"}.mp3`;

        const a = document.createElement("a");
        a.href = URL.createObjectURL(blob);
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        a.remove();
        setTimeout(() => URL.revokeObjectURL(a.href), 5000);

        btn.innerHTML = "✅ Downloaded! Convert another?";
        btn.style.opacity = "1";
        btn.style.pointerEvents = "auto";
        setTimeout(resetDownloadBtn, 2500);
    } catch (err) {
        showError(err.message || "Conversion failed.");
        resetDownloadBtn();
    }
}

document.getElementById("urlInput").addEventListener("keypress", function (e) {
    if (e.key === "Enter") convert();
});

function toggleFaq(item) {
    const wasOpen = item.classList.contains("open");
    document.querySelectorAll(".faq-item").forEach((f) => f.classList.remove("open"));
    if (!wasOpen) item.classList.add("open");
}

document.querySelectorAll('.nav-links a[href^="#"]').forEach((a) => {
    a.addEventListener("click", function (e) {
        e.preventDefault();
        const target = document.querySelector(this.getAttribute("href"));
        if (target) target.scrollIntoView({ behavior: "smooth" });
    });
});
