# -*- coding: utf-8 -*-
"""Understanding and normalizing a deadline.

THE CENTRAL DECISION: a deadline is never FORCED into a single date.

These documents carry 7 different kinds of deadline and not all of them can be
turned into a date. "within 10 days after the prototype is ready" — the
document never says when the prototype will be ready, so the date CANNOT BE
COMPUTED. Admitting that is more correct than inventing an approximate date: a
wrong date looks authoritative and misleads whoever tracks the execution.

So every deadline comes back with a `tur` ("type"):

    absolyut        an exact date          2026-yil 1-may · 18.09.2026
    nisbiy          from the document date bir oy muddatda · uch ish kuni ichida
    takrorlanuvchi  periodic, no single date  har chorakda · har oyning 25-sanasiga qadar
    bogliq          tied to another event     prototip tayyor bo'lgandan so'ng 10 kun
    doimiy          no end date            doimiy
    boshlanish      NOT a deadline         2026-yil 15-martdan boshlab
    yoq             not stated

The `sana` field is filled in only for `absolyut` and `nisbiy`.

Running it:
    python -m app.services.muddat        # tries every deadline in the documents
"""
from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.core import console as ch

APOSTROF = str.maketrans({"’": "'", "‘": "'", "ʻ": "'", "ʼ": "'", "`": "'"})

OYLAR = {
    "yanvar": 1, "fevral": 2, "mart": 3, "aprel": 4, "may": 5, "iyun": 6,
    "iyul": 7, "avgust": 8, "sentabr": 9, "oktabr": 10, "noyabr": 11, "dekabr": 12,
}

# Uzbek number words — "bir oy", "o'n kun", "uch ish kuni"
SONLAR = {
    "bir": 1, "ikki": 2, "uch": 3, "to'rt": 4, "besh": 5, "olti": 6,
    "yetti": 7, "sakkiz": 8, "to'qqiz": 9, "o'n": 10, "o'n besh": 15,
    "yigirma": 20, "o'ttiz": 30,
}

def _son_naqsh() -> str:
    """An alternation of the number words — WITH THE APOSTROPHE OPTIONAL.

    WHY: OCR loses the Uzbek apostrophe quite often. In the `xat_1` scan
    "o'n kun muddatda" came out as "on kun muddatda" and the relative deadline
    was missed entirely. This pattern also covers "tort/to'rt",
    "toqqiz/to'qqiz" and "ottiz/o'ttiz".
    """
    return "|".join(re.escape(s).replace("'", "['’‘ʻʼ]?")
                    for s in sorted(SONLAR, key=len, reverse=True))


SON_NAQSH = _son_naqsh()

SANA_RAQAM = re.compile(r"\b(\d{1,2})\.(\d{2})\.(\d{4})\b")
SANA_SOZ = re.compile(
    r"\b(\d{4})\s*-?\s*yil\w*\s+(\d{1,2})\s*-?\s*(" + "|".join(OYLAR) + r")\w*",
    re.IGNORECASE)

# "... bo'lgandan so'ng N kun/oy ichida" — tied to another event
BOGLIQ = re.compile(
    r"(bo'lgandan|tasdiqlangandan|tugagandan|qabul\s+qilingandan|imzolangandan)"
    r"\s+so'ng", re.IGNORECASE)

# "har ..." ("every ...") — recurring
TAKROR = re.compile(r"\bhar\b", re.IGNORECASE)

# "N kun/oy/hafta ichida|muddatda" — computed from the document date
NISBIY = re.compile(
    r"\b(\d+|" + SON_NAQSH + r")\s+"
    r"(ish\s+kuni|kun|hafta|oy|yil)\w*\s*(ichida|muddatda|davomida)?",
    re.IGNORECASE)

BOSHLANISH = re.compile(r"dan\s+boshlab\b", re.IGNORECASE)
DOIMIY = re.compile(r"\bdoimiy\b|\bmuntazam\b", re.IGNORECASE)


@dataclass
class Muddat:
    xom: str = ""          # as written in the document
    tur: str = "yoq"       # absolyut | nisbiy | takrorlanuvchi | bogliq | doimiy | boshlanish | yoq
    sana: str = ""         # ISO — only for absolyut and nisbiy
    izoh: str = ""         # why it was interpreted this way

    def __bool__(self) -> bool:
        return self.tur != "yoq"


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").translate(APOSTROF)).strip()


# Spelling without the apostrophe -> the number ("on" -> 10). Needed when OCR
# has dropped the apostrophe.
SONLAR_YALANG = {re.sub(r"['’‘ʻʼ]", "", k): v for k, v in SONLAR.items()}


def _son(s: str) -> int | None:
    s = _norm(s).lower()
    if s.isdigit():
        return int(s)
    if s in SONLAR:
        return SONLAR[s]
    return SONLAR_YALANG.get(re.sub(r"['’‘ʻʼ]", "", s))


def _ish_kuni_qosh(boshlanish: date, kunlar: int) -> date:
    """Adds working days (Saturdays and Sundays are skipped).

    Public holidays are NOT taken into account — they move from year to year
    and the document does not state them. That limitation is stated in the
    report.
    """
    kun = boshlanish
    qolgan = kunlar
    while qolgan > 0:
        kun += timedelta(days=1)
        if kun.weekday() < 5:
            qolgan -= 1
    return kun


