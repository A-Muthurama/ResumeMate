import os
import tempfile
import json
import re
from flask import Flask, render_template, request, redirect, url_for, flash, send_file
import google.generativeai as genai
from docx import Document
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet

from utils.parser import extract_text
from utils.scorer import score_against_jobs, ats_score_local
from dotenv import load_dotenv
load_dotenv()  # loads .env file

# ---------------- CONFIG ----------------
app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET", "dev-secret")

# Gemini API key
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
else:
    genai = None  # indicate no AI key available

GEMINI_MODEL_NAME = "gemini-2.5-flash"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
JOBS_PATH = os.path.join(BASE_DIR, "jobs.json")
with open(JOBS_PATH, "r", encoding="utf-8") as f:
    JOBS_DB = json.load(f)

# Store generated files
app.config["LATEST_RESUME_PDF"] = None
app.config["LATEST_RESUME_DOCX"] = None

# ---------------- Helper: Gemini ----------------
def ask_gemini_json(prompt: str):
    """Send prompt to Gemini expecting JSON response"""
    if not genai:
        return None
    try:
        model = genai.GenerativeModel(GEMINI_MODEL_NAME)
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        print("Gemini error:", e)
        return None

def ask_gemini_text(prompt: str):
    """Send prompt to Gemini expecting plain text"""
    if not genai:
        return None
    try:
        model = genai.GenerativeModel(GEMINI_MODEL_NAME)
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        print("Gemini error:", e)
        return None


# Predefined skill set (you can expand this list)
KNOWN_SKILLS = {
    "python", "java", "c++", "javascript", "html", "css", "sql",
    "machine learning", "deep learning", "nlp", "data analysis",
    "excel", "power bi", "tableau", "cloud", "aws", "azure",
    "flask", "django", "react", "node.js", "git", "docker", "kubernetes"
}

def extract_skills(text):
    """Extract only relevant skills from text."""
    text = text.lower()
    found = set()
    for skill in KNOWN_SKILLS:
        if re.search(rf"\b{re.escape(skill)}\b", text):
            found.add(skill)
    return found

def ats_score_local(resume_text, job_desc):
    resume_skills = extract_skills(resume_text)
    job_skills = extract_skills(job_desc)

    matched = resume_skills.intersection(job_skills)
    missing = job_skills - resume_skills

    score = int((len(matched) / len(job_skills) * 100)) if job_skills else 0

    return {
        "ats_score": score,
        "matched_skills": list(matched),
        "missing_skills": list(missing),
        "suggestions": (
            "Add missing skills to improve your ATS score. "
            f"Missing: {', '.join(missing) if missing else 'None'}"
        )
    }

# ---------------- Routes ----------------
@app.route("/")
def home():
    return render_template("index.html")

# ---------- Resume Creation ----------
@app.route("/resume", methods=["GET", "POST"])
def resume_creation():
    if request.method == "POST":
        data = {
            "name": request.form.get("name"),
            "email": request.form.get("email"),
            "phone": request.form.get("phone"),
            "linkedin": request.form.get("linkedin"),
            "summary": request.form.get("summary"),
            "skills": request.form.get("skills", "").split(","),
            "education": request.form.get("education"),
            "projects": request.form.get("projects"),
            "achievements": request.form.get("achievements"),
            "certifications": request.form.get("certifications"),
            "role_category": request.form.get("role_category"),
        }
        template_choice = request.form.get("template")

        # Render chosen template
        return render_template(f"{template_choice}.html", **data)

    return render_template("resume.html")


# ✅ Download Resume as PDF
@app.route("/download_pdf", methods=["POST"])
def download_pdf():
    template_choice = request.form.get("template")
    html = render_template(f"{template_choice}.html", **request.form.to_dict())
    pdf_path = "resume.pdf"

    pdfkit.from_string(html, pdf_path)
    return send_file(pdf_path, as_attachment=True)


