# utils/local_scorer.py
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
import re

def score_against_jobs(resume_text: str, jobs_db: list, top_n: int = 6):
    """
    Simple local job matching:
      - For each job, compute TF-IDF similarity between resume_text and job keywords string.
      - Also compute matched and missing keywords by presence.
    Returns list of dicts: {title, score, matched, missing, job_keywords}
    """
    resume_lower = (resume_text or "").lower()
    results = []
    # prepare job documents
    job_docs = [" ".join(job.get("keywords", [])) for job in jobs_db]
    try:
        vectorizer = TfidfVectorizer().fit([resume_text] + job_docs)
        resume_vec = vectorizer.transform([resume_text])
    except Exception:
        vectorizer = None
        resume_vec = None

    for job in jobs_db:
        keywords = job.get("keywords", [])
        job_text = " ".join(keywords)
        score = 0.0
        if vectorizer:
            job_vec = vectorizer.transform([job_text])
            score = cosine_similarity(resume_vec, job_vec)[0][0] * 100
        # presence-based matched/missing
        matched = [k for k in keywords if k.lower() in resume_lower]
        missing = [k for k in keywords if k.lower() not in resume_lower]
        results.append({
            "title": job.get("title"),
            "score": round(score, 2),
            "matched": matched,
            "missing": missing,
            "job_keywords": keywords
        })
    # sort by score
    results = sorted(results, key=lambda x: x["score"], reverse=True)
    return results[:top_n]

def extract_keywords_from_text(text: str):
    # simple token extractor for ATS
    tokens = re.findall(r"\b[a-zA-Z\+\#\.\-]{2,}\b", text.lower())
    seen = set()
    out = []
    for t in tokens:
        if t not in seen and len(t) > 1:
            seen.add(t)
            out.append(t)
        if len(out) >= 200:
            break
    return out

def ats_score_local(resume_text: str, job_desc: str):
    """
    Basic ATS-like scoring: uses keyword overlap + TF-IDF similarity
    Returns dict: {ats_score, matched_keywords, missing_keywords, suggestions}
    """
    resume_lower = (resume_text or "").lower()
    # extract candidate keywords from job_desc (split by common separators)
    # and also pick known tokens
    jd_keywords = re.findall(r"[a-zA-Z\+\#\.\-]{2,}", job_desc.lower())
    # make unique preserving order
    jd_unique = []
    seen = set()
    for k in jd_keywords:
        if k not in seen:
            seen.add(k)
            jd_unique.append(k)
    # presence
    matched = [k for k in jd_unique if k in resume_lower]
    missing = [k for k in jd_unique if k not in resume_lower]
    # tfidf similarity
    try:
        vectorizer = TfidfVectorizer().fit([resume_text, job_desc])
        vecs = vectorizer.transform([resume_text, job_desc])
        sim = cosine_similarity(vecs[0], vecs[1])[0][0] * 100
    except Exception:
        sim = 0.0
    # combine
    presence_frac = len(matched) / max(1, len(jd_unique))
    final_score = 0.6 * sim + 0.4 * presence_frac * 100
    final_score = round(max(0, min(100, final_score)), 2)
    suggestions = []
    if len(missing) > 0:
        suggestions.append(f"Consider adding keywords: {', '.join(missing[:8])}")
    if presence_frac < 0.5:
        suggestions.append("Try listing key skills and tools prominently in the summary and skills section.")
    return {
        "ats_score": final_score,
        "matched_keywords": matched[:50],
        "missing_keywords": missing[:50],
        "suggestions": " ".join(suggestions) if suggestions else "Good match!"
    }
