# -*- coding: utf-8 -*-
"""Extracting action items: text + deadline + assignee.

FROM THE ASSIGNMENT: "Action items: every action item inside the document, with
its deadline and its assignee. Action items may appear in paragraphs, in
numbered clauses or in a table." — i.e. THREE layouts.

THE TABLE — the columns are found by HEADER, not by POSITION

    xat_2      T/r | Topshiriq mazmuni        | Mas'ul ijrochi | Muddat          (4)
    NAMUNA_2   №   | Topshiriq mazmuni        | Mas'ul ijrochi | Muddat          (4)
    xat_3      T/r | Chora-tadbir (topshiriq) | Mas'ul ijrochi | Natija shakli | Muddat   (5)

    The last one has an extra column. Taken by position, "Natija shakli" would
    have been read as the deadline.
"""
from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.core import config as c
from app.services.muddat import (Muddat, standart_muddat, tahlil as muddat_tahlil,
                             topish as muddat_topish)
from app.core import console as ch
from app.services.pdf_processor import Hujjat, Jadval, oqi

APOSTROF = str.maketrans({"’": "'", "‘": "'", "ʻ": "'", "ʼ": "'", "`": "'"})

# The possible names of the column headers.
# The "№" column. An EXACT match is used (`ustun(..., aniq=True)`), which makes
# it safe to list the OCR variants too: Tesseract reads "№" as "No", "Ne" or
# "N". As a substring, "no" would have matched "Tashkilot nomi".
U_RAQAM = ("t/r", "№", "n/r", "tartib", "no", "ne", "n", "tr", "t/p", "nr")
U_MATN = ("topshiriq", "chora-tadbir", "mazmun", "vazifa")
U_IJROCHI = ("ijrochi", "mas'ul", "bajaruvchi")
U_MUDDAT = ("muddat", "sana")


@dataclass
class Topshiriq:
    matn: str = ""
    ijrochi: str = ""
    muddat: Muddat = field(default_factory=Muddat)
    manba: str = ""        # "jadval" | "abzats" — where it came from (table | prose)
    tartib: str = ""       # its number in the document
    bet: int = 0

    def toliqmi(self) -> bool:
        return bool(self.matn and self.ijrochi and self.muddat)


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").translate(APOSTROF)).strip()


def jadvaldan(j: Jadval, hujjat_sanasi: str = "") -> list[Topshiriq]:
    """Extracts the action items out of one table."""
    i_matn = j.ustun(*U_MATN)
    i_ijrochi = j.ustun(*U_IJROCHI)
    i_muddat = j.ustun(*U_MUDDAT)
    i_raqam = j.ustun(*U_RAQAM, aniq=True)

    # IS THIS AN ACTION ITEM TABLE? A text column is not enough — a DEADLINE
    # column is required as well.
    #
    # WHY: the definition of an action item comes from the assignment — "every
    # action item, with its DEADLINE and its assignee". A table without a
    # deadline is not an action item table.
    #
    # THE MEASURED REASON: when an unrelated PDF (a Python textbook, 112 pages)
    # was tried, the system found 304 "tables" and manufactured 34 false
    # "action items" out of them — rows of an escape-sequence table ("Keyingi
    # qatorga o'tish", "Qo'ng'iroq"). The cause: that table's "Vazifasi" header
    # matched "vazifa" in U_MATN while no deadline column was required.
    #
    # EVERY action item table in the 6 given documents has a "Muddat" column,
    # so this condition loses no real action items (39/39 are kept).
    if i_matn is None or i_muddat is None:
        return []

    natija = []
    for q in j.qatorlar:
        def katak(i):
            return _norm(q[i]) if i is not None and i < len(q) else ""

        matn = katak(i_matn)
        if not matn:
            continue
        t = Topshiriq(
            matn=matn,
            ijrochi=katak(i_ijrochi),
            muddat=muddat_tahlil(katak(i_muddat), hujjat_sanasi),
            manba="jadval",
            tartib=katak(i_raqam),
            bet=j.bet,
        )
        natija.append(t)
    return natija


