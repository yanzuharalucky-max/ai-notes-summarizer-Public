from flask import Flask, render_template, request, redirect, url_for, send_file, session, flash, jsonify
from deep_translator import GoogleTranslator
from langdetect import detect
from docx import Document
import speech_recognition as sr           # 🔥 DITAMBAHKAN
import tempfile                           # 🔥 DITAMBAHKAN
import pytesseract
from PIL import Image
import PyPDF2
import os
import datetime
import uuid
import json
import re

app = Flask(__name__)
app.secret_key = "supersecretkey"

# === KONFIGURASI FOLDER ===
HISTORY_FOLDER = "history"
UPLOAD_FOLDER = "uploads"
USER_FILE = "users.json"
HISTORY_LOG = os.path.join(HISTORY_FOLDER, "history_log.txt")

for folder in [HISTORY_FOLDER, UPLOAD_FOLDER]:
    os.makedirs(folder, exist_ok=True)

if not os.path.exists(USER_FILE):
    with open(USER_FILE, "w", encoding="utf-8") as f:
        json.dump([], f, indent=4)

if not os.path.exists(HISTORY_LOG):
    open(HISTORY_LOG, "w", encoding="utf-8").close()


# ======================================================
# 🔥 ABSTRACTIVE SUMMARIZER
# ======================================================
def abstractive_summarizer(text):
    cleaned = re.sub(r"\s+", " ", text).strip()
    sentences = re.split(r"[.!?\n]+", cleaned)
    sentences = [s.strip() for s in sentences if len(s.strip()) > 5]

    if not sentences:
        return "Tidak ada teks yang dapat diringkas."

    keywords = [
        "tugas", "deadline", "penting", "pengumuman",
        "absen", "izin", "materi", "praktikum",
        "dikumpulkan", "harus", "diminta", "wajib",
        "informasi", "kelompok", "laporan", "pertemuan"
    ]

    key_sentences = []
    for s in sentences:
        score = sum(1 for kw in keywords if kw in s.lower())
        key_sentences.append((score, s))

    key_sentences.sort(reverse=True, key=lambda x: x[0])
    core = [s for _, s in key_sentences[:5]]
    base = " ".join(core)

    summary = (
        "Berikut inti informasi yang disampaikan:\n\n"
        "• " + base.replace(". ", "\n• ").replace("?", "").replace("!", "")
    )

    lines = summary.split("\n")
    cleaned_lines = []
    for ln in lines:
        ln = ln.strip("-• ").strip()
        if len(ln) > 3:
            cleaned_lines.append(f"• {ln}")

    return "\n".join(cleaned_lines)


# ======================================================
# 🔥 TRANSLATE
# ======================================================
def translate_to_indonesian(text):
    try:
        language = detect(text)
        if language != "id":
            return GoogleTranslator(source="auto", target="id").translate(text)
        return text
    except Exception:
        return text


# ======================================================
# 🔥 EXTRACT FILE
# ======================================================
def extract_text_from_file(file_path, ext):
    text = ""
    try:
        if ext == ".txt":
            with open(file_path, "r", encoding="utf-8") as f:
                text = f.read()

        elif ext == ".pdf":
            reader = PyPDF2.PdfReader(file_path)
            for page in reader.pages:
                text += page.extract_text() or ""

        elif ext == ".docx":
            doc = Document(file_path)
            text = "\n".join([p.text for p in doc.paragraphs])

        elif ext in [".png", ".jpg", ".jpeg"]:
            img = Image.open(file_path)
            text = pytesseract.image_to_string(img, lang="eng")

    except Exception as e:
        print(f"⚠️ Error file: {e}")

    return text.strip()


