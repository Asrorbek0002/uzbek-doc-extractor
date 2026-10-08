# -*- coding: utf-8 -*-
"""Rebuilding a scanned table from coordinates.

THE PROBLEM

    In a digital PDF, pdfplumber sees the table's RULING LINES and returns the
    cells correctly. A scan has neither lines nor a text layer — only pixels.
    And plain OCR text mixes the columns up:

        1 { intellekt qo'llash mumkin bo'lgan Tizim tahlili bo`limi i o 20.09.2026
        5 "ру ro'yxati                        ← the ruling lines were read as letters

THE SOLUTION: the COORDINATES of every word are taken from OCR and the table is
rebuilt geometrically.

    1. tesseract --psm 11 (sparse text) + TSV output
       MEASURED: with --psm 3 most of the 152 words were garbage; with
       --psm 11 the mean confidence is 94.0 and only 1 word is low-confidence.
    2. the words are grouped into TEXT LINES by y
    3. the HEADER row defines the columns (x ranges)
       — the number of columns varies from document to document (4 or 5)
    4. the text lines are grouped into LOGICAL ROWS
       MEASURED: inside a row the lines are 26-31 px apart, between rows
       85-87 px — a factor of 2.5. The threshold is set on that.

Running it:
    python -m app.services.table_extractor <scan.pdf>
    python -m app.services.table_extractor            # tries the 6 scans
"""
from __future__ import annotations

import csv
import io
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.core import console as ch
from app.core import config as c
from app.services.pdf_processor import Jadval

# In Uzbek orthography no character other than an apostrophe occurs between two
# LETTERS. OCR, however, can turn an apostrophe ("o'", "g'") into something else.
#
# MEASURED: in the NAMUNA_3 scan, "yig'ilishiga" -> "yig£ilishiga" (U+00A3).
# Interestingly, "to'g'risida" on THAT VERY LINE was read correctly — the error
# is random, so switching the language model does not help; a positional fix is
# what is needed.
#
# The rule is safe: a currency or other sign appears next to a digit or a space,
# never BETWEEN letters.
HARF_ORASI = re.compile(r"(?<=[a-zA-Z])[£§°¢¤|](?=[a-zA-Z])")


def apostrof_tuzat(matn: str) -> str:
    """Turns a stray character between letters back into an apostrophe."""
    return HARF_ORASI.sub("'", matn or "")


ISHONCH_CHEGARA = 40          # below this — a ruling line or noise
SATR_CHEGARA = 0.7            # relative to line height: is this one line
QATOR_KOEFF = 2.5             # if the line spacing grows by this factor — a new row
# MEASURED: 26-31 px inside a row, 85-87 px between rows. But some cells (a
# multi-line deadline) show 62 px — a factor of 2.2 split those wrongly, while
# 2.5 works correctly (a 70 px threshold).
USTUN_BOSHLIQ = 45            # the gap that separates columns in the header

PSM_ASOSIY = "11"             # sparse text — does not read ruling lines as letters
PSM_RAQAM = "6"               # a single block — ONLY for standalone digits
RAQAM_TOKEN = re.compile(r"^\d{1,2}\s*[.)]?$")
RAQAM_ISHONCH = 80            # a high bar for a digit that gets restored
# WHY TWO PASSES (measured, on 2 documents):
#          words  mean conf  conf<40  garbage  Cyrillic
#   psm 3    181       90.1       11        5         0
#   psm 6    182       86.5       19        4         9
#   psm 11   166       95.4        0        0         0   <- the cleanest
# psm 11 is the cleanest, BUT it misses the standalone digits in the "№"
# column (1 2 3 4 5) entirely. psm 6 finds them with 94-97% confidence, but
# also adds 9-12 spurious Cyrillic words. So psm 11 stays the primary source
# and ONLY short numeric tokens are taken from psm 6.


@dataclass
class Soz:
    matn: str
    x: int
    y: int
    w: int
    h: int
    ishonch: float

    @property
    def markaz(self) -> int:
        return self.x + self.w // 2