# ───────────────────────────── from prose ───────────────────────────────
# The names of organizational units — the main signal for finding the assignee
BOLINMA = re.compile(
    r"\b(bo'lim|boshqarma|departament|laboratoriya|markaz|bo'linma|guruh|"
    r"kotibiyat|inspeksiya|palata|agentlik|komissiya|kengash|vazirlik|"
    r"koordinator|rahbariyat)\w*", re.IGNORECASE)

# The start of a clause: "1." "2." ... at the beginning of a line
BAND = re.compile(r"(?m)^\s*(\d{1,2})\s*\.\s+")

# The action-item verb: in Uzbek official documents it is the imperative-
# optative form "-sin". That is the most reliable signal for an action item in
# prose.
FEL = re.compile(r"\w+(sin|sinlar)\b\s*\.?\s*$", re.IGNORECASE)
# Letters use a different form: "... taqdim etishingizni so'raymiz", "... so'raladi"
XAT_FEL = re.compile(r"so'ra(ymiz|ladi|yman)\b", re.IGNORECASE)

# Splitting into sentences. NOTE: the dots in `01.10.2026` are NOT sentence
# ends, so a LETTER is required before the dot.
JUMLA = re.compile(r"(?<=[a-zа-яʼ'’\)])\.\s+(?=[A-ZА-Я])")

# The signature block — the body is cut off there, otherwise the last clause
# swallows the signature too (a measured bug: 535 characters instead of 140)
IMZO_SATR = re.compile(
    r"\b[A-ZА-Я](?:[a-zа-я]|['’‘ʻ])?\.\s*[A-ZА-Я][a-zа-я'’‘ʻ]{2,}\b")
IMZO_LAVOZIM = ("raisi", "direktor", "boshlig", "rahbar", "o'rinbosar",
                "kotib", "vazir", "hokim", "mudir")

# Clauses that are NOT action items.
# The letter's header (address, phone, post) — not an action item, but the
# introductory sentence inside it ends in "...so'raymiz" and gives a false
# positive
SHAPKA = re.compile(r"Tel\.|E-mail|@\w+\.|\b\d{6}\b|«____»", re.IGNORECASE)
# The introductory sentence: "quyidagi vazifalarni bajarishingizni so'raymiz" —
# that is not an action item, it introduces the list below
KIRISH = re.compile(r"\bquyidagi\s+(vazifa|topshiriq|chora|jadval)", re.IGNORECASE)

NAZORAT = re.compile(r"nazorat\s+qilish.*zimmasiga\s+yuklansin", re.IGNORECASE | re.S)
TASDIQ = re.compile(r"ilovaga\s+muvofiq\s+tasdiqlansin", re.IGNORECASE)
QOIDA = re.compile(r"muddati\s+alohida\s+ko'rsatilmagan", re.IGNORECASE)
ILOVA_ISHORA = re.compile(r"ilovada\s+(belgilangan|ko'rsatilgan)", re.IGNORECASE)


def _turini_aniqla(matn: str) -> str:
    """Is the clause an action item, or something else."""
    if QOIDA.search(matn):
        return "qoida"               # "for items without a stated deadline ..."
    if NAZORAT.search(matn):
        return "nazorat"             # who oversight of the execution falls to
    if TASDIQ.search(matn):
        return "tasdiqlash"          # approving the annex
    if ILOVA_ISHORA.search(matn):
        return "ilova_ishora"        # the items are in the annex — taken from the table
    if FEL.search(matn) or XAT_FEL.search(matn):
        return "topshiriq"
    return "boshqa"


