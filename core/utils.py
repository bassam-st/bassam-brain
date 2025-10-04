# ===========================
# core/utils.py
# ===========================
import re

def normalize_text(txt: str) -> str:
    txt = txt.strip()
    txt = re.sub(r"\s+", " ", txt)
    return txt
