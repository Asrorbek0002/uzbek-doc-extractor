# -*- coding: utf-8 -*-
"""Configuration.

The constraint (from the assignment): documents must not be sent to external
cloud services. So everything is local: pdfplumber (reading), Tesseract (OCR),
rules (extraction). There is no API call anywhere.
"""
import os
from pathlib import Path

ILDIZ = Path(__file__).resolve().parents[2]     # repository root
UMUMIY = ILDIZ.parent                           # parent dir — an optional shared location

# `.env` is looked up inside the repository first and in the parent directory
# as a fallback: in a standalone clone everything lives inside it, while if the
# two assignments sit side by side, one `.env` in the parent serves both.
ENV_FAYL = next(
    (p for p in (ILDIZ / ".env", UMUMIY / ".env") if p.is_file()),
    ILDIZ / ".env",
)

try:
    from dotenv import load_dotenv

    load_dotenv(ENV_FAYL)
except ImportError:
    pass

# ─────────────────────────────── data ────────────────────────────────────
DATA_DIR = ILDIZ / "data"
KIRISH = DATA_DIR / "input"
MATNLI = KIRISH / "matnli"          # has a text layer — no OCR needed
SKANER = KIRISH / "skaner"          # no text layer — OCR required
YUKLAMA = KIRISH / "yuklama"        # files uploaded through the web interface

# Two versions of the same 6 documents. `matnli` is the GROUND TRUTH for
# measuring OCR quality: it lets CER/WER be stated as an exact number.
JUFTLIKLAR = [
    ("NAMUNA_1_abzats", "NAMUNA_1_abzats_skaner"),
    ("NAMUNA_2_jadval", "NAMUNA_2_jadval_skaner"),
    ("NAMUNA_3_ilova", "NAMUNA_3_ilova_skaner"),
    ("xat_1_abzatsdagi_topshiriqlar", "xat_1_abzatsdagi_topshiriqlar_skaner"),
    ("xat_2_jadvaldagi_topshiriqlar", "xat_2_jadvaldagi_topshiriqlar_skaner"),
    ("xat_3_ilovadagi_topshiriqlar", "xat_3_ilovadagi_topshiriqlar_skaner"),
]

NATIJA_DIR = DATA_DIR / "results"

# ─────────────────────────────── OCR ─────────────────────────────────────
# Tesseract languages. `uzb` is Uzbek (Latin); `rus` helps with some terms.
# Without them it falls back to `eng` (the Latin alphabet is still read, at
# lower quality).
OCR_TIL = os.getenv("OCR_TIL", "uzb")
OCR_DPI = int(os.getenv("OCR_DPI", "300"))      # 300 dpi — the standard for OCR

# If a PDF holds fewer characters than this, it is treated as a scan and OCR
# kicks in. Measured: the digital documents have 1,366-2,266 characters, the
# scans have 0. 100 is a safe threshold.
MATN_CHEGARA = 100

# ─────────────────────────────── web ─────────────────────────────────────
MAKS_FAYL_MB = 20
