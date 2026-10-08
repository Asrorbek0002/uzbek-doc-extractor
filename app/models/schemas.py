# -*- coding: utf-8 -*-
"""API response schemas.

The shape comes straight out of the assignment:

    "Letterhead fields: sending organization, document number, date, signatory"
    "Action items: each item, with its deadline and its assignee"

That is why `Rekvizitlar` lists the 4 REQUESTED fields first and the extra ones
after. The extras are not required, but they help when reviewing the output.
"""
from __future__ import annotations

from pydantic import BaseModel, Field, model_validator


class Rekvizitlar(BaseModel):
    """The document's letterhead fields."""

    # ── the 4 fields the assignment asks for ──
    tashkilot: str = Field("", description="the sending organization")
    raqam: str = Field("", description="the document number")
    sana: str = Field("", description="the document date — exactly as written in it")
    imzolagan: str = Field("", description="the signatory")

    # ── extras ──
    sana_iso: str = Field("", description="the date in ISO format (YYYY-MM-DD)")
    lavozim: str = Field("", description="the signatory's position")
    qabul_qiluvchi: str = Field("", description="who it was sent to")
    ijrochi_kontakt: str = Field("", description="the clerk/phone line at the end of the document")


class Muddat(BaseModel):
    """An action item's deadline.

    IMPORTANT: a deadline is never FORCED into a single date. "within 10 days
    after the prototype is ready" is not a date, it is a condition. Hence the
    `tur` ("type") field, and `sana` is only filled in when a date can actually
    be computed.
    """

    xom: str = Field("", description="exactly as written in the document")
    tur: str = Field("yoq", description=(
        "absolyut · nisbiy · takrorlanuvchi · bogliq · doimiy · boshlanish · yoq"))
    sana: str = Field("", description="the ISO date — only for absolyut and nisbiy")
    izoh: str = Field("", description="why it was interpreted that way")


class Topshiriq(BaseModel):
    """One action item — its text, its assignee and its deadline."""

    @model_validator(mode="before")
    @classmethod
    def _muddatni_yig(cls, qiymat):
        """Turns the pipeline's FLAT shape into the API's NESTED shape.

        `document_parser` produces the deadline flat (`muddat`, `muddat_turi`,
        `muddat_sana`, `muddat_izoh`) — that shape is what `tests/etalon.py`
        and `natijalar.json` use, so it is not changed. In the API, however, a
        deadline reads more clearly as a single object, because the assignment
        words it together: "each action item, with its deadline and its
        assignee".
        """
        if not isinstance(qiymat, dict) or isinstance(qiymat.get("muddat"), dict):
            return qiymat
        q = dict(qiymat)
        q["muddat"] = {
            "xom": q.get("muddat") or "",
            "tur": q.pop("muddat_turi", None) or "yoq",
            "sana": q.pop("muddat_sana", None) or "",
            "izoh": q.pop("muddat_izoh", None) or "",
        }
        return q

    tartib: str = Field("", description="the item number in the document (if any)")
    matn: str
    ijrochi: str = ""
    muddat: Muddat
    manba: str = Field("", description="jadval | abzats — where it came from (table | prose)")
    bet: int = 0


class Natija(BaseModel):
    """The complete result of analysing one document."""

    fayl: str
    tur: str = Field("", description="xat | qaror (letter | decree)")
    betlar: int = 0
    manba: str = Field("matn", description=(
        "matn — the PDF has a text layer; ocr — a scan, Tesseract was used"))
    rekvizitlar: Rekvizitlar
    topshiriqlar: list[Topshiriq] = []
    rasmiy_hujjatmi: bool = Field(True, description=(
        "whether the document looks like an official letter/decree. If False, "
        "the result should not be trusted — the rules are fitted to the "
        "structure of official documents"))
    dalillar: list[str] = Field([], description=(
        "what that decision rests on: the document number · its date · the action items"))
    vaqt_ms: int = 0


class Namuna(BaseModel):
    """A sample document shipped with the project."""

    nom: str
    tur: str = Field("", description="matnli | skaner (digital | scanned)")
    olcham_kb: int = 0


class Salomatlik(BaseModel):
    """System health — whether every dependency is in place."""

    holat: str = Field("", description="tayyor | nosoz (ready | broken)")
    pdf_oqish: bool = False
    ocr: bool = False
    ocr_izoh: str = ""
    ocr_tillari: list[str] = []
    namunalar: int = 0


class Xato(BaseModel):
    """An error response — with a message the user can understand."""

    xato: str
    izoh: str = ""
