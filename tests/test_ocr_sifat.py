# -*- coding: utf-8 -*-
"""OCR quality — CER / WER and table cell accuracy.

    CER = character error rate = levenshtein(truth, ocr) / len(truth)
    WER = word error rate      = levenshtein(truth_words, ocr_words) / word count

THE GROUND TRUTH COMES FREE: every document exists in two versions — a digital
PDF and a scan of it. The digital PDF's text layer *is* the correct text, so no
ground truth has to be written by hand.

IMPORTANT — WHAT IS COMPARED WITH WHAT

    The pipeline splits the text into TWO STREAMS: the prose and the table
    cells. On the digital path pdfplumber cuts the table area out with
    `outside_bbox`; the OCR path does exactly the same. Therefore:

        prose text  ->  against the digital PDF's text WITHOUT the table
        table cell  ->  against the digital PDF's cell

    At first `pdftotext -layout` (WITH the table) was used as the ground truth,
    and because the OCR side had no table the CER came out at 31% — that was
    not quality, it was a MEASUREMENT ERROR. Both sides have to rest on the
    same basis.

Running it:
    python -m tests.test_ocr_sifat
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core import console as ch
from app.core import config as c
from app.services.pdf_processor import Jadval, oqi

# These thresholds are a REGRESSION SIGNAL, not an acceptance criterion.
#
# The real acceptance criterion lives in `tests/test_aniqlik.py`: the accuracy
# of the letterhead fields and the action items. The numbers here only answer
# the question "has OCR quality dropped?".
CER_CHEGARA = 0.05          # 5% — the usual "good" threshold for OCR
WER_CHEGARA = 0.10          # WER always runs ~3x above CER: one wrong
                            # character makes the whole word wrong
KATAK_CHEGARA = 0.85        # the share of cells that match exactly


def _norm(s: str) -> str:
    """Normalization for comparison.

    The apostrophe variants (`'` `’` `‘` `ʻ` `ʼ`) are folded into one: the
    difference between them is a font matter, not an OCR error. Whitespace is
    normalized too — where a line breaks does not affect the content.
    """
    s = re.sub(r"[‘’ʻʼ`´]", "'", s or "")
    return re.sub(r"\s+", " ", s).strip()


def levenshtein(a: str, b: str) -> int:
    """Character-level edit distance (O(len(a)) memory)."""
    if a == b:
        return 0
    if not a or not b:
        return len(a) or len(b)
    oldingi = list(range(len(b) + 1))
    for i, belgi_a in enumerate(a, 1):
        hozirgi = [i]
        for j, belgi_b in enumerate(b, 1):
            hozirgi.append(min(
                oldingi[j] + 1,                          # deletion
                hozirgi[j - 1] + 1,                      # insertion
                oldingi[j - 1] + (belgi_a != belgi_b),   # substitution
            ))
        oldingi = hozirgi
    return oldingi[-1]


def _soz_masofa(a: list[str], b: list[str]) -> int:
    """Word-level edit distance — for WER."""
    if a == b:
        return 0
    oldingi = list(range(len(b) + 1))
    for i, x in enumerate(a, 1):
        hozirgi = [i]
        for j, y in enumerate(b, 1):
            hozirgi.append(min(oldingi[j] + 1, hozirgi[j - 1] + 1,
                               oldingi[j - 1] + (x != y)))
        oldingi = hozirgi
    return oldingi[-1]


def _kataklar(jadvallar: list[Jadval]) -> list[list[str]]:
    """Collects the rows of every table into one list."""
    return [q for j in jadvallar for q in j.qatorlar]


# ─────────────────────────── the prose text ──────────────────────────────
def abzats_sifati() -> tuple[list[list], dict]:
    qatorlar, jami_xato, jami_belgi, jami_soz_xato, jami_soz = [], 0, 0, 0, 0
    yozuvlar = []
    for matnli, skaner in c.JUFTLIKLAR:
        etalon = _norm(oqi(c.MATNLI / f"{matnli}.pdf").matn)
        olingan = _norm(oqi(c.SKANER / f"{skaner}.pdf").matn)

        xato = levenshtein(etalon, olingan)
        cer = xato / max(len(etalon), 1)
        e_soz, o_soz = etalon.split(), olingan.split()
        soz_xato = _soz_masofa(e_soz, o_soz)
        wer = soz_xato / max(len(e_soz), 1)

        jami_xato += xato
        jami_belgi += len(etalon)
        jami_soz_xato += soz_xato
        jami_soz += len(e_soz)

        qatorlar.append([matnli[:28], f"{len(etalon):,}", f"{cer * 100:.2f}%",
                         f"{wer * 100:.2f}%",
                         ch.yashil("✓") if cer <= CER_CHEGARA else ch.qizil("✗")])
        yozuvlar.append({"hujjat": matnli, "belgilar": len(etalon),
                         "cer": round(cer, 4), "wer": round(wer, 4)})

    return qatorlar, {
        "hujjatlar": yozuvlar,
        "umumiy_cer": round(jami_xato / max(jami_belgi, 1), 4),
        "umumiy_wer": round(jami_soz_xato / max(jami_soz, 1), 4),
    }


# ─────────────────────────── the table cells ─────────────────────────────
def jadval_sifati() -> tuple[list[list], dict]:
    qatorlar, yozuvlar = [], []
    jami_katak = jami_aynan = jami_xato = jami_belgi = 0

    for matnli, skaner in c.JUFTLIKLAR:
        e_qatorlar = _kataklar(oqi(c.MATNLI / f"{matnli}.pdf").jadvallar)
        o_qatorlar = _kataklar(oqi(c.SKANER / f"{skaner}.pdf").jadvallar)
        if not e_qatorlar and not o_qatorlar:
            continue                                  # a prose document

        aynan = katak = xato = belgi = 0
        for e_q, o_q in zip(e_qatorlar, o_qatorlar):
            for e_k, o_k in zip(e_q, o_q):
                e_k, o_k = _norm(e_k), _norm(o_k)
                if not e_k:
                    continue
                katak += 1
                aynan += e_k == o_k
                xato += levenshtein(e_k, o_k)
                belgi += len(e_k)

        qator_mos = len(e_qatorlar) == len(o_qatorlar)
        cer = xato / max(belgi, 1)
        nisbat = aynan / max(katak, 1)
        jami_katak += katak
        jami_aynan += aynan
        jami_xato += xato
        jami_belgi += belgi

        qatorlar.append([
            matnli[:28],
            f"{len(e_qatorlar)} / {len(o_qatorlar)}",
            f"{aynan}/{katak}",
            f"{nisbat * 100:.1f}%",
            f"{cer * 100:.2f}%",
            ch.yashil("✓") if qator_mos and nisbat >= KATAK_CHEGARA else ch.qizil("✗"),
        ])
        yozuvlar.append({"hujjat": matnli, "qator_etalon": len(e_qatorlar),
                         "qator_ocr": len(o_qatorlar), "kataklar": katak,
                         "aynan": aynan, "cer": round(cer, 4)})

    return qatorlar, {
        "hujjatlar": yozuvlar,
        "aynan_nisbat": round(jami_aynan / max(jami_katak, 1), 4),
        "umumiy_cer": round(jami_xato / max(jami_belgi, 1), 4),
    }


# ─────────────────────────────── CLI ─────────────────────────────────────
def main() -> int:
    ch.sarlavha("OCR quality — CER, WER and the table cells")
    ch.maydon("language", c.OCR_TIL)
    ch.maydon("dpi", c.OCR_DPI)
    ch.eslatma("ground truth: the digital PDF version of the same document")
    ch.eslatma("prose and tables are measured SEPARATELY — the pipeline separates them too")

    ch.bolim("Prose text")
    a_qatorlar, abzats = abzats_sifati()
    ch.jadval(["document", "truth chars", "CER", "WER", ""], a_qatorlar,
              ongga={1, 2, 3})
    print()
    ch.maydon("overall CER", f"{abzats['umumiy_cer'] * 100:.2f}%",
              abzats["umumiy_cer"] <= CER_CHEGARA, izoh="character errors")
    ch.maydon("overall WER", f"{abzats['umumiy_wer'] * 100:.2f}%",
              abzats["umumiy_wer"] <= WER_CHEGARA, izoh="word errors")

    ch.bolim("Table cells")
    j_qatorlar, jadval = jadval_sifati()
    ch.jadval(["document", "rows truth/ocr", "exact", "exact %", "CER", ""],
              j_qatorlar, ongga={1, 2, 3, 4})
    print()
    ch.maydon("cells matching exactly", f"{jadval['aynan_nisbat'] * 100:.1f}%",
              jadval["aynan_nisbat"] >= KATAK_CHEGARA)
    ch.maydon("cell CER", f"{jadval['umumiy_cer'] * 100:.2f}%",
              jadval["umumiy_cer"] <= CER_CHEGARA)

    natija = {"til": c.OCR_TIL, "dpi": c.OCR_DPI,
              "abzats": abzats, "jadval": jadval}
    c.NATIJA_DIR.mkdir(parents=True, exist_ok=True)
    yol = c.NATIJA_DIR / "ocr_sifat.json"
    yol.write_text(json.dumps(natija, ensure_ascii=False, indent=1), encoding="utf-8")
    print()
    ch.natija(True, f"saved → {yol.relative_to(c.ILDIZ)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
