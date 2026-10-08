# -*- coding: utf-8 -*-
"""API routes.

    GET  /api/salomatlik        health (pdfplumber, Tesseract, languages)
    GET  /api/namunalar         the sample documents shipped with the project
    POST /api/tahlil            upload a PDF -> analyze
    POST /api/namuna/{nom}      analyze a sample (without uploading anything)

THE CONSTRAINT (from the assignment): documents are never sent to external
cloud services. There is no outbound network call here — pdfplumber and
Tesseract are both local.
"""
from __future__ import annotations

import re
import time
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile
from starlette.concurrency import run_in_threadpool

from app.core import config as c
from app.models.schemas import Namuna, Natija, Salomatlik
from app.services.document_parser import tahlil as hujjat_tahlil
from app.services.ocr import mavjudmi as ocr_mavjudmi, tillar as ocr_tillar

yollar = APIRouter(prefix="/api", tags=["tahlil"])

XAVFSIZ = re.compile(r"[^A-Za-z0-9._-]+")


def _xavfsiz_nom(nom: str) -> str:
    """Makes a filename safe.

    ONLY the basename is taken and every disallowed character is replaced with
    a dash — which stops path traversal such as `../../etc/passwd`.
    """
    toza = XAVFSIZ.sub("-", Path(nom).name).strip("-.") or "hujjat"
    return toza[:120]


def _namunalar() -> dict[str, Path]:
    """Sample name -> path. Collected from the two directories."""
    jadval = {}
    for papka in (c.MATNLI, c.SKANER):
        if papka.is_dir():
            for yol in sorted(papka.glob("*.pdf")):
                jadval[yol.name] = yol
    return jadval


# ─────────────────────────────── health ──────────────────────────────────
@yollar.get("/salomatlik", response_model=Salomatlik,
            summary="System health")
def salomatlik() -> Salomatlik:
    """Checks every dependency — a fault is visible immediately."""
    try:
        import pdfplumber  # noqa: F401
        pdf_ok = True
    except ImportError:
        pdf_ok = False

    ocr_ok, izoh = ocr_mavjudmi()
    return Salomatlik(
        holat="tayyor" if pdf_ok else "nosoz",
        pdf_oqish=pdf_ok,
        ocr=ocr_ok,
        ocr_izoh=izoh,
        ocr_tillari=ocr_tillar() if ocr_ok else [],
        namunalar=len(_namunalar()),
    )


# ─────────────────────────────── samples ─────────────────────────────────
@yollar.get("/namunalar", response_model=list[Namuna],
            summary="The list of sample documents")
def namunalar() -> list[Namuna]:
    """The 12 documents shipped with the project (6 digital + 6 scanned)."""
    return [
        Namuna(nom=nom,
               tur="skaner" if yol.parent == c.SKANER else "matnli",
               olcham_kb=round(yol.stat().st_size / 1024))
        for nom, yol in _namunalar().items()
    ]


@yollar.post("/namuna/{nom}", response_model=Natija,
             summary="Analyze a sample")
async def namuna_tahlil(nom: str) -> Natija:
    """Analyzes a sample shipped with the project, without an upload — for demos."""
    yol = _namunalar().get(_xavfsiz_nom(nom))
    if yol is None:
        raise HTTPException(404, f"«{nom}» nomli namuna topilmadi")
    return await _tahlil_qil(yol)


# ─────────────────────────────── upload ──────────────────────────────────
@yollar.post("/tahlil", response_model=Natija,
             summary="Upload a PDF and analyze it")
async def tahlil_yukla(fayl: UploadFile = File(..., description="a PDF document")) -> Natija:
    """Accepts a PDF, stores it locally and analyzes it."""
    nom = _xavfsiz_nom(fayl.filename or "hujjat.pdf")
    if not nom.lower().endswith(".pdf"):
        raise HTTPException(400, "Faqat PDF fayl qabul qilinadi")

    xom = await fayl.read()
    if not xom:
        raise HTTPException(400, "Fayl bo'sh")
    if len(xom) > c.MAKS_FAYL_MB * 1024 * 1024:
        raise HTTPException(
            413, f"Fayl juda katta — chegara {c.MAKS_FAYL_MB} MB, "
                 f"yuklangani {len(xom) / 1024 / 1024:.1f} MB")
    if not xom.startswith(b"%PDF"):
        raise HTTPException(400, "Fayl PDF emas (sarlavhasi «%PDF» bilan boshlanmaydi)")

    c.YUKLAMA.mkdir(parents=True, exist_ok=True)
    yol = c.YUKLAMA / nom
    yol.write_bytes(xom)
    return await _tahlil_qil(yol)


async def _tahlil_qil(yol: Path) -> Natija:
    """Runs the analysis ON A SEPARATE THREAD.

    WHY a threadpool: for a scanned document OCR takes 18-35 seconds (a 300 dpi
    render plus Tesseract). Called directly, that would freeze the whole server
    for all of it — FastAPI's event loop runs on one thread.
    """
    t0 = time.perf_counter()
    try:
        natija = await run_in_threadpool(hujjat_tahlil, yol)
    except Exception as xato:                       # noqa: BLE001
        raise HTTPException(422, f"Hujjatni tahlil qilib bo'lmadi: {xato}") from xato
    javob = Natija.model_validate(natija, from_attributes=True)
    javob.vaqt_ms = round((time.perf_counter() - t0) * 1000)
    return javob
