# Report

**The task:** extract the letterhead fields (sending organization, document
number, date, signatory) and the action items (text, deadline, assignee) out of
PDF documents. Both digital and scanned.

**The constraint:** documents must not be sent to external cloud services.

---

## 1. Which method was chosen

### The decision: rules (deterministic), not an LLM

| Option | Why it was rejected / chosen |
|:--|:--|
| A cloud LLM (GPT, Gemini) | ❌ **forbidden by the constraint** — the document would leave the machine |
| A local LLM (Qwen 2B) | ❌ does not break the constraint, but its output is not deterministic; for a field like a deadline that is a risk. ~4 GB of VRAM and tens of seconds |
| **Rules (regex + geometry)** | ✅ deterministic, ~0.3 s, no external dependency, measured accuracy 100% |

The limitation of the rule-based path is **stated openly**: it is fitted to the
structure of the 6 given samples. On a document with a different template
accuracy will drop. A local LLM could later be added as a **fallback** (fired
when the rules find 0 action items) — that way the strengths of both approaches
are kept.

### Reading PDFs: pdfplumber

`pdftotext` and PyMuPDF return text flattened, separating columns with spaces.
In our documents the cell text is split across two lines — deciding "which word
belongs to which column" from whitespace is not reliable. pdfplumber sees the
table's **ruling lines** and returns the cells correctly.

### OCR: Tesseract (`uzb`)

| | PaddleOCR | **Tesseract** |
|:--|:--|:--|
| Uzbek model | none, only a generic `latin` | **`uzb` exists** |
| Installation | paddlepaddle ~500 MB | `apt install` |
| Measured CER | — | **1.83%** |

`pytesseract` / `pdf2image` were **not used**: both are thin shells over
`tesseract` and `pdftoppm`. Calling them directly through `subprocess` removes
a dependency and gives full control over the TSV output (word coordinates) —
which is exactly what rebuilding the scanned tables rests on.

### Deadlines are never forced into a single date

"within 10 days after the prototype is ready" is a **condition**, not a date.
Writing it down as 2026-10-10 would lose information. Seven types are
distinguished: `absolyut` · `nisbiy` · `bogliq` · `takrorlanuvchi` ·
`boshlanish` · `doimiy` · `yoq`.

---

## 2. How accurate it is

### The gold set

Written by hand: `tests/etalon.py` — 6 documents, **24 letterhead fields** and
**39 action items**, each with its assignee and deadline type. Which clauses
were deliberately excluded is explained as well (oversight items, approval
clauses, sentences introducing a table — these are not action items).

Every document exists in **two versions**: a digital PDF and a scan of it. That
is what lets one gold set evaluate both collections and shows the price of OCR
directly.

### Final result

| Metric | Digital PDF | Scan (OCR) |
|:--|--:|--:|
| Letterhead — organization | 6/6 — 100% | 6/6 — 100% |
| Letterhead — number | 6/6 — 100% | 6/6 — 100% |
| Letterhead — date | 6/6 — 100% | 6/6 — 100% |
| Letterhead — signatory | 6/6 — 100% | 6/6 — 100% |
| **Letterhead total** | **24/24 — 100%** | **24/24 — 100%** |
| Action items — recall | **100%** | **100%** |
| Action items — precision | **100%** | **100%** |
| Action items — F1 | **100%** | **100%** |
| Assignee correct | 39/39 — 100% | 39/39 — 100% |
| Deadline type correct | 39/39 — 100% | 39/39 — 100% |
| Deadline date correct | 39/39 — 100% | 39/39 — 100% |
| Deadline normalizer | 18/18 | 18/18 |

To reproduce:

```bash
venv/bin/python -m tests.test_aniqlik             # digital
venv/bin/python -m tests.test_aniqlik --skaner    # scans
```

Result JSON: `baholash_matnli.json` · `baholash_skaner.json`

### OCR quality, measured separately

