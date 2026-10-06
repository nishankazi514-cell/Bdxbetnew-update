from flask import Flask, send_from_directory
from pathlib import Path
import os

BASE_DIR = Path(__file__).resolve().parent

app = Flask(
    __name__,
    static_folder=str(BASE_DIR),
    static_url_path=""
)


# =========================
# HOME / DASHBOARD
# =========================
@app.get("/")
def home():
    return send_from_directory(BASE_DIR, "index.html")


# =========================
# LUDO
# =========================
@app.get("/ludo")
def ludo():
    return send_from_directory(BASE_DIR, "shuvoludo.html")


# =========================
# HEALTH CHECK
# =========================
@app.get("/health")
def health():
    return {
        "ok": True,
        "service": "BDXbet",
        "ludo": "ready"
    }


# =========================
# OTHER STATIC FILES
# =========================
@app.get("/<path:filename>")
def static_files(filename):
    file_path = BASE_DIR / filename

    if file_path.is_file():
        return send_from_directory(BASE_DIR, filename)

    return "Not Found", 404


# =========================
# RUN SERVER
# =========================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(
        host="0.0.0.0",
        port=port
    )
