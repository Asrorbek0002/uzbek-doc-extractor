<div align="center">

# Extracting letterhead fields and action items from PDF documents

**Digital and scanned** · **no cloud** · measured accuracy: **100%** (on both sets)

</div>

> This is the **second** of two assignments. The first one:
> [**uzbek-semantic-qa**](https://github.com/<github-nomi>/uzbek-semantic-qa) —
> an Uzbek-language semantic question answering system.

---

## What it does

Given an official document (a letter or a decree) as a PDF, it extracts two
things:

| | |
|:--|:--|
| **Letterhead fields** (`rekvizit`) | sending organization · document number · date · signatory |
| **Action items** (`topshiriq`) | the text of each item · its **deadline** · its **assignee** |

Action items appear in three different places in these documents, and all three
are supported: in free-form paragraphs, in numbered clauses, and in **tables**
(including the table of an annex).

> [!IMPORTANT]
> **The constraint is satisfied:** documents are **never** sent to external
> cloud services. The whole pipeline is local — `pdfplumber`, `Tesseract` and
> rules. No external API is called, so the system works fully offline.

---

## Quick start

```bash
# 1) system packages (once)
sudo apt install -y tesseract-ocr tesseract-ocr-uzb poppler-utils

# 2) environment
git clone https://github.com/<github-nomi>/uzbek-doc-extractor.git
cd uzbek-doc-extractor
python3 -m venv venv && venv/bin/pip install -r requirements.txt

# 3) web interface
venv/bin/uvicorn app.main:app --reload
#    -> http://127.0.0.1:8000        upload a PDF and press "Tahlil qilish" (Analyze)
#    -> http://127.0.0.1:8000/docs   API documentation (Swagger)
```

From the terminal:

```bash
venv/bin/python -m app.services.document_parser          # 6 documents, as a table
venv/bin/python -m app.services.document_parser --json   # JSON
venv/bin/python -m app.services.document_parser <file.pdf>
```

---

## Web interface

The flow asked for in the assignment: **upload a PDF → "Analyze" → the list of
letterhead fields and action items**.

- pick a file or **drag & drop** it
- the **12 samples** shipped with the project can be selected from a list — to
  try it without uploading anything
- for a scanned document it warns that OCR will take 20-40 s
- every action item carries a colored **deadline type** label: green — an exact
  date, blue — computed, yellow — conditional/recurring, red — no deadline
- no external CDN, a single HTML file — it works without internet

---

## Architecture

```
                              PDF
                               │
                  ┌────────────┴────────────┐
            Digital PDF                Scanned PDF
                  │                          │
            pdfplumber                pdftoppm 300 dpi
          text + tables                      │
         (by ruling lines)            tesseract -l uzb
                  │                  ┌────────┴────────┐
                  │              psm 3 TSV        psm 11 TSV
                  │              page text        table —
                  │            (table region      rebuilt from
                  │              cut out)         coordinates
                  │                  └────────┬────────┘
                  └────────────┬──────────────┘
                               ▼
                   Document(text, tables, pages)
                               │
                     ┌─────────┴─────────┐
                     ▼                   ▼
                rekvizit.py        topshiriq.py ──▶ muddat.py
              4 fields + 4        from tables +     7 deadline
               extra ones          from prose         types
                     └─────────┬─────────┘
                               ▼
                      document_parser.py
                               │
              ┌────────────────┼────────────────┐
              ▼                ▼                ▼
      natijalar.json      FastAPI + web       tests/
                                          (against the gold set)
```

**The central property:** the scanned path is wired into the main pipeline in
such a way that `document_parser.py` works **unchanged** for both kinds of
input. `pdf_processor.oqi()` detects on its own that a PDF has no text layer and
switches to OCR.

---

## Why these technologies

### pdfplumber, not PyMuPDF

`pdftotext` and PyMuPDF return text **flattened**, separating columns with
spaces. In our documents the cell text is split across two lines:

```
1   Murojaatlarni avtomatik tasniflash      Axborot texnologiyalari
    modulini joriy etish                    boshqarmasi              2026-yil 1-may
```

Deciding "which word belongs to which column" from whitespace alone is not
reliable here. pdfplumber, on the other hand, sees the **ruling lines** of the
table and returns the cells correctly.

### Tesseract (`uzb`), not PaddleOCR

| | PaddleOCR | **Tesseract** |
|:--|:--|:--|
| Uzbek model | none — only a generic `latin` | **`uzb` exists** (plus `uzb_cyrl`) |
| Installation | paddlepaddle, ~500 MB | `apt install`, already on the system |
| Measured CER | — | **1.83%** (paragraph text) |

### Rules, not an LLM

This is a **measured decision**. The rule-based path reaches 100% on both sets,
runs in ~0.3 s and is **deterministic** — the same input always produces the
same output. A local LLM (Qwen) would also have been possible without breaking
the constraint, but:

- the current accuracy is 100% — there is nothing left for an LLM to improve;
- an LLM's output is not deterministic, which is a risk for a field like a
  deadline;
- a 2B model needs ~4 GB of VRAM and tens of seconds.

**The limitation of the rule-based path is stated openly:** it is fitted to the
structure of these 6 samples. On a document with a completely different template
accuracy will drop — see "Where it fails" below.

---

## How it works — the key solutions

### 1. Rebuilding a table from a scan (`table_extractor.py`)

A scan has neither ruling lines nor a text layer — only pixels. Plain OCR text
mixes the columns up. So the table is rebuilt geometrically, **from word
coordinates**:

1. `tesseract --psm 11` (sparse text) + TSV → `x, y, w, h` for every word
2. words are grouped into **text lines** by `y` (chained)
3. the **header row** defines the columns (4 or 5 of them — it varies)
4. text lines are merged into **logical rows**
5. end of table: if two consecutive rows carry no deadline — it is over

**Two passes turned out to be necessary.** The header is centered in its cell
while the body text is left-aligned. Measured on `xat_2`:

```
header:  «T/r» 337..400          «Topshiriq mazmuni» 765..1153
midpoint:                 582
body:                           «Murojaatlar» 466..681
```

The 582 boundary fell in the middle of the action item text and split it in
two. The fix: pass 1 finds the **end of the table** using coarse boundaries,
then the boundaries are recomputed from the **empty corridors** between words
inside the table region only (the real corridor is 376..465).

### 2. `--psm 11` and `--psm 6` together

Measured (2 documents):

| psm | words | avg confidence | confidence<40 | garbage | spurious Cyrillic |
|:--|--:|--:|--:|--:|--:|
| 3 | 181 | 90.1 | 11 | 5 | 0 |
| 6 | 182 | 86.5 | 19 | 4 | 9 |
| **11** | 166 | **95.4** | **0** | **0** | **0** |

`--psm 11` is the cleanest, **but** it misses the standalone digits in the "№"
column (1 2 3 4 5) entirely. `--psm 6` finds them with 94-97% confidence, but
also adds 9-12 spurious Cyrillic words. So **`psm 11` is the primary** source
and only **short numeric tokens** are taken from `psm 6` (the ones that do not
land on an existing word box).

### 3. A deadline is never forced into a single date

"within 10 days after the prototype is ready" is not a date, it is a
**condition**. Writing it down as 2026-10-10 would **lose information**. That is
why 7 types are distinguished:

| type | example | is a date computed |
|:--|:--|:--|
| `absolyut` (absolute) | 2026-yil 1-may · 18.09.2026 | ✅ |
| `nisbiy` (relative) | within three working days · within a month | ✅ from the document date |
| `bogliq` (dependent) | within 2 months after the system is ready | ❌ a condition |
| `takrorlanuvchi` (recurring) | every quarter · every Friday | ❌ periodic |
| `boshlanish` (start) | starting from 15 March 2026 | ✅ the start date |
| `doimiy` (permanent) | permanently · regularly | ❌ |
| `yoq` (none) | — | ❌ |

For `nisbiy`, **working days** are taken into account (Saturdays and Sundays are
skipped). The document's own rule is read as well: *"action items without an
explicitly stated deadline shall be completed within one month"*.

### 4. Uzbek-specific handling

- **Apostrophe variants** (`'` `’` `‘` `ʻ` `ʼ`) are normalized to one form
- **Two-letter initials**: `Sh. Qodirov`, `Ch. Rahimov`, `O'. Toshev`
- The **imperative-optative verb** suffix `-sin` / `-sinlar` is the main signal
  for recognizing an action item (`taqdim etilsin`, `ta'minlansinlar`)
- In letters, `so'raymiz` / `so'raladi` is the polite imperative form
- **OCR loses the apostrophe**: in number words the apostrophe was made optional
  (`o'n`/`on`, `to'rt`/`tort`) — in the `xat_1` scan "o'n kun muddatda" came out
  as "on kun muddatda" and the deadline was being missed

---

## Accuracy — measured

The gold set is written by hand: `tests/etalon.py` — 6 documents, **24
letterhead fields** and **39 action items**, each with its assignee and deadline
type.

```bash
venv/bin/python -m tests.test_aniqlik             # digital PDFs
venv/bin/python -m tests.test_aniqlik --skaner    # scans (OCR)
venv/bin/python -m tests.test_ocr_sifat           # OCR CER/WER
venv/bin/python -m app.services.muddat            # 18 deadline cases
```

### Final result

| metric | digital PDF | scan (OCR) |
|:--|--:|--:|
| Letterhead fields (organization · number · date · signatory) | **24/24 — 100%** | **24/24 — 100%** |
| Finding action items — recall | **100%** | **100%** |
| Finding action items — precision | **100%** | **100%** |
| F1 | **100%** | **100%** |
| Assignee correct | **39/39 — 100%** | **39/39 — 100%** |
| Deadline type correct | **39/39 — 100%** | **39/39 — 100%** |
| Deadline date correct | **39/39 — 100%** | **39/39 — 100%** |
| Deadline normalizer | 18/18 | 18/18 |

### OCR quality, measured separately

The ground truth comes for free: every document exists in **two versions** — a
digital PDF and a scan of it. The text layer of the digital PDF *is* the correct
text.

| document | paragraph CER | paragraph WER | table rows | cells exact |
|:--|--:|--:|:--:|--:|
| NAMUNA_1_abzats | 0.34% | 3.57% | — | — |
| NAMUNA_2_jadval | 0.68% | 7.14% | 5 / 5 ✓ | 100.0% |
| NAMUNA_3_ilova | 0.55% | 5.51% | 5 / 5 ✓ | 90.0% |
| xat_1_abzatsdagi | 1.88% | 3.43% | — | — |
| xat_2_jadvaldagi | 3.92% | 7.61% | 6 / 6 ✓ | 70.8% |
| xat_3_ilovadagi | 4.09% | 10.34% | 7 / 7 ✓ | 85.7% |
| **overall** | **1.81%** | **5.61%** | **all correct** | **85.9%** |

85.9% of the table cells match **exactly**, and the cell-level CER is 2.38%. The
remaining differences are apostrophe forms and single-character errors; they had
**no effect on the extraction result** (the 100% above).

### Speed

Measured over HTTP (`uvicorn app.main:app`, median):

| path | time | note |
|:--|--:|:--|
| `GET /` (web page) | **0.6 ms** | a single HTML file, no CDN |
| `GET /api/namunalar` | **1.2 ms** | the list of 12 files |
| `GET /api/salomatlik` | **13.1 ms** | a `tesseract --list-langs` subprocess |
| digital, 1 page of prose | **49.5 ms** | 5 action items |
| digital, 1 page with a table | **59.1 ms** | 6 action items |
| digital, 2 pages + annex | **81.0 ms** | 8 action items |
| PDF upload (multipart, 2 pages) | **82.8 ms** | write to disk + parse |
| **scan, 1 page** | **19.9 s** | 300 dpi render + OCR ×2 + table rebuild |
| **scan, 2 pages** | **37.3 s** | ~20 s per page |
| scan — **from cache** | **3.7 – 5.3 ms** | ~5000x faster |

Startup takes **0.46 s** — no model is loaded (rules + Tesseract).

The OCR result is cached in `data/results/ocr_kesh/` keyed by the **hash of the
file contents**, so the same document is parsed instantly the second time. The
web interface recognizes a scanned file up front and warns "OCR is running — it
may take 20-40 seconds".

---

## Where it fails

| Risk | What happens | Current state |
|:--|:--|:--|
| **A different template** | the rules are fitted to the structure of the 6 samples; in a document of a completely different shape action items may not be found at all | the main limitation. A local LLM could be added as a fallback |
| **An unrelated PDF** (a book, a CV, a report) | not an official document — the output cannot be trusted | **measured and guarded:** a deadline column is mandatory in the action item table (false items 34 → 0), and with `rasmiy_hujjatmi=false` the web interface warns openly |
| **A table without ruling lines** | in a digital PDF, if the table has no lines pdfplumber does not see it | the text is read as prose — the action items are still found, but not split into columns |
| **Spurious Cyrillic** | OCR reads some word with Cyrillic letters (`bo'linmalarga` → `Бо птаагга`) | 1 word in `xat_2`. It stays as a text fragment and did not affect extraction |
| **A deadline split across two lines** | the row boundary may push it onto the next row | the boundary is placed half a line above the start of the row — fixed on NAMUNA_3 |
| **A skewed scan** | coordinate-based table rebuilding groups lines by y; heavy skew breaks it | untested — the samples are scanned straight |
| **Concurrent requests** | many simultaneous requests for the same scan | **guarded:** a file lock — OCR runs once and the others wait for its result (measured: 3 requests → 1 tesseract, 20 s) |
| **Cache corruption** | the process dies in the middle of a write | **guarded:** atomic writes (`os.replace`) + recovery from a corrupted cache |
| **Handwriting** | Tesseract is trained on printed text | not supported |
| **Size of the gold set** | 6 documents, 39 action items — a small set | the 100% figure holds for this set. On a larger set a drop is natural |

> [!NOTE]
> **How to read that 100%.** It is the result on these 6 documents (in 2
> versions = 12 files) and 39 action items. The gold set is written by hand, and
> which clauses were deliberately excluded is explained in `tests/etalon.py`
> (oversight items, approval clauses, sentences introducing a table — these are
> not action items). The evaluation matches **by text fragment**, so OCR
> character errors cannot falsely improve the result.

---

## Files

```
uzbek-doc-extractor/
├── app/
│   ├── main.py                     the FastAPI application
│   ├── api/routes.py               4 routes: salomatlik · namunalar · tahlil · namuna
│   ├── core/
│   │   ├── config.py               paths, OCR settings, thresholds
│   │   └── console.py              pretty terminal output
│   ├── services/
│   │   ├── pdf_processor.py        PDF -> text + tables; detects scans itself
│   │   ├── ocr.py                  pdftoppm + tesseract, cached
│   │   ├── table_extractor.py      rebuilds a scanned table from coordinates
│   │   ├── rekvizit.py             4 letterhead fields + 4 extra ones
│   │   ├── topshiriq.py            action items from tables and from prose
│   │   ├── muddat.py               7 deadline types, working days
│   │   └── document_parser.py      ties everything together
│   ├── models/schemas.py           API schemas (pydantic)
│   └── templates/index.html        web interface, no CDN
├── data/
│   ├── input/{matnli,skaner}/       6 + 6 documents (digital / scanned)
│   └── results/                     measurements (JSON) + the OCR cache
├── tests/
│   ├── etalon.py                   the HAND-WRITTEN gold set: 24 + 39
│   ├── test_aniqlik.py             letterhead / action item accuracy
│   └── test_ocr_sifat.py           CER · WER · table cell accuracy
├── requirements.txt
└── README.md
```

Report: [`data/results/hisobot.md`](data/results/hisobot.md) — the method,
the accuracy and the failure modes in short form.

> [!NOTE]
> Module names, routes, response fields and CLI flags keep their Uzbek names
> (`rekvizit`, `topshiriq`, `muddat`, `/api/namunalar`, `--skaner`) because that
> is what the code and the API actually expose. Their meaning is given in the
> tables above.