def _tsv(rasm: Path, til: str, psm: str, chegara: float) -> list[Soz]:
    """One tesseract pass — the words with their coordinates."""
    natija = subprocess.run(
        ["tesseract", str(rasm), "-", "-l", til, "--psm", psm, "tsv"],
        check=True, capture_output=True, text=True)
    # QUOTE_NONE IS MANDATORY: if a cell contains a quote character (e.g.
    # "Mas'ul" or “YANGI AVLOD”), the csv module reads it as a field delimiter,
    # glues the remaining rows into one field and the TSV falls apart.
    oqigich = csv.DictReader(io.StringIO(natija.stdout), delimiter="\t",
                             quoting=csv.QUOTE_NONE)
    sozlar = []
    for q in oqigich:
        matn = (q.get("text") or "").strip()
        if not matn:
            continue
        try:
            ishonch = float(q["conf"])
        except (KeyError, ValueError):
            continue
        if ishonch < chegara:
            continue
        sozlar.append(Soz(matn, int(q["left"]), int(q["top"]),
                          int(q["width"]), int(q["height"]), ishonch))
    return sozlar


def _kesishadi(a: Soz, b: Soz) -> bool:
    """Do the two words' boxes overlap."""
    return (a.x < b.x + b.w and b.x < a.x + a.w
            and a.y < b.y + b.h and b.y < a.y + a.h)


def _raqamlarni_tikla(rasm: Path, til: str, bor: list[Soz]) -> list[Soz]:
    """Takes the standalone digits psm 11 missed from psm 6.

    Only short numeric tokens ("1", "2.", "10)") are accepted, and only those
    that do not land on an existing word box — that keeps psm 6's Cyrillic
    garbage out.
    """
    return [s for s in _tsv(rasm, til, PSM_RAQAM, RAQAM_ISHONCH)
            if RAQAM_TOKEN.match(s.matn) and not any(_kesishadi(s, b) for b in bor)]


def sozlar_ol(rasm: Path, til: str = None) -> list[Soz]:
    """Reads the words with their coordinates out of the image (two passes)."""
    til = til or c.OCR_TIL
    sozlar = _tsv(rasm, til, PSM_ASOSIY, ISHONCH_CHEGARA)
    sozlar += _raqamlarni_tikla(rasm, til, sozlar)
    sozlar.sort(key=lambda s: (s.y, s.x))
    return sozlar


