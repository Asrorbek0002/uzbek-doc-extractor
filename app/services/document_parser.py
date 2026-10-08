# -*- coding: utf-8 -*-
"""Document analysis — ties every stage together.

    PDF ──read──▶ text + tables
                       │
           ┌───────────┴───────────┐
           ▼                       ▼
       rekvizit               topshiriq
   (the 4 fields)      (text · deadline · assignee)
           └───────────┬───────────┘
                       ▼
                    Natija

The output shape comes straight out of the assignment:
"Letterhead fields: the sending organization, the document number, its date,
the signatory"
"Action items: every action item, with its deadline and its assignee"

Running it:
    python -m app.services.document_parser                    # 6 documents, as a table
    python -m app.services.document_parser --json             # JSON output
    python -m app.services.document_parser <file.pdf>
"""
from __future__ import annotations

import json
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.core import console as ch
from app.core import config as c
from app.services.rekvizit import Rekvizit, ajrat as rekvizit_ajrat
from app.services.topshiriq import Topshiriq, hujjatdan
from app.services.pdf_processor import Hujjat, oqi


@dataclass
class Natija:
    fayl: str = ""
    tur: str = ""                  # xat | qaror (letter | decree)
    betlar: int = 0
    manba: str = "matn"            # matn | ocr (text layer | OCR)
    rekvizitlar: dict = field(default_factory=dict)
    topshiriqlar: list = field(default_factory=list)
    rasmiy_hujjatmi: bool = True   # does it look like an official document
    dalillar: list = field(default_factory=list)   # what that decision rests on

    def jadval_soni(self) -> int:
        return sum(1 for t in self.topshiriqlar if t["manba"] == "jadval")

    def abzats_soni(self) -> int:
        return sum(1 for t in self.topshiriqlar if t["manba"] == "abzats")


def _topshiriq_dict(t: Topshiriq) -> dict:
    return {
        "tartib": t.tartib,
        "matn": t.matn,
        "ijrochi": t.ijrochi,
        "muddat": t.muddat.xom,
        "muddat_turi": t.muddat.tur,
        "muddat_sana": t.muddat.sana,
        "muddat_izoh": t.muddat.izoh,
        "manba": t.manba,
        "bet": t.bet,
    }


def _rasmiy_hujjatmi(r: Rekvizit, ts: list) -> tuple[bool, list[str]]:
    """Does the document look like an official letter/decree — judged by evidence.

    WHY IT IS NEEDED: the rules are fitted to the structure of official
    documents. Handed an unrelated PDF, the system must not stay SILENT and
    report something wrong.

    MEASURED: given a 112-page Python textbook, it returned the book's title
    ("PYTHON ASOSLARI | ABBOSBEK IBRAGIMOV") as the "organization" — because
    `rekvizit.py` treats an uppercase line as the organization, and a book
    title is written in uppercase.

    The evidence — nearly always present in an official document, and absent in
    a book or a CV:
        · a document number (№ 07-04/2219)
        · a document date
        · at least one action item (with a deadline)

    Two of them are enough. All three are present in the 6 given documents.
    """
    dalillar = []
    if r.raqam:
        dalillar.append("hujjat raqami topildi")
    if r.sana:
        dalillar.append("hujjat sanasi topildi")
    if ts:
        dalillar.append(f"{len(ts)} ta topshiriq topildi")
    return len(dalillar) >= 2, dalillar


def tahlil(yol: str | Path, h: Hujjat | None = None) -> Natija:
    """Analyses the PDF and returns the letterhead fields and the action items."""
    h = h or oqi(yol)
    r = rekvizit_ajrat(h)
    ts = hujjatdan(h, r.sana_iso, r.qabul_qiluvchi)
    rasmiy, dalillar = _rasmiy_hujjatmi(r, ts)
    return Natija(
        rasmiy_hujjatmi=rasmiy,
        dalillar=dalillar,
        fayl=Path(yol).name,
        tur=r.tur,
        betlar=len(h.betlar),
        manba="ocr" if h.skanermi else "matn",
        rekvizitlar={
            # the 4 fields the assignment asks for
            "tashkilot": r.tashkilot,
            "raqam": r.raqam,
            "sana": r.sana,
            "imzolagan": r.imzolagan,
            # extras — useful, but not required
            "sana_iso": r.sana_iso,
            "lavozim": r.lavozim,
            "qabul_qiluvchi": r.qabul_qiluvchi,
            "ijrochi_kontakt": r.ijrochi,
        },
        topshiriqlar=[_topshiriq_dict(t) for t in ts],
    )


# ─────────────────────────────── CLI ─────────────────────────────────────
TUR_RANG = {
    "absolyut": ch.yashil, "nisbiy": ch.kok, "takrorlanuvchi": ch.sariq,
    "bogliq": ch.sariq, "doimiy": ch.kul, "boshlanish": ch.sariq, "yoq": ch.qizil,
}


def korsat(n: Natija) -> None:
    ch.bolim(f"{n.fayl}   ({n.tur}, {n.betlar} pages, {n.manba})")
    r = n.rekvizitlar
    ch.maydon("organization", r["tashkilot"][:54])
    ch.maydon("number", r["raqam"])
    ch.maydon("date", f"{r['sana']}  →  {r['sana_iso']}")
    ch.maydon("signatory", f"{r['imzolagan']}" + (f"  ({r['lavozim']})" if r["lavozim"] else ""))
    if r["qabul_qiluvchi"]:
        ch.maydon("recipient", r["qabul_qiluvchi"][:54])
    print()
    ch.jadval(
        ["№", "action item", "assignee", "deadline", "type", "date"],
        [[t["tartib"] or "—",
          t["matn"][:34] + ("…" if len(t["matn"]) > 34 else ""),
          (t["ijrochi"][:22] + "…") if len(t["ijrochi"]) > 22 else t["ijrochi"],
          (t["muddat"][:18] + "…") if len(t["muddat"]) > 18 else (t["muddat"] or "—"),
          TUR_RANG.get(t["muddat_turi"], ch.kul)(t["muddat_turi"]),
          t["muddat_sana"] or "—"]
         for t in n.topshiriqlar],
    )
    ch.eslatma(f"{len(n.topshiriqlar)} action items in total "
               f"({n.jadval_soni()} from tables, {n.abzats_soni()} from prose)")


def main() -> int:
    yollar = ([Path(a) for a in sys.argv[1:] if not a.startswith("-")]
              or sorted(c.MATNLI.glob("*.pdf")))
    natijalar = [tahlil(y) for y in yollar]

    if "--json" in sys.argv:
        print(json.dumps([asdict(n) for n in natijalar], ensure_ascii=False, indent=1))
        return 0

    ch.sarlavha("Document analysis")
    for n in natijalar:
        korsat(n)

    # The results are saved to a file as well — the assignment asks for "the
    # results for the given documents"
    c.NATIJA_DIR.mkdir(parents=True, exist_ok=True)
    yol = c.NATIJA_DIR / "natijalar.json"
    yol.write_text(json.dumps([asdict(n) for n in natijalar],
                              ensure_ascii=False, indent=1), encoding="utf-8")
    print()
    jami = sum(len(n.topshiriqlar) for n in natijalar)
    ch.maydon("documents", len(natijalar))
    ch.maydon("action items", jami)
    ch.natija(True, f"saved → {yol.relative_to(c.ILDIZ)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