# ✅ Download Resume as DOCX
@app.route("/download_docx", methods=["POST"])
def download_docx():
    template_choice = request.form.get("template")
    data = request.form.to_dict()

    doc = Document()
    doc.add_heading(data["name"], 0)
    doc.add_paragraph(f"Email: {data['email']} | Phone: {data['phone']} | LinkedIn: {data['linkedin']}")
    doc.add_heading("Summary", level=1)
    doc.add_paragraph(data["summary"])
    doc.add_heading("Skills", level=1)
    for s in data["skills"].split(","):
        doc.add_paragraph(s.strip(), style="List Bullet")
    doc.add_heading("Education", level=1)
    doc.add_paragraph(data["education"])
    doc.add_heading("Projects", level=1)
    doc.add_paragraph(data["projects"])
    doc.add_heading("Achievements", level=1)
    doc.add_paragraph(data["achievements"])
    doc.add_heading("Certifications", level=1)
    doc.add_paragraph(data["certifications"])

    doc_path = "resume.docx"
    doc.save(doc_path)
    return send_file(doc_path, as_attachment=True)
# ✅ Alternative PDF generation using ReportLab

# ---------- Job Matching ----------
@app.route("/match", methods=["GET", "POST"])
def job_matching():
    matches = None
    if request.method == "POST":
        uploaded = request.files.get("resume_file")
        resume_text = request.form.get("resume_text", "").strip()
        if uploaded and uploaded.filename != "":
            try:
                resume_text = extract_text(uploaded)
            except Exception as e:
                flash(f"Failed to parse resume: {e}", "danger")

        if not resume_text:
            flash("Please upload or paste a resume.", "warning")
            return render_template("match.html")

        if genai:
            job_list_str = "\n".join([f"- {j['title']}: {', '.join(j.get('keywords', []))}" for j in JOBS_DB])
            prompt = (
                "You are a job-matching assistant. Compare the candidate resume with job roles.\n"
                "Return JSON array: {title, score (0-100), matched_skills:[], missing_skills:[]}\n\n"
                f"Jobs:\n{job_list_str}\n\nResume:\n{resume_text}\n\nReturn JSON only."
            )
            gem_text = ask_gemini_json(prompt)
            import re, json as _json
            try:
                m = re.search(r"(\[.*\])", gem_text, re.S)
                matches = _json.loads(m.group(1)) if m else score_against_jobs(resume_text, JOBS_DB)
            except Exception:
                matches = score_against_jobs(resume_text, JOBS_DB)
        else:
            matches = score_against_jobs(resume_text, JOBS_DB)

        matches = sorted(matches, key=lambda x: x.get("score", 0), reverse=True)

    return render_template("match.html", matches=matches)

# ---------- ATS Scoring ----------
@app.route("/score", methods=["GET", "POST"])
def ats_scoring():
    result = None
    if request.method == "POST":
        uploaded = request.files.get("resume_file")
        resume_text = request.form.get("resume_text", "").strip()
        job_desc = request.form.get("job_desc", "").strip()

        # Step 1: Extract text from uploaded resume
        if uploaded and uploaded.filename != "":
            try:
                resume_text = extract_text(uploaded)
            except Exception as e:
                flash(f"Failed to parse resume: {e}", "danger")

        if not resume_text or not job_desc:
            flash("Upload/paste resume and provide job description.", "warning")
            return render_template("score.html")

        # Step 2: Call Gemini for optimized skill-based ATS scoring
        if genai:
            prompt = f"""
            You are an advanced ATS scoring assistant. 

            Task:
            - Extract only the **relevant hard and soft skills** (e.g., Python, SQL, Machine Learning, Communication).
            - Compare skills from resume and job description.
            - Ignore common filler words like 'the', 'is', 'and', 'with'.
            - Return JSON only in this format:

            {{
              "ats_score": int, 
              "matched_skills": ["..."], 
              "missing_skills": ["..."], 
              "suggestions": "Write improvements for missing skills or keywords."
            }}

            Resume Text:
            {resume_text}

            Job Description:
            {job_desc}
            """

            gem_text = ask_gemini_json(prompt)
            import re, json as _json
            try:
                m = re.search(r"(\{.*\})", gem_text, re.S)
                result = _json.loads(m.group(1)) if m else ats_score_local(resume_text, job_desc)
            except Exception:
                result = ats_score_local(resume_text, job_desc)

        else:
            result = ats_score_local(resume_text, job_desc)

    return render_template("score.html", result=result)


# ---------------- MAIN ----------------
if __name__ == "__main__":
    app.run(debug=True)