def matn_satrlari(sozlar: list[Soz]) -> list[list[Soz]]:
    """Groups the words into text lines by y.

    CHAINED grouping: each word is compared against the LAST word added, not
    against the FIRST word of the line.

    WHY: in a table row the font and the baseline differ between columns. One
    line measured in `xat_2` spans 34 px, from 1673 (Biznes-tahlil) to 1707
    ("va"), while the threshold is 28. Anchored to the first word, "va" fell
    out of the line, moved to the next one and the cell text came out broken as
    "vakolatlar tashkiliy va tuzilma" (it should be "vakolatlar va tashkiliy
    tuzilma").

    To keep the chain from growing without bound, the line's total height is
    capped as well (it must not exceed `balandlik`) — otherwise a neighbouring
    line could join the chain: in xat_2 the lines are 45-57 px apart while the
    spread inside a line is 34 px.
    """
    if not sozlar:
        return []
    balandlik = sorted(s.h for s in sozlar)[len(sozlar) // 2]
    chegara = max(int(balandlik * SATR_CHEGARA), 8)
    kenglik = max(balandlik, chegara + 1)
    satrlar = [[sozlar[0]]]
    for s in sozlar[1:]:
        oxirgi = satrlar[-1][-1].y
        bosh = min(z.y for z in satrlar[-1])
        if abs(s.y - oxirgi) <= chegara and s.y - bosh <= kenglik:
            satrlar[-1].append(s)
        else:
            satrlar.append([s])
    for sat in satrlar:
        sat.sort(key=lambda s: s.x)
    return satrlar


# The column names in a table header. They are matched as WHOLE WORDS — a
# fragment inside running text, such as "muddatlarda bajarilishini", is not a
# header.
MUDDAT_SOZ = {"muddat", "muddati", "sana"}
RAQAM_SOZ = {"t/r", "№", "no", "ne", "n", "tr", "t/p"}
MATN_SOZ = {"topshiriq", "chora-tadbir", "mazmuni", "vazifa"}


def _tokenlar(sozlar: list[Soz]) -> set[str]:
    return {re.sub(r"[^\w/'’-]", "", s.matn).lower() for s in sozlar}


def _sarlavhami(sozlar: list[Soz]) -> bool:
    """Is this set of words a table header.

    Three conditions: there is a "Muddat" column · there is a number or text
    column · the line is short. The last one matters — the word "muddat" also
    occurs in running prose, but there it sits in a long sentence.
    """
    tok = _tokenlar(sozlar)
    if not (tok & MUDDAT_SOZ):
        return False
    if not (tok & RAQAM_SOZ or tok & MATN_SOZ):
        return False
    return len(sozlar) <= 12


def _sarlavha_topish(satrlar: list[list[Soz]]) -> tuple[int, int, list[Soz]] | None:
    """Finds the table header -> (start, how many lines, words).

    A header can be split across TWO lines — OCR sometimes reads the "Muddat"
    column lower down (exactly what happens in NAMUNA_3):
        No Topshiriq mazmuni Mas'ul ijrochi
        Muddat
    """
    # Pass 1: a SINGLE-LINE header. All of them are checked first, because a
    # two-line combination may coincidentally match an earlier text line and
    # fire before the real header.
    for i, sat in enumerate(satrlar):
        if _sarlavhami(sat):
            return i, 1, sat

    # Pass 2: in case the header is split across two lines
    for i, sat in enumerate(satrlar[:-1]):
        keyingi = satrlar[i + 1]
        balandlik = max(s.h for s in sat)
        yaqinmi = (min(s.y for s in keyingi) - min(s.y for s in sat)
                   <= balandlik * 2.5)
        if yaqinmi and _sarlavhami(sat + keyingi):
            return i, 2, sorted(sat + keyingi, key=lambda s: s.x)

    return None


def _ustunlar(sarlavha: list[Soz]) -> list[dict]:
    """Splits the header words into labels and gives the column boundaries."""
    guruh = [[sarlavha[0]]]
    for s in sarlavha[1:]:
        oldin = guruh[-1][-1]
        if s.x - (oldin.x + oldin.w) > USTUN_BOSHLIQ:
            guruh.append([s])
        else:
            guruh[-1].append(s)
    return [{"nom": " ".join(x.matn for x in g),
             "a": g[0].x, "b": g[-1].x + g[-1].w} for g in guruh]


# For deciding where the table ended. In a real row the last column is the
# deadline; if the text after the table (prose, a signature) accidentally turns
# into a row, there will be no deadline in it.
MUDDAT_BELGI = re.compile(
    r"\d{4}|\d{1,2}\.\d{2}\.\d{4}|\bhar\b|\bichida\b|\bqadar\b|\bmuddat|"
    r"\bdoimiy\b|\bso'ng\b|\bsoʻng\b|\bkun\b|\boy\b|\bhafta|\bchorak",
    re.IGNORECASE)


def _muddatga_oxshaydi(katak: str) -> bool:
    return bool(MUDDAT_BELGI.search(katak or ""))


def _qator_chegaralari(sozlar: list[Soz], ustun_i) -> list[int]:
    """Finds the logical row boundaries (y).

    IMPORTANT: the distances are measured along the column with the MOST words
    (the action item text) ONLY. Mixing all the columns together lets a
    multi-line cell in the deadline column ("prototip tayyor bo'lgandan so'ng
    10 kun ichida") distort the distances and the rows run into each other.

    MEASURED (NAMUNA_2, the text column alone):
        inside a row   55-57 px
        between rows   86-142 px
    Mixed together it came out as 40-62 ↔ 62-126, which cannot be separated.
    """
    import collections
    sanoq = collections.Counter(ustun_i(s.markaz) for s in sozlar)
    if not sanoq:
        return []
    asosiy = sanoq.most_common(1)[0][0]
    ustun_sozlari = sorted((s for s in sozlar if ustun_i(s.markaz) == asosiy),
                           key=lambda s: s.y)
    if len(ustun_sozlari) < 2:
        return []

    # the text lines inside that column
    balandlik = sorted(s.h for s in ustun_sozlari)[len(ustun_sozlari) // 2]
    satr_y = []
    for s in ustun_sozlari:
        if not satr_y or s.y - satr_y[-1] > balandlik * 0.7:
            satr_y.append(s.y)

    farqlar = [satr_y[i + 1] - satr_y[i] for i in range(len(satr_y) - 1)]
    if not farqlar:
        return []
    # NOT THE MEDIAN, THE LOWER QUARTILE. The reason: when the rows are two
    # lines tall, the distances alternate (55, 86, 56, 113, 57, 114...) and
    # half of them are "within a row" while half are "between rows" — the
    # median lands right in the middle and the threshold comes out above the
    # row boundary. The lower quartile always gives the "within a row" distance.
    tartib = sorted(farqlar)
    asos = tartib[len(tartib) // 4]
    chegara = asos * 1.4

    # The boundary is placed half a line above the START OF THE NEXT ROW, not
    # in the MIDDLE OF THE GAP.
    #
    # WHY: a multi-line cell in another column (the deadline) may end BELOW the
    # last line of its own row. Measured on NAMUNA_3 —
    #     text column:     ... 1084            1198 (the next row)
    #     deadline column: ... 1084  1141
    # the middle of the gap, (1084+1198)/2 = 1141, fell exactly on that
    # boundary and "soʻng 3 oy ichida" moved into the NEXT row. 1198 - 56/2 =
    # 1170 keeps it in its own row and still works when the next row starts
    # slightly above its own line.
    kesim = []
    for i, f in enumerate(farqlar):
        if f > chegara:
            kesim.append(max(satr_y[i] + 1, satr_y[i + 1] - asos // 2))
    return kesim


def _kesim_nuqtalari(ustunlar: list[dict], tana: list[Soz]) -> list[int]:
    """Finds the column boundaries from the empty corridors in the BODY text.

    WHY the header alone is not enough: the header is CENTERED inside its cell
    while the body text is LEFT-ALIGNED. The case measured in `xat_2` —

        header:    "T/r" 337..400        "Topshiriq mazmuni" 765..1153
        midpoint:                 582
        body:                           "Murojaatlar" 466..681

    i.e. the 582 boundary fell in the MIDDLE of the body text and split the
    action item in two ("Murojaatlar 1 bo'yicha" | "portalidagi..."). The widest
    vertical gap between the body words, on the other hand, is 376..465 — the
    real boundary is there.
    """
    kesim = []
    for i in range(len(ustunlar) - 1):
        chap = (ustunlar[i]["a"] + ustunlar[i]["b"]) // 2
        ong = (ustunlar[i + 1]["a"] + ustunlar[i + 1]["b"]) // 2
        # the body words that fall inside that window
        oraliq = sorted((s.x, s.x + s.w) for s in tana
                        if s.x + s.w > chap and s.x < ong)
        eng, nuqta, oxir = 0, (chap + ong) // 2, chap
        for a, b in oraliq:
            if a - oxir > eng:
                eng, nuqta = a - oxir, (oxir + a) // 2
            oxir = max(oxir, b)
        if ong - oxir > eng:
            nuqta = (oxir + ong) // 2
        kesim.append(nuqta)
    return kesim


def _qatorlar_tuz(tana_satr: list[tuple[int, Soz]], ustunlar: list[dict],
                  kesim: list[int]) -> tuple[list[list[str]], int]:
    """Assembles the words into rows using the given column boundaries.

    Returns: (rows, y of the table's end) — the second value is what pass 2
    needs in order to separate the table zone from the prose.
    """
    def ustun_i(x: int) -> int:
        for i, k in enumerate(kesim):
            if x < k:
                return i
        return len(ustunlar) - 1

    tana = [s for _, s in tana_satr]
    kesim_y = _qator_chegaralari(tana, ustun_i)

    def qator_i(y: int) -> int:
        for i, k in enumerate(kesim_y):
            if y < k:
                return i
        return len(kesim_y)

    guruh: dict[int, list[tuple[int, Soz]]] = {}
    for i, s in tana_satr:
        guruh.setdefault(qator_i(s.y), []).append((i, s))

    kalitlar = sorted(guruh)
    qatorlar, chegaralar = [], []
    for k in kalitlar:
        kataklar = [""] * len(ustunlar)
        # Inside a cell the order follows the LINE. Sorting by raw `y` shuffles
        # the words: within one line y wobbles by 2-6 px, and "Tizim tahlili
        # bo'limi" came out as "tahlili bo'limi Tizim".
        for _, s in sorted(guruh[k], key=lambda z: (z[0], z[1].x)):
            i = ustun_i(s.markaz)
            kataklar[i] = (kataklar[i] + " " + apostrof_tuzat(s.matn)).strip()
        if any(kataklar):
            qatorlar.append(kataklar)
            chegaralar.append(max(s.y + s.h for _, s in guruh[k]))

    # Deciding where the table ended: if TWO CONSECUTIVE rows carry no
    # deadline, the table is over and what follows is text (prose, signature).
    #
    # Why one row is not enough: OCR can split a deadline across two lines and
    # leave only its beginning in the cell ("texnik topshiriq" — while
    # "tasdiqlangandan so'ng 3 oy ichida" is on the next line). Stopping on a
    # single row would cut real rows off.
    for i in range(len(qatorlar) - 1):
        if (not _muddatga_oxshaydi(qatorlar[i][-1])
                and not _muddatga_oxshaydi(qatorlar[i + 1][-1])):
            qatorlar, chegaralar = qatorlar[:i], chegaralar[:i]
            break

    # The boilerplate at the bottom of the page — not part of the table
    saqla = [i for i, q in enumerate(qatorlar)
             if not re.search(r"Test uchun example|Tashkilot nomlari", " ".join(q))]
    qatorlar = [qatorlar[i] for i in saqla]
    oxiri = max((chegaralar[i] for i in saqla), default=0)
    return qatorlar, oxiri


def jadval_tikla(sozlar: list[Soz], bet: int = 1) -> Jadval | None:
    """Rebuilds the table from a set of words. None when no table is found.

    It works in TWO PASSES:

      pass 1 — the column boundaries are taken from the midpoints between the
               HEADER words. That is coarse, but enough to find WHERE THE TABLE
               ENDS.
      pass 2 — now that the table zone is known, the boundaries are recomputed
               from the empty corridors between the words IN THAT ZONE only.

    Why pass 2 is needed: the header is centered in its cell while the body
    text is left-aligned — in `xat_2` the header midpoint fell at 582 and split
    an action item that starts at 465 in two.

    Why the corridors cannot be computed right away: the prose AFTER the table
    spreads across the page and fills every empty corridor. Excluding it
    requires knowing where the table ends — which is exactly what pass 1 is for.
    """
    satrlar = matn_satrlari(sozlar)
    topilgan = _sarlavha_topish(satrlar)
    if topilgan is None:
        return None
    bosh, nechta, sarlavha_sozlari = topilgan

    ustunlar = _ustunlar(sarlavha_sozlari)
    if len(ustunlar) < 3:
        return None

    tana_satr = [(i, s) for i, sat in enumerate(satrlar[bosh + nechta:]) for s in sat]

    # pass 1 — the header midpoints
    kesim = [(ustunlar[i]["b"] + ustunlar[i + 1]["a"]) // 2
             for i in range(len(ustunlar) - 1)]
    qatorlar, oxiri = _qatorlar_tuz(tana_satr, ustunlar, kesim)
    if not qatorlar:
        return None

    # pass 2 — the empty corridors between the words in the table zone only
    zona = [s for _, s in tana_satr if s.y <= oxiri]
    aniq = _kesim_nuqtalari(ustunlar, zona)
    if aniq != kesim:
        yangi, _ = _qatorlar_tuz(tana_satr, ustunlar, aniq)
        if yangi:
            qatorlar = yangi

    # The table's area: from the header down to the last accepted row. Used to
    # cut the table out of the page text.
    ichida = [s for s in sarlavha_sozlari] + [s for _, s in tana_satr if s.y <= oxiri]
    maydon = (min(s.x for s in ichida), min(s.y for s in ichida),
              max(s.x + s.w for s in ichida), max(s.y + s.h for s in ichida))
    return Jadval(bet=bet, sarlavhalar=[u["nom"] for u in ustunlar],
                  qatorlar=qatorlar, maydon=maydon)


def pdfdan(yol: str | Path) -> list[Jadval]:
    """Rebuilds every table in a scanned PDF."""
    yol = Path(yol)
    jadvallar = []
    with tempfile.TemporaryDirectory() as vaqtli:
        subprocess.run(["pdftoppm", "-r", str(c.OCR_DPI), "-png", str(yol),
                        str(Path(vaqtli) / "bet")], check=True, capture_output=True)
        for n, rasm in enumerate(sorted(Path(vaqtli).glob("bet-*.png")), 1):
            j = jadval_tikla(sozlar_ol(rasm), bet=n)
            if j:
                jadvallar.append(j)
    return jadvallar


# ─────────────────────────────── CLI ─────────────────────────────────────
def main() -> int:
    ch.sarlavha("Rebuilding a scanned table from coordinates")
    yollar = ([Path(a) for a in sys.argv[1:] if not a.startswith("-")]
              or sorted(c.SKANER.glob("*.pdf")))
    for yol in yollar:
        ch.bolim(yol.stem)
        jadvallar = pdfdan(yol)
        if not jadvallar:
            ch.eslatma("no table found (a prose document)")
            continue
        for j in jadvallar:
            ch.maydon("page", j.bet)
            ch.maydon("columns", f"{len(j.sarlavhalar)} — " +
                      " | ".join(x[:16] for x in j.sarlavhalar))
            ch.maydon("rows", len(j))
            print()
            ch.jadval([x[:13] for x in j.sarlavhalar],
                      [[k[:26] for k in q] for q in j.qatorlar])
    return 0


if __name__ == "__main__":
    sys.exit(main())
