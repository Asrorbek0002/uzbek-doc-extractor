# -*- coding: utf-8 -*-
"""Measuring accuracy — compares the system's output against the hand-written gold set.

FROM THE ASSIGNMENT: "a short report: which method was chosen, HOW ACCURATE IT
IS, WHERE IT FAILS". This script answers the second and third of those.

WHAT IS MEASURED

    Letterhead fields  4 fields × 6 documents = 24 values, each checked separately
    Action items       were they found (recall) · nothing extra (precision)
                       and among those found: assignee · deadline type · date

MATCHING: the gold set stores a unique FRAGMENT, not the full text. The system
may cut the text slightly differently, but the fragment will still be inside it.

Running it:
    python -m tests.test_aniqlik
    python -m tests.test_aniqlik --skaner
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core import console as ch
from app.core import config as c
from app.services.document_parser import tahlil
from tests.etalon import ETALON

APOSTROF = str.maketrans({"’": "'", "‘": "'", "ʻ": "'", "ʼ": "'", "`": "'",
                          "“": '"', "”": '"'})


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").translate(APOSTROF)).strip().lower()


def _ichidami(bolak: str, matn: str) -> bool:
    return _norm(bolak) in _norm(matn)


# ─────────────────────────── letterhead fields ───────────────────────────
def rekvizit_bahola(natijalar: dict) -> tuple[int, int, list]:
    togri = jami = 0
    xatolar = []
    for fayl, kutilgan in ETALON.items():
        r = natijalar[fayl].rekvizitlar
        for maydon in ("tashkilot", "raqam", "sana_iso", "imzolagan"):
            jami += 1
            k, olingan = kutilgan[maydon], r.get(maydon, "")
            # the organization name is long — a fragment match is enough
            mos = (_ichidami(k, olingan) if maydon == "tashkilot"
                   else _norm(k) == _norm(olingan))
            if mos:
                togri += 1
            else:
                xatolar.append((fayl, maydon, k, olingan))
    return togri, jami, xatolar


# ─────────────────────────── action items ────────────────────────────────
def topshiriq_bahola(natijalar: dict):
    topildi = qoldirilgan = ortiqcha = 0
    ijrochi_togri = tur_togri = sana_togri = 0
    xatolar = []

    for fayl, kutilgan in ETALON.items():
        olingan = list(natijalar[fayl].topshiriqlar)
        ishlatilgan = set()

        for bolak, e_ijrochi, e_tur, e_sana in kutilgan["topshiriqlar"]:
            mos = None
            for i, t in enumerate(olingan):
                if i in ishlatilgan:
                    continue
                if _ichidami(bolak, t["matn"]):
                    mos, ishlatilgan = t, ishlatilgan | {i}
                    break
            if mos is None:
                qoldirilgan += 1
                xatolar.append((fayl, "missed", bolak, "—"))
                continue

            topildi += 1
            if not e_ijrochi or _ichidami(e_ijrochi, mos["ijrochi"]):
                ijrochi_togri += 1
            else:
                xatolar.append((fayl, "assignee", e_ijrochi, mos["ijrochi"]))
            if mos["muddat_turi"] == e_tur:
                tur_togri += 1
            else:
                xatolar.append((fayl, "deadline type", e_tur, mos["muddat_turi"]))
            if mos["muddat_sana"] == e_sana:
                sana_togri += 1
            else:
                xatolar.append((fayl, "deadline date", e_sana or "—",
                                mos["muddat_sana"] or "—"))

        for i, t in enumerate(olingan):
            if i not in ishlatilgan:
                ortiqcha += 1
                xatolar.append((fayl, "spurious", "—", t["matn"][:48]))

    return {
        "topildi": topildi, "qoldirilgan": qoldirilgan, "ortiqcha": ortiqcha,
        "ijrochi_togri": ijrochi_togri, "tur_togri": tur_togri,
        "sana_togri": sana_togri, "xatolar": xatolar,
    }


def _foiz(a: int, b: int) -> str:
    return f"{a / b * 100:.1f}%" if b else "—"


def _yol(fayl: str, skaner: bool) -> Path:
    """A gold-set key (the digital file's name) -> the actual path.

    The gold set was written BY HAND against the digital PDFs, and the scans
    are of those very same documents (`..._skaner.pdf`). That is what lets ONE
    gold set evaluate both collections — and show directly how much accuracy
    the scans cost.
    """
    if not skaner:
        return c.MATNLI / fayl
    return c.SKANER / f"{Path(fayl).stem}_skaner.pdf"


def main() -> int:
    skaner = "--skaner" in sys.argv
    ch.sarlavha("Measuring accuracy — against the gold set"
                + ("  ·  SCANS (OCR)" if skaner else "  ·  DIGITAL PDF"))
    natijalar = {f: tahlil(_yol(f, skaner)) for f in ETALON}

    # ── letterhead fields ──
    r_togri, r_jami, r_xato = rekvizit_bahola(natijalar)
    ch.bolim("Letterhead fields")
    ch.jadval(
        ["field", "correct", "total", "accuracy"],
        [[m,
          sum(1 for f in ETALON
              if not any(x[0] == f and x[1] == m for x in r_xato)),
          len(ETALON),
          _foiz(sum(1 for f in ETALON
                    if not any(x[0] == f and x[1] == m for x in r_xato)), len(ETALON))]
         for m in ("tashkilot", "raqam", "sana_iso", "imzolagan")],
        ongga={1, 2, 3},
    )
    print()
    ch.maydon("total", f"{r_togri}/{r_jami}", r_togri == r_jami, izoh=_foiz(r_togri, r_jami))

    # ── action items ──
    t = topshiriq_bahola(natijalar)
    etalon_soni = sum(len(d["topshiriqlar"]) for d in ETALON.values())
    tizim_soni = sum(len(n.topshiriqlar) for n in natijalar.values())
    recall = t["topildi"] / etalon_soni
    precision = t["topildi"] / tizim_soni if tizim_soni else 0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0

    ch.bolim("Finding the action items")
    ch.jadval(
        ["metric", "value", "note"],
        [["in the gold set", etalon_soni, "counted by hand"],
         ["the system found", tizim_soni, ""],
         ["correctly found", t["topildi"], ""],
         ["missed", t["qoldirilgan"], "never found"],
         ["spurious", t["ortiqcha"], "not an action item, but was taken as one"],
         ["recall", _foiz(t["topildi"], etalon_soni), "how much of the gold set was found"],
         ["precision", _foiz(t["topildi"], tizim_soni), "how many of the hits are right"],
         ["F1", f"{f1 * 100:.1f}%", ""]],
        ongga={1},
    )

    ch.bolim("The fields of the action items that were found")
    ch.jadval(
        ["field", "correct", "total", "accuracy"],
        [["assignee", t["ijrochi_togri"], t["topildi"], _foiz(t["ijrochi_togri"], t["topildi"])],
         ["deadline type", t["tur_togri"], t["topildi"], _foiz(t["tur_togri"], t["topildi"])],
         ["deadline date", t["sana_togri"], t["topildi"], _foiz(t["sana_togri"], t["topildi"])]],
        ongga={1, 2, 3},
    )

    # ── the failures ──
    hamma_xato = r_xato + t["xatolar"]
    if hamma_xato:
        ch.bolim(f"Failures — {len(hamma_xato)}")
        ch.jadval(
            ["document", "what", "expected", "got"],
            [[f.replace(".pdf", "")[:22], tur, str(k)[:30], str(o)[:30]]
             for f, tur, k, o in hamma_xato],
        )

    natija = {
        "rekvizitlar": {"togri": r_togri, "jami": r_jami, "aniqlik": r_togri / r_jami},
        "topshiriqlar": {k: v for k, v in t.items() if k != "xatolar"},
        "recall": recall, "precision": precision, "f1": f1,
        "xatolar": [{"hujjat": f, "nima": n, "kutilgan": k, "olingan": o}
                    for f, n, k, o in hamma_xato],
    }
    c.NATIJA_DIR.mkdir(parents=True, exist_ok=True)
    # The two collections' results must not overwrite each other — the digital
    # and the scanned measurements should sit side by side and show the gap.
    yol = c.NATIJA_DIR / ("baholash_skaner.json" if skaner else "baholash_matnli.json")
    yol.write_text(json.dumps(natija, ensure_ascii=False, indent=1), encoding="utf-8")
    ch.natija(True, f"saved → {yol.relative_to(c.ILDIZ)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