def _oy_qosh(d: date, oylar: int) -> date:
    oy = d.month - 1 + oylar
    yil = d.year + oy // 12
    oy = oy % 12 + 1
    # so as not to run past the last day of the month
    kun = min(d.day, [31, 29 if yil % 4 == 0 and (yil % 100 != 0 or yil % 400 == 0)
                      else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][oy - 1])
    return date(yil, oy, kun)


def tahlil(xom: str, hujjat_sanasi: str = "") -> Muddat:
    """Analyses a deadline string.

    `hujjat_sanasi` (ISO) is used to compute relative deadlines. Without it the
    relative type is still identified, but no date is computed.
    """
    m = Muddat(xom=_norm(xom))
    matn = m.xom.lower()
    if not matn:
        return m

    # THE ORDER MATTERS: "bogliq" is checked first, because it contains
    # "2 oy ichida" inside it and would look like "nisbiy".
    if BOGLIQ.search(matn):
        m.tur = "bogliq"
        voqea = BOGLIQ.split(matn)[0].strip(" ,")
        n = NISBIY.search(matn)
        m.izoh = (f"«{voqea}» voqeasidan keyin"
                  + (f" {n.group(1)} {n.group(2)}" if n else ""))
        return m

    if DOIMIY.search(matn):
        m.tur, m.izoh = "doimiy", "tugash sanasi yo'q"
        return m

    if TAKROR.search(matn):
        m.tur, m.izoh = "takrorlanuvchi", "davriy — bitta sana yo'q"
        return m

    if BOSHLANISH.search(matn):
        m.tur = "boshlanish"
        s = SANA_SOZ.search(matn) or SANA_RAQAM.search(matn)
        if s:
            m.sana = _iso(s)
        m.izoh = "bu tugash muddati EMAS, ish boshlanish sanasi"
        return m

    # absolute
    s = SANA_RAQAM.search(matn)
    if s:
        m.tur, m.sana = "absolyut", _iso(s)
        m.izoh = "aniq sana"
        return m
    s = SANA_SOZ.search(matn)
    if s:
        m.tur, m.sana = "absolyut", _iso(s)
        m.izoh = "aniq sana"
        return m

    # relative
    n = NISBIY.search(matn)
    if n:
        son = _son(n.group(1))
        birlik = n.group(2).lower()
        m.tur = "nisbiy"
        m.izoh = f"hujjat sanasidan +{n.group(1)} {birlik}"
        if son and hujjat_sanasi:
            try:
                baza = date.fromisoformat(hujjat_sanasi)
            except ValueError:
                return m
            if "ish" in birlik:
                m.sana = _ish_kuni_qosh(baza, son).isoformat()
                m.izoh += " (ish kunlari)"
            elif birlik.startswith("kun"):
                m.sana = (baza + timedelta(days=son)).isoformat()
            elif birlik.startswith("hafta"):
                m.sana = (baza + timedelta(weeks=son)).isoformat()
            elif birlik.startswith("oy"):
                m.sana = _oy_qosh(baza, son).isoformat()
            elif birlik.startswith("yil"):
                m.sana = _oy_qosh(baza, son * 12).isoformat()
        return m

    return m


def _iso(mos) -> str:
    g = mos.groups()
    if len(g) == 3 and g[2].isdigit():          # DD.MM.YYYY
        return f"{g[2]}-{g[1]}-{int(g[0]):02d}"
    yil, kun, oy = g[0], g[1], g[2].lower()      # YYYY-yil DD-month
    return f"{yil}-{OYLAR[oy]:02d}-{int(kun):02d}"



# ─────────────────────── finding a deadline inside text ──────────────────
# In prose the deadline is not in a tidy column, it is buried IN A SENTENCE:
#   "... tahliliy ma'lumotni 2026-yil 20-sentabrga qadar Agentlikka taqdim etsin"
#                            └──────── the deadline ────┘
# So the patterns are tried IN ORDER: the most specific (recurring, dependent)
# first and the most general (relative) last. Otherwise "2 oy ichida" would be
# caught before "bo'lgandan so'ng 2 oy ichida".

_OY = "|".join(OYLAR)
NAQSHLAR = [
    # recurring — from the complex to the simple
    r"har\s+chorak\s+yakunidan\s+keyingi\s+oyning\s+\d{1,2}\s*-?\s*sanasiga\s+qadar",
    r"har\s+oyning\s+\d{1,2}\s*-?\s*sanasiga\s+qadar",
    r"har\s+haftaning\s+\w+\s+kuni",
    r"har\s+(oyda|chorakda|yilda|haftada|kuni)",
    # dependent
    r"[\w'’\s]{3,40}?(?:bo'lgandan|tasdiqlangandan|tugagandan|qabul\s+qilingandan)"
    r"\s+so'ng\s+\d+\s+(?:kun|oy|hafta)\w*\s*(?:ichida)?",
    # a start date (NOT a deadline, but it has to be recognized as such)
    rf"\d{{4}}\s*-?\s*yil\w*\s+\d{{1,2}}\s*-?\s*(?:{_OY})\w*dan\s+boshlab",
    # absolute
    rf"\d{{4}}\s*-?\s*yil\w*\s+\d{{1,2}}\s*-?\s*(?:{_OY})\w*(?:\s+qadar)?",
    r"\d{1,2}\.\d{2}\.\d{4}(?:\s+yilgacha)?",
    # relative
    r"(?:\d+|" + SON_NAQSH +
    r")\s+ish\s+kuni\s+(?:ichida|muddatda|davomida)",
    r"(?:\d+|" + SON_NAQSH +
    r")\s+(?:kun|hafta|oy|yil)\w*\s+(?:ichida|muddatda|davomida)",
    r"doimiy",
]
NAQSHLAR = [re.compile(x, re.IGNORECASE) for x in NAQSHLAR]


