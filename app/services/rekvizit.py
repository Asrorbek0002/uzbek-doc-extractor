# -*- coding: utf-8 -*-
"""Extracting the letterhead fields: organization, number, date, signatory.

FROM THE ASSIGNMENT: "Letterhead fields: the sending organization, the document
number, its date, the signatory." — exactly those four. The rest (position,
clerk) are extras.

TWO DOCUMENT TYPES, TWO LAYOUTS

    A LETTER (xat)                       A DECREE (qaror)
    ───────────────────────────────      ───────────────────────────────
    MA'LUMOTLAR ... AGENTLIGI            HUQUQIY ... MILLIY AGENTLIGI
    100060, Toshkent shahri, Tel.:       KENGASHINING
    15.09.2026 № 07-04/2219              Q A R O R I
    ...                                  2026-yil 10-fevral | Toshkent | № 121
    Direktor        D. Ergasheva         ...
    Ijrochi: B. Hamidov                  Kengash raisi    M. Tursunov

The type is decided by the word "QARORI". NOTE: in the PDF it comes out with
spaces between the letters ("Q  A R O R I"), so the spaces are stripped before
comparing.

Running it:
    python -m app.services.rekvizit            # the 6 documents
    python -m app.services.rekvizit <file>
"""
from __future__ import annotations

import re
import sys
from dataclasses import dataclass, asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.core import config as c
from app.core import console as ch
from app.services.pdf_processor import Hujjat, oqi

# Uzbek apostrophes: ' ’ ‘ ʻ ʼ — all normalized to one form
APOSTROF = str.maketrans({"’": "'", "‘": "'", "ʻ": "'", "ʼ": "'", "`": "'"})

OYLAR = {
    "yanvar": 1, "fevral": 2, "mart": 3, "aprel": 4, "may": 5, "iyun": 6,
    "iyul": 7, "avgust": 8, "sentabr": 9, "oktabr": 10, "noyabr": 11, "dekabr": 12,
}

# ── the date ──
SANA_RAQAM = re.compile(r"\b(\d{2})\.(\d{2})\.(\d{4})\b")                    # 15.09.2026
SANA_SOZ = re.compile(                                                        # 2026-yil 10-fevral
    r"\b(\d{4})\s*-?\s*yil\w*\s+(\d{1,2})\s*-?\s*("
    + "|".join(OYLAR) + r")\w*", re.IGNORECASE)

# ── the document number: № 07-04/2219 or № 121 ──
RAQAM = re.compile(r"[№N]\s*([0-9][0-9\-/._]*)")

# ── the signature: "Direktor ... D. Ergasheva" / "Kengash raisi ... M. Tursunov" ──
# The name form: initial(s) + a dot + the surname.
# NOTE: an Uzbek initial can consist of TWO characters — "Sh. Qodirov",
# "Ch. Rahimov", "O'. Karimov". Hence an optional lowercase letter or
# apostrophe after the initial.
ISM = re.compile(
    r"\b([A-ZА-Я](?:[a-zа-я]|['’‘ʻ])?\.)\s*"      # Sh.  D.  O'.
    r"([A-ZА-Я][a-zа-я'’‘ʻ]{2,})\b"                # the surname
)
IJROCHI = re.compile(r"Ijrochi\s*:\s*(.+?)\s*$", re.IGNORECASE | re.MULTILINE)

# In a letter's header the recipient sits on the RIGHT, on the same line as the
# date and number. Read out of the PDF, the two land on one line:
#     15.09.2026 № 07-04/2219          Adliya organlari va muassasalarida axborot
#     «____» ____________ dagi ________-son xatga  texnologiyalarini ... markaziga
# So the boilerplate on the LEFT is removed and what remains is the recipient.
XATGA_QOLIP = re.compile(r"«_+»\s*_+\s*dagi\s*_+\s*-?\s*son\s+xatga", re.IGNORECASE)

# The positions that appear on a signature line
LAVOZIMLAR = ("raisi", "direktor", "boshlig", "rahbar", "o'rinbosar", "kotib",
              "vazir", "hokim", "mudir")


@dataclass
class Rekvizit:
    tur: str = ""              # "xat" (letter) | "qaror" (decree)
    qabul_qiluvchi: str = ""   # who the letter was sent to (absent in decrees)
    tashkilot: str = ""        # the sending organization
    raqam: str = ""            # the document number
    sana: str = ""             # the document date (as written in the document)
    sana_iso: str = ""         # YYYY-MM-DD — for computation
    imzolagan: str = ""        # the signatory
    lavozim: str = ""          # extra
    ijrochi: str = ""          # extra (present in letters)

    def toliqmi(self) -> bool:
        """Were all 4 fields the assignment asks for found."""
        return all([self.tashkilot, self.raqam, self.sana, self.imzolagan])


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s.translate(APOSTROF)).strip()


def _bosh_harflimi(satr: str) -> bool:
    """Is the line mostly UPPERCASE (that is how an organization name is written)."""
    harflar = [x for x in satr if x.isalpha()]
    if len(harflar) < 6:
        return False
    return sum(x.isupper() for x in harflar) / len(harflar) > 0.85


def turini_aniqla(satrlar: list[str]) -> str:
    """The word "QARORI" means a decree, otherwise it is a letter.

    In the PDF spaces fall between the letters ("Q  A R O R I"), so the spaces
    are stripped before comparing.
    """
    for s in satrlar[:8]:
        if "QARORI" in re.sub(r"\s+", "", s).upper():
            return "qaror"
    return "xat"


