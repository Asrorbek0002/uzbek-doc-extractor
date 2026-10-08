# -*- coding: utf-8 -*-
"""Turning a scanned PDF into text (OCR).

WHY THERE ARE NO EXTRA PYTHON PACKAGES

    The usual choice is `pytesseract` plus `pdf2image`, but both of them are
    thin wrappers that simply invoke a system command. We invoke it directly —
    two dependencies fewer, and the pipeline is visible in the code:

        PDF ──pdftoppm -r 300──▶ PNG ──tesseract -l uzb──▶ text

FIXING OCR ERRORS

    One systematic error found during testing: the "№" sign is read as "Ne".
    That breaks extraction of the document number, so the OCR output is
    normalized. The remaining differences (apostrophe variants, "+" → "4" in a
    phone number) have no effect on the analysis.

THE CACHE

    One page takes ~17 seconds (13.5 s to render + 3.4 s of OCR). The result is
    saved as JSON, so a re-run is instant.

Running it:
    python -m app.services.ocr                  # reads the 6 scans
    python -m app.services.ocr --qayta          # ignores the cache
    python -m app.services.ocr <file.pdf>
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.core import console as ch
from app.core import config as c

KESH_DIR = c.NATIJA_DIR / "ocr_kesh"

# Systematic errors in Tesseract's output. The order matters: longer patterns
# first.
TUZATISH = [
    # "№ 03-12/1456" -> "Ne 03-12/1456" / "No 03-12" / "N2 03-12"
    (re.compile(r"\bN[eo2][\s.]*(?=\d)"), "№ "),
    (re.compile(r"\bNo\.?\s*(?=\d)"), "№ "),
]


def mavjudmi() -> tuple[bool, str]:
    """Whether tesseract and pdftoppm are installed."""
    yoq = [x for x in ("tesseract", "pdftoppm") if shutil.which(x) is None]
    if yoq:
        return False, (f"not found: {', '.join(yoq)}\n"
                       "  sudo apt install -y tesseract-ocr tesseract-ocr-uzb poppler-utils")
    tillar = subprocess.run(["tesseract", "--list-langs"], capture_output=True,
                            text=True).stdout
    if c.OCR_TIL not in tillar:
        return False, (f"the '{c.OCR_TIL}' language pack is not installed\n"
                       f"  sudo apt install -y tesseract-ocr-{c.OCR_TIL}")
    return True, ""


def tillar() -> list[str]:
    """The list of languages installed in Tesseract."""
    try:
        chiqish = subprocess.run(["tesseract", "--list-langs"],
                                 capture_output=True, text=True, check=True).stdout
    except (OSError, subprocess.CalledProcessError):
        return []
    # The first line is "List of available languages...", the rest are languages
    return [s.strip() for s in chiqish.splitlines()[1:] if s.strip()]


def _tuzat(matn: str) -> str:
    from app.services.table_extractor import apostrof_tuzat
    matn = apostrof_tuzat(matn)
    for naqsh, almash in TUZATISH:
        matn = naqsh.sub(almash, matn)
    return matn


def _kesh_yoli(yol: Path) -> Path:
    imzo = hashlib.md5(
        f"{yol.name}|{yol.stat().st_size}|{c.OCR_DPI}|{c.OCR_TIL}".encode()
    ).hexdigest()[:10]
    return KESH_DIR / f"{yol.stem}_{imzo}.json"


# ───────────────────────── the cache: locking and atomicity ──────────────
# Per-file locks. The lock table itself is also mutated under a lock.
_QULFLAR: dict[str, threading.Lock] = {}
_QULFLAR_QULFI = threading.Lock()


def _fayl_qulfi(kalit: str) -> threading.Lock:
    """The lock for this cache file — so only one OCR runs at a time.

    WHY IT IS NEEDED (measured): FastAPI executes a synchronous endpoint on a
    threadpool, which means requests really do run in parallel. Without the
    lock, three requests for the same scanned document all ran the full OCR —
    23 s each (19.9 s on its own). The work was done three times over.
    """
    with _QULFLAR_QULFI:
        return _QULFLAR.setdefault(kalit, threading.Lock())


def _keshni_oqi(kesh: Path) -> dict | None:
    """Reads the cache. Returns None when it is corrupt — then OCR re-runs.

    WHY the try: if the process dies mid-write (OOM, Ctrl+C), the JSON is left
    half-written. Every subsequent request that tried to read it would crash.
    """
    if not kesh.exists():
        return None
    try:
        d = json.loads(kesh.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return d if "jadvallar" in d and "betlar" in d else None


def _keshni_yoz(kesh: Path, natija: dict) -> None:
    """Writes the cache ATOMICALLY: to a temporary file, then into place.

    `os.replace` is atomic on POSIX — so another thread sees either the new or
    the old complete file, and never a half-written one.
    """
    KESH_DIR.mkdir(parents=True, exist_ok=True)
    vaqtli = kesh.with_suffix(f".{os.getpid()}.vaqtli")
    try:
        vaqtli.write_text(json.dumps(natija, ensure_ascii=False, indent=1),
                          encoding="utf-8")
        os.replace(vaqtli, kesh)
    finally:
        vaqtli.unlink(missing_ok=True)


def ocr_toliq(yol: str | Path, qayta: bool = False,
              korsat: bool = False) -> dict:
    """Runs OCR on a PDF: the text AND the tables.

    THE SAVING: rendering to an image is the expensive step (~13.5 s per page
    at 300 dpi). Rendering separately for the text and for the tables would
    take twice as long, so both are taken from a single render.

    Returns: {"betlar": [text...], "jadvallar": [{bet, sarlavhalar, qatorlar}...]}
    """
    yol = Path(yol)
    kesh = _kesh_yoli(yol)
    if not qayta:
        d = _keshni_oqi(kesh)
        if d is not None:
            return d

    # THE LOCK: with parallel requests for the same document, OCR runs ONCE.
    # After acquiring the lock the cache is checked AGAIN — while we waited,
    # another thread may have finished ("double-checked locking").
    with _fayl_qulfi(str(kesh)):
        if not qayta:
            d = _keshni_oqi(kesh)
            if d is not None:
                return d
        return _ocr_bajar(yol, kesh, korsat)


def _ocr_bajar(yol: Path, kesh: Path, korsat: bool) -> dict:
    """Actually runs the OCR (called under the lock)."""
    ok, xabar = mavjudmi()
    if not ok:
        raise SystemExit(f"OCR is unavailable: {xabar}")

    from app.services.table_extractor import jadval_tikla, sozlar_ol   # avoids a circular import

    t0 = time.perf_counter()
    betlar: list[str] = []
    jadvallar: list[dict] = []
    with tempfile.TemporaryDirectory() as vaqtli:
        subprocess.run(
            ["pdftoppm", "-r", str(c.OCR_DPI), "-png", str(yol),
             str(Path(vaqtli) / "bet")],
            check=True, capture_output=True)
        rasmlar = sorted(Path(vaqtli).glob("bet-*.png"))

        for i, rasm in enumerate(rasmlar, 1):
            if korsat:
                print(f"\r  OCR  page {i}/{len(rasmlar)}…", end="", flush=True)
            # 1) the table — by coordinates
            j = jadval_tikla(sozlar_ol(rasm), bet=i)
            if j:
                jadvallar.append({"bet": j.bet, "sarlavhalar": j.sarlavhalar,
                                  "qatorlar": j.qatorlar})
            # 2) the page text — everything OUTSIDE the table's area
            betlar.append(_bet_matni(rasm, j.maydon if j else None))

    if korsat:
        print(f"\r  OCR  {len(rasmlar)} pages · {len(jadvallar)} tables · "
              f"{ch.vaqt(time.perf_counter() - t0)}      ")

    natija = {"fayl": yol.name, "dpi": c.OCR_DPI, "til": c.OCR_TIL,
              "sekund": round(time.perf_counter() - t0, 1),
              "betlar": betlar, "jadvallar": jadvallar}
    _keshni_yoz(kesh, natija)
    return natija


def _bet_satrlari(rasm: Path) -> list[list]:
    """Takes the lines out of the `--psm 3` TSV using TESSERACT'S OWN structure.

    WHY TSV, but not my own grouping: when I grouped the words by `y` myself,
    text quality went down (measured: F1 97.4% -> 94.9%) — tesseract's page
    analysis (`block_num`/`par_num`/`line_num`) does it better than I do. The
    TSV is needed only for the COORDINATES; the line breaks come from
    tesseract. The result is identical to its plain-text output.
    """
    from app.services.table_extractor import Soz

    natija = subprocess.run(
        ["tesseract", str(rasm), "-", "-l", c.OCR_TIL, "--psm", "3", "tsv"],
        check=True, capture_output=True, text=True)
    # QUOTE_NONE: a quote character inside a cell or a word breaks the csv parser
    oqigich = csv.DictReader(io.StringIO(natija.stdout), delimiter="\t",
                             quoting=csv.QUOTE_NONE)
    satrlar: dict[tuple[int, int, int], list] = {}
    for q in oqigich:
        matn = (q.get("text") or "").strip()
        if not matn:
            continue
        try:
            kalit = (int(q["block_num"]), int(q["par_num"]), int(q["line_num"]))
            soz = Soz(matn, int(q["left"]), int(q["top"]),
                      int(q["width"]), int(q["height"]), float(q["conf"]))
        except (KeyError, TypeError, ValueError):
            continue
        satrlar.setdefault(kalit, []).append(soz)
    return [sorted(v, key=lambda s: s.x) for _, v in sorted(satrlar.items())]


def _bet_matni(rasm: Path, maydon: tuple[int, int, int, int] | None) -> str:
    """The page text — with the table's area CUT OUT.

    WHY the cut is necessary: on the digital path pdfplumber removes the table
    with `outside_bbox`, otherwise the table text gets mixed in with the prose.
    When we did not do this for OCR, the entire table text also landed in the
    page text and `abzatsdan()` manufactured FALSE action items out of it
    ("T/r Topshiriq mazmuni Mas'ul ijrochi Muddat Murojaatlar...").

    An extra benefit: the table's ruling lines are inside that same area, so
    the garbage `--psm 3` reads off those lines does not reach the page text.
    """
    satrlar = _bet_satrlari(rasm)
    if maydon:
        satrlar = [sat for sat in satrlar if not _maydonda(sat, maydon)]
    return _tuzat("\n".join(" ".join(s.matn for s in sat) for sat in satrlar))


def _maydonda(sat: list, maydon: tuple[int, int, int, int]) -> bool:
    """Is the line inside the table's area — decided by MORE THAN HALF its words."""
    x0, y0, x1, y1 = maydon
    ichida = sum(1 for s in sat
                 if x0 <= s.markaz <= x1 and y0 <= s.y + s.h // 2 <= y1)
    return ichida * 2 > len(sat)


def ocr_qil(yol: str | Path, qayta: bool = False,
            korsat: bool = False) -> list[str]:
    """Returns the text of each page of the PDF (the older interface)."""
    return ocr_toliq(yol, qayta=qayta, korsat=korsat)["betlar"]


# ─────────────────────────────── CLI ─────────────────────────────────────
def main() -> int:
    ch.sarlavha("OCR — scanned PDFs")
    ok, xabar = mavjudmi()
    ch.maydon("tesseract", "ready" if ok else xabar.split("\n")[0], ok)
    if not ok:
        print(xabar)
        return 1
    ch.maydon("language", c.OCR_TIL)
    ch.maydon("dpi", c.OCR_DPI)

    qayta = "--qayta" in sys.argv
    yollar = ([Path(a) for a in sys.argv[1:] if not a.startswith("-")]
              or sorted(c.SKANER.glob("*.pdf")))
    print()
    for yol in yollar:
        ch.bolim(yol.stem)
        betlar = ocr_qil(yol, qayta=qayta, korsat=True)
        jami = sum(len(b) for b in betlar)
        ch.maydon("pages", len(betlar))
        ch.maydon("text", f"{jami:,} characters")
        bosh = re.sub(r"\s+", " ", betlar[0])[:88]
        ch.eslatma(f"begins: {bosh}…")
    return 0


if __name__ == "__main__":
    sys.exit(main())