# ======================================================
# USER MANAGEMENT
# ======================================================
def load_users():
    with open(USER_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_users(users):
    with open(USER_FILE, "w", encoding="utf-8") as f:
        json.dump(users, f, indent=4)


# ======================================================
# ROUTES
# ======================================================

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "").strip()

        if not name or not email or not password:
            flash("Lengkapi semua field.", "warning")
            return redirect(url_for("register"))

        users = load_users()

        if any(u["email"] == email for u in users):
            flash("Email sudah terdaftar.", "warning")
            return redirect(url_for("login"))

        users.append({
            "name": name,
            "email": email,
            "password": password,
            "joined": datetime.datetime.now().strftime("%d %B %Y %H:%M")
        })

        save_users(users)
        flash("Akun berhasil dibuat.", "success")
        return redirect(url_for("login"))

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "").strip()

        users = load_users()

        user_by_email = next((u for u in users if u["email"] == email), None)
        if not user_by_email:
            flash("Akun tidak ditemukan, silakan daftar terlebih dahulu!", "danger")
            return redirect(url_for("login"))

        user = next((u for u in users if u["email"] == email and u["password"] == password), None)

        if user:
            session["user"] = user
            flash("Login berhasil!", "success")
            return redirect(url_for("index"))

        flash("Email atau password salah.", "danger")

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.pop("user", None)
    flash("Anda telah logout.", "info")
    return redirect(url_for("login"))


# ======================================================
# ⭐ HALAMAN PROFIL
# ======================================================
@app.route("/profile")
def profile():
    if "user" not in session:
        return redirect(url_for("login"))
    return render_template("profile.html", user=session["user"])


@app.route("/profil")
def profil():
    if "user" not in session:
        return redirect(url_for("login"))
    return render_template("profile.html", user=session["user"])


# ======================================================
# ⭐ EDIT PROFIL
# ======================================================
@app.route("/edit_profile", methods=["GET", "POST"])
def edit_profile():
    if "user" not in session:
        return redirect(url_for("login"))

    users = load_users()
    current_email = session["user"]["email"]

    if request.method == "GET":
        return render_template("edit_profile.html", user=session["user"])

    new_name = request.form.get("name", "").strip()
    new_email = request.form.get("email", "").strip().lower()
    new_password = request.form.get("password", "").strip()

    if not new_name or not new_email:
        flash("Nama dan email tidak boleh kosong.", "warning")
        return redirect(url_for("edit_profile"))

    for u in users:
        if u["email"] == new_email and u["email"] != current_email:
            flash("Email sudah digunakan pengguna lain.", "danger")
            return redirect(url_for("edit_profile"))

    for u in users:
        if u["email"] == current_email:
            u["name"] = new_name
            u["email"] = new_email
            if new_password:
                u["password"] = new_password

    save_users(users)
    session["user"] = next(u for u in users if u["email"] == new_email)

    flash("Profil berhasil diperbarui.", "success")
    return redirect(url_for("profile"))


# ======================================================
# ⭐ INDEX
# ======================================================
@app.route("/")
def index():
    if "user" not in session:
        return redirect(url_for("login"))
    return render_template("index.html", user=session["user"])


# ======================================================
# ⭐⭐ 🔥 ABOUT AI PAGE (BARU DITAMBAHKAN)
# ======================================================
@app.route("/about")
def about():
    return render_template("about.html", user=session.get("user"))


# ======================================================
# ⭐ SUMMARIZE
# ======================================================
@app.route("/summarize", methods=["POST"])
def summarize():
    if "user" not in session:
        return redirect(url_for("login"))

    file = request.files.get("file")
    text_input = request.form.get("text_input", "").strip()
    text = ""

    if file and file.filename:
        ext = os.path.splitext(file.filename)[1].lower()
        new_filename = f"upload_{uuid.uuid4().hex[:8]}{ext}"
        file_path = os.path.join(UPLOAD_FOLDER, new_filename)
        file.save(file_path)
        text = extract_text_from_file(file_path, ext)

    elif text_input:
        text = text_input

    if not text:
        return render_template("result.html",
                               summary="⚠️ Tidak ada teks yang bisa diringkas.",
                               text=None,
                               user=session["user"])

    summary = abstractive_summarizer(text)
    translated = translate_to_indonesian(summary)

    now = datetime.datetime.now()
    tanggal = now.strftime("%d-%m-%Y")
    waktu = now.strftime("%H%M")

    summary_filename = f"📝 Ringkasan-{tanggal}-{waktu}.txt"
    summary_path = os.path.join(HISTORY_FOLDER, summary_filename)

    with open(summary_path, "w", encoding="utf-8") as f:
        f.write(translated)

    timestamp = datetime.datetime.now().strftime("%d-%m-%Y %H:%M:%S")
    with open(HISTORY_LOG, "a", encoding="utf-8") as f:
        f.write(f"{summary_filename}|{timestamp}\n")

    return render_template(
        "result.html",
        text=text,
        summary=translated,
        filename=summary_filename,
        timestamp=timestamp,
        user=session["user"]
    )