def _sana(matn: str) -> tuple[str, str]:
    """(as written in the document, ISO). Both empty when nothing is found."""
    m = SANA_RAQAM.search(matn)
    if m:
        k, o, y = m.groups()
        return m.group(0), f"{y}-{o}-{k}"
    m = SANA_SOZ.search(matn)
    if m:
        y, k, oy = m.group(1), m.group(2), m.group(3).lower()
        return _norm(m.group(0)), f"{y}-{OYLAR[oy]:02d}-{int(k):02d}"
    return "", ""


def _tashkilot(satrlar: list[str], tur: str) -> str:
    """The uppercase lines in the header — the organization's name.

    In a decree the name spans two lines ("... AGENTLIGI" + "KENGASHINING"), so
    consecutive uppercase lines are joined. The "QARORI" line is not part of
    the name.
    """
    qismlar = []
    for s in satrlar[:6]:
        toza = _norm(s)
        if not toza or "QARORI" in re.sub(r"\s+", "", toza).upper():
            continue
        # the address line: it carries a postcode, Tel., E-mail
        if re.search(r"\d{5,}|Tel\.|E-mail|@", toza):
            break
        if _bosh_harflimi(toza):
            qismlar.append(toza)
        elif qismlar:
            break
    return _norm(" ".join(qismlar))


def _qabul_qiluvchi(satrlar: list[str]) -> str:
    """Who the letter was sent to — the right column of the header.

    Decrees have no such field (they are internal documents), so it comes back
    empty. That is normal, not an error.
    """
    qismlar = []
    for s in satrlar:
        toza = _norm(s)
        m = XATGA_QOLIP.search(toza)          # «____» ____ dagi ____-son xatga
        if m:
            qolgan = toza[m.end():].strip()
            if qolgan:
                qismlar.append(qolgan)
            continue
        mr = RAQAM.search(toza)               # the date + number line
        if mr and (SANA_RAQAM.search(toza) or SANA_SOZ.search(toza)):
            qolgan = toza[mr.end():].strip()
            # in a decree the right side carries "Toshkent shahri" — not a recipient
            if qolgan and not re.fullmatch(r"[\w'’\s]*shahri", qolgan, re.IGNORECASE):
                qismlar.append(qolgan)
    nom = _norm(" ".join(qismlar))
    # a recipient ends in the dative case: "...markaziga"
    return nom if re.search(r"(ga|iga|ka|qa)\s*$", nom) else ""


def _imzo(satrlar: list[str]) -> tuple[str, str]:
    """(the signatory, their position). Searched from the end backwards."""
    for s in reversed(satrlar):
        toza = _norm(s)
        if not toza or toza.lower().startswith("ijrochi"):
            continue
        m = ISM.search(toza)
        if not m:
            continue
        ism = _norm(f"{m.group(1)} {m.group(2)}")
        # whatever precedes the name is the position
        lavozim = _norm(toza[:m.start()])
        if lavozim and any(x in lavozim.lower() for x in LAVOZIMLAR):
            return ism, lavozim
        if lavozim:
            return ism, lavozim
    return "", ""


def ajrat(h: Hujjat) -> Rekvizit:
    satrlar = [s for s in h.betlar[0].split("\n") if s.strip()]
    r = Rekvizit(tur=turini_aniqla(satrlar))
    r.tashkilot = _tashkilot(satrlar, r.tur)

    # The date and the number sit at the TOP of the document (line 4 in a
    # letter, and near the top in a decree too). Only those upper lines are
    # searched — the body holds other dates (action item deadlines) and they
    # must not be confused with these.
    bosh = "\n".join(satrlar[:8])
    r.sana, r.sana_iso = _sana(bosh)
    m = RAQAM.search(bosh)
    if m:
        r.raqam = m.group(1).strip(" .-/")

    r.qabul_qiluvchi = _qabul_qiluvchi(satrlar[:8])
    r.imzolagan, r.lavozim = _imzo(satrlar)
    m = IJROCHI.search(h.matn)
    if m:
        r.ijrochi = _norm(ISM.search(m.group(1)).group(0)) if ISM.search(m.group(1)) \
            else _norm(m.group(1))
    return r


# ─────────────────────────────── CLI ─────────────────────────────────────
def main() -> int:
    ch.sarlavha("Extracting the letterhead fields")
    yollar = ([Path(a) for a in sys.argv[1:] if not a.startswith("-")]
              or sorted(c.MATNLI.glob("*.pdf")))
    qatorlar, toliq = [], 0
    for yol in yollar:
        r = ajrat(oqi(yol))
        toliq += r.toliqmi()
        qatorlar.append([
            yol.stem[:26], r.tur,
            (r.tashkilot[:30] + "…") if len(r.tashkilot) > 30 else r.tashkilot,
            r.raqam or "—", r.sana_iso or "—", r.imzolagan or "—",
            ch.yashil(ch.OK) if r.toliqmi() else ch.qizil(ch.XATO),
        ])
    ch.jadval(["document", "type", "organization", "number", "date", "signatory", ""],
              qatorlar)
    ch.natija(toliq == len(yollar),
              f"all 4 fields found in: {toliq}/{len(yollar)} documents")
    return 0 if toliq == len(yollar) else 1


if __name__ == "__main__":
    sys.exit(main())