def _ijrochi(matn: str, muddat_boshi: int | None) -> str:
    """Finds the subject of the sentence — the name of an organizational unit.

    THE LOGIC: the assignee stands at the BEGINNING of the sentence and ends
    with the name of a unit:
        "Markazning Tizim tahlili bo'limi amaldagi murojaatlar portalining..."
         └────────── assignee ─────────┘

    Two safeguards:
      1. The text is cut at the DEADLINE — otherwise the second "Kengash" in
         "har chorakda Kengash yig'ilishiga" would be taken as the assignee.
      2. What remains is capped at 85 characters — beyond that it is usually
         the recipient organization ("Agentlikning ... departamentiga").
    """
    bosh = matn[:muddat_boshi] if muddat_boshi else matn
    bosh = bosh[:85]

    # "X bilan birgalikda Y" ("X together with Y") — both units are assignees
    birga = re.search(r"\s+bilan\s+birgalikda\b", bosh, re.IGNORECASE)
    if birga:
        bosh = bosh[:birga.start()]

    moslar = list(BOLINMA.finditer(bosh))
    if not moslar:
        return ""
    # up to the last unit word — i.e. the complete subject phrase
    toliq = _norm(bosh[:moslar[-1].end()])
    if birga and len(moslar) > 1:
        # split in two: a new phrase starts after the previous unit
        kesim = moslar[-2].end()
        return _norm(f"{bosh[:kesim]}, {bosh[kesim:moslar[-1].end()]}")
    return toliq


def _imzogacha(tana: str) -> str:
    """Returns the part that precedes the signature block.

    Otherwise the last clause takes the signature, the clerk and the phone
    number along with it — that was a measured bug.
    """
    satrlar = tana.split("\n")
    for i, s in enumerate(satrlar):
        past = s.lower().translate(APOSTROF)
        if past.strip().startswith("ijrochi"):
            return "\n".join(satrlar[:i])
        if IMZO_SATR.search(s) and any(x in past for x in IMZO_LAVOZIM):
            return "\n".join(satrlar[:i])
    return tana


def _topshiriq_yasa(matn: str, raqam: str, standart, hujjat_sanasi: str,
                    zaxira_ijrochi: str = "") -> Topshiriq:
    mud = muddat_topish(matn, hujjat_sanasi)
    boshi = matn.lower().find(mud.xom.lower()) if mud.xom else None
    if boshi == -1:
        boshi = None
    if not mud and standart:
        mud = Muddat(xom=standart.xom, tur=standart.tur,
                     sana=standart.sana, izoh=standart.izoh)
    ijrochi = _ijrochi(matn, boshi)
    if not ijrochi and zaxira_ijrochi:
        # The sentence names no assignee ("...taqdim etishingizni so'raymiz") —
        # which means it is whoever the letter was addressed to. We do not
        # invent one; we take the recipient from the document's header.
        ijrochi = zaxira_ijrochi
    return Topshiriq(matn=matn, ijrochi=ijrochi, muddat=mud,
                     manba="abzats", tartib=raqam, bet=1)