# ======================================================
# ⭐ DOWNLOAD
# ======================================================
@app.route("/download/<filename>")
def download(filename):
    path = os.path.join(HISTORY_FOLDER, filename)
    if not os.path.exists(path):
        return "⚠️ File tidak ditemukan.", 404

    return send_file(path, as_attachment=True)


# ======================================================
# ⭐ HISTORY
# ======================================================
@app.route("/history")
def history():
    if "user" not in session:
        return redirect(url_for("login"))

    histories = []
    if not os.path.exists(HISTORY_LOG):
        open(HISTORY_LOG, "w", encoding="utf-8").close()

    with open(HISTORY_LOG, "r", encoding="utf-8") as f:
        lines = [l.strip() for l in f.readlines() if l.strip()]

    for line in reversed(lines):
        parts = line.split("|")
        if len(parts) == 2:
            histories.append({"filename": parts[0], "timestamp": parts[1]})

    last_summary = None
    if histories:
        last_file = histories[0]["filename"]
        path = os.path.join(HISTORY_FOLDER, last_file)
        if os.path.exists(path):
            last_summary = open(path, "r", encoding="utf-8").read()

    return render_template("history.html",
                           histories=histories,
                           last_summary=last_summary,
                           user=session["user"])


# ======================================================
# ⭐ DELETE FILE
# ======================================================
@app.route("/delete/<filename>", methods=["POST"])
def delete_file(filename):
    path = os.path.join(HISTORY_FOLDER, filename)
    if os.path.exists(path):
        os.remove(path)

    with open(HISTORY_LOG, "r", encoding="utf-8") as f:
        lines = f.readlines()

    with open(HISTORY_LOG, "w", encoding="utf-8") as f:
        for line in lines:
            if filename not in line:
                f.write(line)

    flash("Riwayat berhasil dihapus.", "info")
    return redirect(url_for("history"))


@app.route("/delete_all_history", methods=["POST"])
def delete_all_history():
    for file in os.listdir(HISTORY_FOLDER):
        path = os.path.join(HISTORY_FOLDER, file)
        if os.path.isfile(path):
            os.remove(path)

    open(HISTORY_LOG, "w", encoding="utf-8").close()
    flash("Semua riwayat berhasil dihapus.", "info")
    return redirect(url_for("history"))


# ======================================================
# 🎤 API SPEECH TO TEXT
# ======================================================
@app.route("/speech_to_text", methods=["POST"])
def speech_to_text():

    if "audio" not in request.files:
        return jsonify({"error": "Tidak ada file audio."}), 400

    audio_file = request.files["audio"]

    with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as temp:
        audio_file.save(temp.name)
        temp_path = temp.name

    recognizer = sr.Recognizer()

    try:
        with sr.AudioFile(temp_path) as source:
            audio_data = recognizer.record(source)

        text = recognizer.recognize_google(audio_data, language="id-ID")

        return jsonify({"text": text})

    except sr.UnknownValueError:
        return jsonify({"error": "Suara tidak dikenali."}), 400

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ======================================================
# ⭐⭐ 🔥 ABOUT AI POPUP (ROUTE BARU) — **DITAMBAHKAN**
# ======================================================
@app.route("/about_info")
def about_info():
    return jsonify({
        "title": "Tentang AI Summarizer",
        "desc": "AI ini menggunakan teknik Natural Language Processing (NLP) untuk meringkas teks panjang menjadi poin-poin penting.",
        "work": [
            "Menganalisis isi teks",
            "Mendeteksi kalimat inti",
            "Menghasilkan ringkasan akurat dan mudah dipahami"
        ],
        "benefit": [
            "Menghemat waktu membaca",
            "Memudahkan memahami materi kuliah",
            "Cocok untuk merangkum PDF, tugas, catatan, atau gambar"
        ]
    })


# ======================================================
# RUN
# ======================================================
if __name__ == "__main__":
    app.run(debug=True)