| document | prose CER | prose WER | table rows (truth/OCR) | cells exact |
|:--|--:|--:|:--:|--:|
| NAMUNA_1_abzats | 0.34% | 3.57% | — | — |
| NAMUNA_2_jadval | 0.68% | 7.14% | 5 / 5 ✓ | 20/20 — 100% |
| NAMUNA_3_ilova | 0.55% | 5.51% | 5 / 5 ✓ | 18/20 — 90% |
| xat_1_abzatsdagi | 1.88% | 3.43% | — | — |
| xat_2_jadvaldagi | 3.92% | 7.61% | 6 / 6 ✓ | 17/24 — 70.8% |
| xat_3_ilovadagi | 4.09% | 10.34% | 7 / 7 ✓ | 30/35 — 85.7% |
| **overall** | **1.81%** | **5.61%** | **all correct** | **85.9%** · CER 2.38% |

Result JSON: `ocr_sifat.json`

> **The basis of the measurement matters.** The pipeline splits the text into
> two streams: the prose and the table cells. So the prose is compared against
> the digital PDF's text **without** the table, and a cell against a cell. At
> first `pdftotext -layout` (with the table) was used as the ground truth and
> the CER came out at 31% — that was not quality, it was a **measurement
> error**.

### Speed

Measured over HTTP (`uvicorn app.main:app`, median):

| path | time | note |
|:--|--:|:--|
| `GET /` (web page) | **0.6 ms** | a single HTML file |
| `GET /api/namunalar` | **1.2 ms** | the list of 12 files |
| `GET /api/salomatlik` | **13.1 ms** | invokes `tesseract --list-langs` as a subprocess |
| `POST /api/tahlil` — digital, 1 page of prose | **49.5 ms** | 5 action items |
| `POST /api/tahlil` — digital, 1 page with a table | **59.1 ms** | 6 action items |
| `POST /api/tahlil` — digital, 2 pages + annex | **81.0 ms** | 8 action items |
| PDF upload (multipart, 2 pages) | **82.8 ms** | write to disk + parse |
| `POST /api/tahlil` — **scan, 1 page** | **19.9 s** | 300 dpi render + OCR ×2 + table rebuild |
| `POST /api/tahlil` — **scan, 2 pages** | **37.3 s** | ~20 s per page |
| scan — **from cache** | **3.7 – 5.3 ms** | keyed by the hash of the file contents |

Startup: **0.46 s** (no model is loaded — rules and Tesseract do the work).

> [!NOTE]
> 20 s per page on a scan is the real cost of OCR: `pdftoppm` renders a 300 dpi
> image, then `tesseract` runs twice (`--psm 3` for the text, `--psm 11` for the
> table coordinates). The result is cached, so the same document is parsed
> **4000x faster** the second time.
>
> The web interface recognizes a scanned file up front and warns "OCR is
> running — it may take 20-40 seconds", so the user knows to wait.

The OCR result is stored in `ocr_kesh/` keyed by the **hash** of the file
contents.

---

## 3. Where it fails

### Bugs found and fixed so far

Problems discovered during the measurements and solved — each one confirmed
against the gold set:

| Problem | Cause | Fix |
|:--|:--|:--|
| Table text mixed into the prose | on the OCR path the table area was not cut out | the page text is collected from outside the table's bbox |
| An action item split across two columns | the header is centered, the body left-aligned — the boundary fell in the middle of the text | **two passes**: once the end of the table is known, the boundaries are recomputed from the empty corridors |
| Word order broken inside a cell | line grouping was anchored to the first word's `y` | chained grouping + a cap on the line's height |
| The "№" column was empty | `--psm 11` does not see standalone digits | **only** short numeric tokens are added from `--psm 6` |
| A deadline leaked into the next row | the row boundary sat in the middle of the gap | the boundary is placed half a line above the start of the next row |
| A relative deadline was missed | OCR lost the apostrophe: "o'n kun" → "on kun" | the apostrophe is optional in number words |
| The order number was empty | OCR reads "№" as "No" | the column name is matched **exactly** (a substring is dangerous: "no" would match "Tashkilot nomi") |
| OCR repeated on concurrent requests | the cache had no lock; FastAPI runs a synchronous endpoint on a threadpool, so requests really do run in parallel. **MEASURED:** 3 requests for the same scan → all three ran the full OCR (23 s each, the work done 3 times) | a per-file lock + double-checked locking. **MEASURED result:** at most **1** tesseract at a time, and all three requests finish in 20.05 s — the same as a single request |
| A corrupt cache returned 500 forever | the cache write was not atomic; if the process died mid-write (OOM, Ctrl+C) the JSON was left half-written and EVERY subsequent request crashed with `JSONDecodeError` | write to a temporary file and move it into place with `os.replace` (atomic on POSIX) + read under `try`: a corrupt cache is discarded and OCR re-runs. **Tested:** recovered from both a truncated JSON and complete garbage |
| A stray character between letters | OCR read an apostrophe as `£`: "yig'ilishiga" → "yig£ilishiga". On that very line "to'g'risida" was read correctly — the error is random | a **positional** fix: `£ § ° ¢ ¤ \|` between two letters is turned back into an apostrophe. Uzbek orthography has no sign between letters, and a currency sign stands next to a digit. CER 1.83% → **1.81%** |