def topish(matn: str, hujjat_sanasi: str = "") -> Muddat:
    """Finds a deadline phrase in free text and analyses it.

    When nothing is found it returns `tur="yoq"` — which is a normal case: the
    document itself may have stated a default deadline rule (clause 6 of
    NAMUNA_1).
    """
    toza = _norm(matn)
    for naqsh in NAQSHLAR:
        m = naqsh.search(toza)
        if m:
            return tahlil(m.group(0), hujjat_sanasi)
    return Muddat()


# The document's own rule: "action items without an explicitly stated deadline
# shall be completed <deadline>" — NAMUNA_1 has exactly such a clause.
STANDART_QOIDA = re.compile(
    r"muddati\s+alohida\s+ko'rsatilmagan[^.]*?"
    r"((?:\d+|" + SON_NAQSH +
    r")\s+(?:kun|hafta|oy|yil)\w*\s+(?:ichida|muddatda))",
    re.IGNORECASE)


def standart_muddat(matn: str, hujjat_sanasi: str = "") -> Muddat | None:
    """Does the document carry a "for items without a stated deadline ..." rule."""
    m = STANDART_QOIDA.search(_norm(matn))
    if not m:
        return None
    mud = tahlil(m.group(1), hujjat_sanasi)
    mud.izoh += " (hujjatning standart muddat qoidasidan)"
    return mud


# ─────────────────────────────── the test ────────────────────────────────
SINOVLAR = [
    # (text, expected type, document date, expected date)
    ("18.09.2026", "absolyut", "2026-09-11", "2026-09-18"),
    ("2026-yil 1-may", "absolyut", "", "2026-05-01"),
    ("2026-yil 15-oktabr", "absolyut", "", "2026-10-15"),
    ("2026-yil 1-iyulga qadar", "absolyut", "", "2026-07-01"),
    ("01.10.2026 yilgacha", "absolyut", "", "2026-10-01"),
    ("bir oy muddatda", "nisbiy", "2026-02-10", "2026-03-10"),
    ("o'n kun muddatda", "nisbiy", "2026-09-08", "2026-09-18"),
    ("uch ish kuni ichida", "nisbiy", "2026-09-08", "2026-09-11"),
    ("har chorakda", "takrorlanuvchi", "", ""),
    ("har oyning 25-sanasiga qadar", "takrorlanuvchi", "", ""),
    ("har haftaning juma kuni", "takrorlanuvchi", "", ""),
    ("har chorak yakunidan keyingi oyning 10-sanasiga qadar", "takrorlanuvchi", "", ""),
    ("tizim tayyor bo'lgandan so'ng 2 oy ichida", "bogliq", "", ""),
    ("prototip tayyor bo'lgandan so'ng 10 kun ichida", "bogliq", "", ""),
    ("texnik topshiriq tasdiqlangandan so'ng 3 oy ichida", "bogliq", "", ""),
    ("doimiy", "doimiy", "", ""),
    ("2026-yil 15-martdan boshlab", "boshlanish", "", "2026-03-15"),
    ("", "yoq", "", ""),
]


def main() -> int:
    ch.sarlavha("The deadline normalizer — a test")
    qatorlar, xato = [], 0
    for xom, kutilgan_tur, hsana, kutilgan_sana in SINOVLAR:
        m = tahlil(xom, hsana)
        tur_ok = m.tur == kutilgan_tur
        sana_ok = m.sana == kutilgan_sana
        if not (tur_ok and sana_ok):
            xato += 1
        qatorlar.append([
            (xom or "(empty)")[:46],
            m.tur if tur_ok else ch.qizil(f"{m.tur}≠{kutilgan_tur}"),
            (m.sana or "—") if sana_ok else ch.qizil(f"{m.sana or '—'}≠{kutilgan_sana or '—'}"),
            ch.yashil(ch.OK) if tur_ok and sana_ok else ch.qizil(ch.XATO),
        ])
    ch.jadval(["deadline text", "type", "computed date", ""], qatorlar)
    print()
    ch.maydon("tests", f"{len(SINOVLAR) - xato}/{len(SINOVLAR)} passed", xato == 0)
    ch.natija(xato == 0, "the deadline normalizer works correctly" if xato == 0
              else f"{xato} test(s) failed")
    return 0 if xato == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
