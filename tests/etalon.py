# -*- coding: utf-8 -*-
"""THE GOLD SET — all six documents read by hand, with the correct answers.

WHY IT IS NEEDED: a number like "38 action items found" proves nothing — it
may be too many, it may be too few. Knowing the real accuracy requires the
CORRECT answer, and that can only be written by hand.

For each action item a unique FRAGMENT of its text is recorded (not the whole
text) — the system may cut the text slightly differently, but the fragment will
still be inside it. The matching goes by that fragment.

DECISIONS (why some clauses are NOT in the gold set):
  • "Mazkur qaror ijrosini nazorat qilish ... zimmasiga yuklansin" — not an
    action item; it states who oversight falls to.
  • "... chora-tadbirlar rejasi ilovaga muvofiq tasdiqlansin" — an act of
    approval; the action items are in the annex.
  • "Ilovada belgilangan topshiriqlar ... ijro etilishi ta'minlansin" — a
    pointer to the annex, with no deadline of its own.
  • "quyidagi topshiriqlar belgilansin:" — introduces the table.

The gold data itself stays in Uzbek: these are fragments of the Uzbek
documents.
"""

# file -> {letterhead field: ..., topshiriqlar: [(fragment, assignee fragment, deadline type, date)]}
ETALON = {
    "NAMUNA_1_abzats.pdf": {
        "tashkilot": "HUQUQIY XIZMATLARNI RAQAMLASHTIRISH MILLIY AGENTLIGI",
        "raqam": "121",
        "sana_iso": "2026-02-10",
        "imzolagan": "M. Tursunov",
        "topshiriqlar": [
            ("hujjat loyihasini", "Ro'yxatga olish departamenti", "nisbiy", "2026-03-10"),
            ("integratsiyasini", "Axborot texnologiyalari boshqarmasi", "absolyut", "2026-07-01"),
            ("avtomatik tekshirish modulini", "Huquqiy ekspertiza boshqarmasi", "nisbiy", "2026-03-10"),
            ("amaliy qo'llanmani tarqatish", "Hududiy bo'linmalar", "boshlanish", "2026-03-15"),
            ("har oyda", "Ro'yxatga olish departamenti", "takrorlanuvchi", ""),
        ],
    },
    "NAMUNA_2_jadval.pdf": {
        "tashkilot": "YURIDIK XIZMATLAR SIFATINI OSHIRISH RESPUBLIKA KOMISSIYASINING",
        "raqam": "145",
        "sana_iso": "2026-02-24",
        "imzolagan": "O. Saidov",
        "topshiriqlar": [
            ("Murojaatlarni avtomatik tasniflash", "Axborot texnologiyalari", "absolyut", "2026-05-01"),
            ("chatbotini ishga tushirish", "Axborot texnologiyalari", "absolyut", "2026-06-15"),
            ("avtomatik taqsimlash tizimini", "Ish yuritish", "bogliq", ""),
            ("o'quv seminarlarini", "Kadrlar boshqarmasi", "takrorlanuvchi", ""),
            ("xavfsizligi talablariga", "Axborot xavfsizligi", "absolyut", "2026-04-20"),
            ("har chorak yakunidan", "Axborot texnologiyalari boshqarmasi", "takrorlanuvchi", ""),
        ],
    },
    "NAMUNA_3_ilova.pdf": {
        "tashkilot": "NOTARIAT VA FHDYO FAOLIYATINI MUVOFIQLASHTIRISH",
        "raqam": "160",
        "sana_iso": "2026-03-05",
        "imzolagan": "G. Nazarova",
        "topshiriqlar": [
            ("elektron qayd etish modulini", "Notariat boshqarmasi", "absolyut", "2026-06-01"),
            ("raqamli arxivga", "FHDYo boshqarmasi", "absolyut", "2026-08-01"),
            ("tizimlararo almashish", "Axborot texnologiyalari", "bogliq", ""),
            ("xodimlarini yangi tizimda", "Kadrlar boshqarmasi", "absolyut", "2026-05-15"),
            ("qo'llanma va axborot materiallarini", "Axborot xizmati", "nisbiy", "2026-04-05"),
            ("ilova ijrosi to'g'risida", "Kengash kotibiyati", "takrorlanuvchi", ""),
        ],
    },
    "xat_1_abzatsdagi_topshiriqlar.pdf": {
        "tashkilot": "RAQAMLI HUQUQIY XIZMATLAR AGENTLIGI",
        "raqam": "03-12/1456",
        "sana_iso": "2026-09-08",
        "imzolagan": "Sh. Qodirov",
        "topshiriqlar": [
            ("funksional imkoniyatlarini tahlil", "Tizim tahlili bo'limi", "absolyut", "2026-09-20"),
            ("avtomatik tasniflash imkoniyatini", "Sun'iy intellekt laboratoriyasi", "absolyut", "2026-10-01"),
            ("himoya qilish bo'yicha takliflarni", "Axborot xavfsizligi bo'limi", "nisbiy", "2026-09-18"),
            ("virtual yordamchining", "Dasturiy ta'minotni ishlab chiqish", "absolyut", "2026-10-25"),
            ("ijrosi holati to'g'risida", "Markaz", "takrorlanuvchi", ""),
            ("umumlashtirilgan hisobot", "", "absolyut", "2026-11-05"),
            ("mas'ul xodimlar to'g'risidagi", "", "nisbiy", "2026-09-11"),
        ],
    },
    "xat_2_jadvaldagi_topshiriqlar.pdf": {
        "tashkilot": "YANGI AVLOD RAQAMLI YECHIMLAR",
        "raqam": "15/2-784",
        "sana_iso": "2026-09-11",
        "imzolagan": "A. Yusupov",
        "topshiriqlar": [
            ("klassifikatorlarni", "Tizim tahlili bo'limi", "absolyut", "2026-09-18"),
            ("prototip ishlab chiqish", "Sun'iy intellekt", "absolyut", "2026-09-30"),
            ("vakolatlar va tashkiliy tuzilma", "Biznes-tahlil", "absolyut", "2026-10-05"),
            ("integratsiyasi bo'yicha texnik talablarni", "Integratsiya bo'limi", "bogliq", ""),
            ("natijalarini baholash", "Loyiha guruhi", "absolyut", "2026-11-01"),
            ("qisqacha ma'lumot taqdim etish", "Loyiha koordinatori", "takrorlanuvchi", ""),
            # The paragraph after the table — no deadline, but an action item:
            ("umumlashtirilgan ma'lumot loyiha koordinatori", "", "yoq", ""),
        ],
    },
    "xat_3_ilovadagi_topshiriqlar.pdf": {
        "tashkilot": "MA'LUMOTLAR XAVFSIZLIGI VA INTEGRATSIYA AGENTLIGI",
        "raqam": "07-04/2219",
        "sana_iso": "2026-09-15",
        "imzolagan": "D. Ergasheva",
        "topshiriqlar": [
            ("qo'llash mumkin bo'lgan jarayonlarni", "Tizim tahlili bo'limi", "absolyut", "2026-09-20"),
            ("manbalarini inventarizatsiya", "Ma'lumotlar bazalarini", "absolyut", "2026-09-30"),
            ("atributlarini ajratish modulining", "Sun'iy intellekt laboratoriyasi", "absolyut", "2026-10-15"),
            ("vakolatlari bazasini shakllantirish", "Biznes-tahlil bo'limi", "absolyut", "2026-10-25"),
            ("muvofiqligini tekshirish", "Axborot xavfsizligi bo'limi", "bogliq", ""),
            ("keyingi joriy etish bosqichi", "Loyiha guruhi", "absolyut", "2026-11-10"),
            ("yangi modullar bilan ishlashga", "Kadrlar bo'limi", "doimiy", ""),
            ("ijro holati to'g'risida", "", "takrorlanuvchi", ""),
        ],
    },
}


def jami_topshiriq() -> int:
    return sum(len(d["topshiriqlar"]) for d in ETALON.values())
