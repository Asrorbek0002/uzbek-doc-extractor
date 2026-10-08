# -*- coding: utf-8 -*-
"""PDF -> text + tables.

WHY pdfplumber and NOT `pdftotext -layout`

    pdftotext turns a table into plain text and separates the columns with
    SPACES. In our documents the text inside a cell is split across several
    lines:

        1   Murojaatlarni avtomatik tasniflash      Axborot texnologiyalari
            modulini joriy etish                    boshqarmasi              2026-yil 1-may

    Deciding "which word belongs to which column" from whitespace alone is not
    reliable here. pdfplumber, by contrast, sees the table's RULING LINES and
    returns the cells correctly.

THE SCANNED PATH

    When the PDF has no text layer (`skanermi`), that same Hujjat is FILLED IN
    from OCR — the calling code cannot tell the difference:

        digital PDF  -> pdfplumber: text + tables (by ruling lines)
        scanned PDF  -> tesseract:  text + tables (by coordinates)

    That is what lets `app/services/document_parser.py` work UNCHANGED for both.

WHAT IT RETURNS

    Hujjat(
        matn      -> the text OUTSIDE the tables (prose, letterhead fields)
        jadvallar -> [Jadval(headers, rows), ...]
        betlar    -> each page separately (an annex is usually on page 2)
    )

Running it:
    python -m app.services.pdf_processor                 # reads and shows the 6 documents
    python -m app.services.pdf_processor <file.pdf>      # a single file
"""
from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pdfplumber

from app.core import config as c
from app.core import console as ch

# Boilerplate repeated on every page — it must not enter the analysis
SHOVQIN = (
    "Test uchun example",
    "AI tizimini sinash uchun tuzilgan",
)


@dataclass
class Jadval:
    bet: int
    sarlavhalar: list[str]
    qatorlar: list[list[str]]
    # On the OCR path, the table's area in the image (x0, y0, x1, y1) — needed
    # in order to CUT the table out of the page text. On the pdfplumber path
    # that is done with `outside_bbox`, so there it stays None.
    maydon: tuple[int, int, int, int] | None = None

    def __len__(self) -> int:
        return len(self.qatorlar)

    def ustun(self, *nomlar: str, aniq: bool = False) -> int | None:
        """Finds a column index by its header.

        The number of columns varies from document to document (4 or 5 — the
        annex of `xat_3` adds "Natija shakli"), so the lookup goes by HEADER
        and not by POSITION.

        `aniq=True` — the header has to match in FULL, being contained in it is
        not enough. That is necessary for short headers: among the OCR variants
        of the "№" column there is "no", which as a substring would also match
        headers like "Tashkilot NOmi".
        """
        for i, s in enumerate(self.sarlavhalar):
            past = re.sub(r"[‘’ʻʼ]", "'", (s or "").lower()).strip()
            if aniq:
                yalang = re.sub(r"[^\w/№]", "", past)
                if yalang in nomlar:
                    return i
            elif any(n in past for n in nomlar):
                return i
        return None


@dataclass
class Hujjat:
    yol: Path
    betlar: list[str] = field(default_factory=list)
    jadvallar: list[Jadval] = field(default_factory=list)
    matn: str = ""
    skanermi: bool = False

    @property
    def nom(self) -> str:
        return self.yol.stem


def _tozala(s: str | None) -> str:
    """Collapses a cell's text onto one line (pdfplumber inserts \n)."""
    if not s:
        return ""
    return re.sub(r"\s+", " ", s.replace("\n", " ")).strip()


def _shovqinmi(satr: str) -> bool:
    return any(x in satr for x in SHOVQIN)


def oqi(yol: str | Path, ocr: bool = True, korsat: bool = False) -> Hujjat:
    """Reads the PDF. With no text layer it falls back to OCR (`ocr=False` disables that)."""
    yol = Path(yol)
    h = Hujjat(yol=yol)

    with pdfplumber.open(yol) as pdf:
        for n, bet in enumerate(pdf.pages, 1):
            # ── tables ──
            for xom in bet.extract_tables():
                qatorlar = [[_tozala(k) for k in q] for q in xom if any(q)]
                if len(qatorlar) < 2:          # a header plus at least 1 row
                    continue
                h.jadvallar.append(
                    Jadval(bet=n, sarlavhalar=qatorlar[0], qatorlar=qatorlar[1:])
                )

            # ── text (everything outside the tables) ──
            # The table areas are cut out, otherwise the table text would get
            # mixed in with the prose.
            toza = bet
            for jadval_obyekt in bet.find_tables():
                toza = toza.outside_bbox(jadval_obyekt.bbox)
            xom_matn = toza.extract_text(layout=True) or ""
            satrlar = [s.rstrip() for s in xom_matn.split("\n")
                       if s.strip() and not _shovqinmi(s)]
            h.betlar.append("\n".join(satrlar))

    h.matn = "\n".join(h.betlar)
    h.skanermi = len(re.sub(r"\s", "", h.matn)) < c.MATN_CHEGARA

    if h.skanermi and ocr:
        _ocr_bilan_toldir(h, korsat=korsat)
    return h


def _ocr_bilan_toldir(h: Hujjat, korsat: bool = False) -> None:
    """Fills a scanned document in from the OCR result (modifies it in place)."""
    from app.services.ocr import ocr_toliq          # avoids a circular import

    natija = ocr_toliq(h.yol, korsat=korsat)
    h.betlar = [
        "\n".join(s.rstrip() for s in bet.split("\n")
                  if s.strip() and not _shovqinmi(s))
        for bet in natija["betlar"]
    ]
    h.matn = "\n".join(h.betlar)
    h.jadvallar = [
        Jadval(bet=j["bet"], sarlavhalar=j["sarlavhalar"], qatorlar=j["qatorlar"])
        for j in natija["jadvallar"]
    ]


# ─────────────────────────────── CLI ─────────────────────────────────────
def _korsat(h: Hujjat) -> None:
    ch.bolim(h.nom)
    ch.maydon("pages", len(h.betlar))
    ch.maydon("text", f"{len(h.matn):,} characters")
    ch.maydon("tables", len(h.jadvallar),
              izoh="via OCR" if h.skanermi else "")
    for j in h.jadvallar:
        ch.maydon(f"  table (page {j.bet})",
                  f"{len(j.sarlavhalar)} columns × {len(j)} rows")
        print(f"      {ch.kul(' | '.join(x[:22] for x in j.sarlavhalar))}")
        for q in j.qatorlar[:2]:
            print(f"      {' | '.join(x[:22] for x in q)}")
        if len(j) > 2:
            print(f"      {ch.kul(f'... {len(j) - 2} more rows')}")


def main() -> int:
    ch.sarlavha("Reading PDFs — text and tables")
    arg = [Path(a) for a in sys.argv[1:] if not a.startswith("-")]
    yollar = arg or sorted((c.SKANER if "--skaner" in sys.argv else c.MATNLI)
                           .glob("*.pdf"))
    for yol in yollar:
        _korsat(oqi(yol, korsat=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