def abzatsdan(h: Hujjat, hujjat_sanasi: str = "",
              qabul_qiluvchi: str = "") -> list[Topshiriq]:
    """Action items in prose — numbered clauses and unnumbered paragraphs.

    There are two kinds:
      1. A numbered clause:     "1. Markazning Tizim tahlili bo'limi ... etsin."
      2. An unnumbered paragraph: "Shuningdek, ... taqdim etishingizni so'raymiz."

    The second kind only occurs in letters, and ignoring it would be wrong —
    those are action items too, with deadlines, and they have to be carried out.
    """
    tana = _imzogacha(h.betlar[0])
    standart = standart_muddat(tana, hujjat_sanasi)

    bandlar = BAND.split("\n" + tana)
    juftlar = [(bandlar[i], bandlar[i + 1]) for i in range(1, len(bandlar) - 1, 2)]
    oldi = bandlar[0] if bandlar else ""

    natija, qoldiq = [], [oldi]
    for raqam, xom in juftlar:
        # The clause is split into sentences and we stop at the one that ends
        # with an action-item verb — what follows belongs to the subsequent
        # (unnumbered) paragraphs.
        jumlalar = JUMLA.split(_norm(xom))
        yigilgan, tugadi = [], False
        for j in jumlalar:
            if tugadi:
                qoldiq.append(j)
            else:
                yigilgan.append(j)
                tugadi = bool(FEL.search(j) or XAT_FEL.search(j))
        matn = _norm(" ".join(yigilgan))
        if KIRISH.search(matn):          # the sentence introducing the table
            continue
        if len(matn) >= 25 and _turini_aniqla(matn) == "topshiriq":
            natija.append(_topshiriq_yasa(matn, raqam, standart, hujjat_sanasi,
                                          qabul_qiluvchi))

    # The unnumbered paragraphs: "... so'raymiz" / "... so'raladi"
    for bolak in qoldiq:
        for j in JUMLA.split(_norm(bolak)):
            j = _norm(j)
            # An unnumbered paragraph ends in one of two ways:
            #   in letters  "... taqdim etishingizni so'raymiz"
            #   in a decree "... taqdim etilsin"   ← this was missed at first
            if len(j) < 40 or not (XAT_FEL.search(j) or FEL.search(j)):
                continue
            if SHAPKA.search(j) or KIRISH.search(j):
                continue
            tur = _turini_aniqla(j)
            if tur == "topshiriq":
                natija.append(_topshiriq_yasa(j, "", standart, hujjat_sanasi,
                                              qabul_qiluvchi))
            elif tur == "ilova_ishora":
                # "Ilovada ko'rsatilgan topshiriqlar..." is usually just a
                # pointer to the annex. BUT when it carries a deadline of its
                # own, it is a real action item (e.g. an obligation to report
                # monthly).
                mud = muddat_topish(j, hujjat_sanasi)
                if mud:
                    natija.append(_topshiriq_yasa(j, "", standart, hujjat_sanasi,
                                                  qabul_qiluvchi))
    return natija


def hujjatdan(h: Hujjat, hujjat_sanasi: str = "",
              qabul_qiluvchi: str = "") -> list[Topshiriq]:
    """EVERY action item in the document — from the tables and from the prose."""
    natija = []
    for j in h.jadvallar:
        natija += jadvaldan(j, hujjat_sanasi)
    natija += abzatsdan(h, hujjat_sanasi, qabul_qiluvchi)
    return natija


# ─────────────────────────────── CLI ─────────────────────────────────────
TUR_RANG = {
    "absolyut": ch.yashil, "nisbiy": ch.kok, "takrorlanuvchi": ch.sariq,
    "bogliq": ch.sariq, "doimiy": ch.kul, "boshlanish": ch.sariq, "yoq": ch.qizil,
}


def main() -> int:
    from app.services.rekvizit import ajrat as rekvizit_ajrat

    ch.sarlavha("Extracting action items from tables")
    yollar = ([Path(a) for a in sys.argv[1:] if not a.startswith("-")]
              or sorted(c.MATNLI.glob("*.pdf")))
    jami = toliq = 0
    for yol in yollar:
        h = oqi(yol)
        r = rekvizit_ajrat(h)
        ts = hujjatdan(h, r.sana_iso, r.qabul_qiluvchi)
        if not ts:
            continue
        ch.bolim(f"{yol.stem}  ({r.sana_iso})")
        qatorlar = []
        for t in ts:
            rang = TUR_RANG.get(t.muddat.tur, ch.kul)
            qatorlar.append([
                t.tartib or "—",
                t.matn[:38] + ("…" if len(t.matn) > 38 else ""),
                (t.ijrochi[:26] + "…") if len(t.ijrochi) > 26 else (t.ijrochi or "—"),
                rang(t.muddat.tur),
                t.muddat.sana or "—",
            ])
            jami += 1
            toliq += t.toliqmi()
        ch.jadval(["№", "action item", "assignee", "deadline type", "date"], qatorlar)
    print()
    ch.maydon("action items found", jami)
    ch.maydon("all three fields present", f"{toliq}/{jami}", toliq == jami)
    ch.natija(jami > 0, f"{jami} action items extracted")
    return 0


if __name__ == "__main__":
    sys.exit(main())