### What happens with an unrelated PDF — measured

Beyond the 6 documents given in the assignment, two genuinely unrelated PDFs
were tried:

| | A CV (2 pages) | A Python textbook (112 pages) |
|:--|:--|:--|
| tables found | 0 | **304** |
| action items — **before the fix** | 0 ✅ | **34 false ones** ❌ |
| action items — **after the fix** | **0** ✅ | **0** ✅ |
| `rasmiy_hujjatmi` | **false** | **false** |

**The cause of the false action items:** the header of the textbook's
escape-sequence table ("Vazifasi") matched "vazifa" in the `U_MATN` list, while
no deadline column was required. As a result rows such as "Keyingi qatorga
o'tish" (`\n`) and "Qo'ng'iroq" (`\a`) were taken as action items.

**The fix:** an action item table must have a **deadline column** as well — the
assignment defines an action item that way ("each action item, with its
DEADLINE and its assignee"). Every action item table in the 6 given documents
has a "Muddat" column, so accuracy stayed at 100% (39/39).

**A second fix — not failing silently.** The letterhead extractor takes an
uppercase line as the organization, and a book title is in uppercase — which is
why the textbook produced "organization = PYTHON ASOSLARI". There is now a
document-level `rasmiy_hujjatmi` judgement; it looks at three pieces of
evidence (document number · date · at least one action item) and when two of
them are missing the web interface warns openly: *"Bu fayl rasmiy xat yoki
qarorga o'xshamaydi"* ("this file does not look like an official letter or
decree").

The separation is complete: all three pieces of evidence are present in the 6
documents, and not one of them in the CV or the textbook.

### Remaining limitations

| Risk | What happens | Current state |
|:--|:--|:--|
| **A different template** | the rules are fitted to the 6 samples; in a document of another shape the action items may not be found | **the main limitation**. Fallback: a local LLM |
| **An unrelated PDF** | if it is not an official document the result is unreliable | stated openly with `rasmiy_hujjatmi=false`; it manufactures no false action items (measured) |
| **A table without ruling lines** | pdfplumber does not see the table | the text is read as prose; the action items are still found, but not split into columns |
| **Spurious Cyrillic** | OCR reads some word in Cyrillic (`bo'linmalarga` → `Бо птаагга`) | 1 word in `xat_2`; it did not affect the extraction |
| **A skewed scan** | the table rebuild groups lines by `y` | untested — the samples are scanned straight |
| **Handwriting** | Tesseract is trained on printed text | not supported |
| **Size of the gold set** | 6 documents, 39 action items — a small set | the 100% holds for this set; on a larger one a drop is natural |

### How to read that 100%

- The set is **small**: 6 documents, in 2 versions = 12 files, 39 action items.
- The gold set is written **by hand**, i.e. not taken from the system's output.
- The evaluation matches **by text fragment** — OCR character errors cannot
  falsely improve the result (if anything, they break the match).
- Even so, the number does **not** mean "the system is perfect". It means "no
  errors remain on the given documents".

---

## 4. The result files

| file | what it holds |
|:--|:--|
| `natijalar.json` | the full analysis of the 6 documents (letterhead + action items) |
| `baholash_matnli.json` | accuracy on the digital PDFs, with the list of failures |
| `baholash_skaner.json` | accuracy on the scans |
| `ocr_sifat.json` | CER · WER · table cell accuracy |
| `ocr_kesh/` | the OCR cache (not committed, recomputable) |
