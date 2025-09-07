import os
import requests
import re

HF_API_TOKEN = os.environ.get("HF_API_TOKEN")  # put your Hugging Face token here

# Which model endpoint to use at inference API for keyphrase/skills extraction:
# You can choose a model like "mrm8488/t5-base-finetuned-keyphrase-extraction" on HF.
# We will call the HF inference HTTP API generically using text-generation or zero-shot if needed.
HF_MODEL = os.environ.get("HF_MODEL", "mrm8488/t5-base-finetuned-keyphrase-extraction")

def call_hf_keyphrase_model(text: str, max_keywords: int = 20):
    """
    Calls Hugging Face Inference API for keyphrase extraction.
    Returns a list of candidate keywords or skills.
    """
    if not HF_API_TOKEN:
        return []

    # Many keyphrase models expect a simple POST with 'inputs' payload and return a string.
    headers = {"Authorization": f"Bearer {HF_API_TOKEN}"}
    api_url = f"https://api-inference.huggingface.co/models/{HF_MODEL}"
    payload = {"inputs": text, "parameters": {"max_new_tokens": 128, "return_full_text": False}}

    try:
        resp = requests.post(api_url, headers=headers, json=payload, timeout=30)
        resp.raise_for_status()
        data = resp.json()

        # different models return different shapes; try robust parsing:
        if isinstance(data, dict) and "error" in data:
            return []
        if isinstance(data, list):
            # some models return [{"generated_text": "..., keywords"}]
            parts = []
            for item in data:
                if isinstance(item, dict) and "generated_text" in item:
                    parts.append(item["generated_text"])
                elif isinstance(item, str):
                    parts.append(item)
            joined = " ".join(parts)
        elif isinstance(data, str):
            joined = data
        else:
            # fallback stringify
            joined = str(data)

        # split by commas/newlines and clean
        candidates = re.split(r"[,\n;]+", joined)
        cleaned = [c.strip().lower() for c in candidates if len(c.strip()) >= 2]
        # dedupe and limit
        seen = set()
        out = []
        for kw in cleaned:
            if kw not in seen:
                seen.add(kw)
                out.append(kw)
            if len(out) >= max_keywords:
                break
        return out
    except Exception:
        return []


# fallback simple extractor: words 3+ chars, common skill tokens
COMMON_SKILLS = [
    "python","java","c++","c","javascript","react","angular","nodejs","sql","mysql","postgresql",
    "mongodb","tensorflow","pytorch","machine learning","deep learning","nlp","computer vision",
    "pandas","numpy","scikit-learn","aws","azure","docker","kubernetes","git","html","css","bootstrap",
    "rest","api","flask","django","linux"
]

def simple_skill_extractor(text: str, max_keywords: int = 30):
    """
    Basic skill extractor: find occurrences of common skills and return a list.
    Also extracts capitalized tokens and tech-like tokens.
    """
    text_lower = text.lower()
    found = []
    # check common list
    for skill in COMMON_SKILLS:
        if skill in text_lower and skill not in found:
            found.append(skill)
            if len(found) >= max_keywords:
                return found

    # extract tokens that look like tech words (alphanumeric, len>=3)
    tokens = re.findall(r"\b[a-zA-Z0-9\+\#\.\-]{3,}\b", text)
    for t in tokens:
        tl = t.lower()
        if tl not in found and len(found) < max_keywords:
            # ignore too generic words
            if tl in ("the","and","for","with","this","that","from"):
                continue
            found.append(tl)
    return found[:max_keywords]


def extract_skills_from_text(text: str, max_keywords: int = 30):
    """
    Main function to extract skills / keyphrases from a body of text.
    Uses Hugging Face model if HF_API_TOKEN present; otherwise fallback.
    """
    text = (text or "").strip()
    if not text:
        return []

    # prefer HF model if available
    if HF_API_TOKEN:
        keywords = call_hf_keyphrase_model(text, max_keywords=max_keywords)
        if keywords:
            return keywords

    # fallback
    return simple_skill_extractor(text, max_keywords=max_keywords)
