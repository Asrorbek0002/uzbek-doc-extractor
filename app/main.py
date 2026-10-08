# -*- coding: utf-8 -*-
"""The FastAPI application — document analysis.

Running it:
    uvicorn app.main:app --reload
    python -m app.main                  # the same, but it picks the port itself

Then in a browser: http://127.0.0.1:8000

THE CONSTRAINT (from the assignment): documents are never sent to external
cloud services. The whole pipeline is local — pdfplumber, Tesseract and rules.
No external API is called, so the application works fully offline.

NOTE ON LANGUAGE: the strings the user sees stay in Uzbek — the documents and
their readers are Uzbek. Comments are in English.
"""
from __future__ import annotations

import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.routes import yollar
from app.core import config as c

SHABLON = Path(__file__).resolve().parent / "templates"

app = FastAPI(
    title="Document analysis",
    description=(
        "Extracts the letterhead fields and the action items out of a PDF "
        "document. Digital or scanned — everything runs locally, no cloud."
    ),
    version="1.0",
    docs_url="/docs",
)

app.include_router(yollar)
app.mount("/static", StaticFiles(directory=SHABLON), name="static")


@app.get("/", include_in_schema=False)
def bosh_sahifa() -> FileResponse:
    """The web interface: upload a PDF -> "Tahlil qilish" (Analyze) -> results."""
    return FileResponse(SHABLON / "index.html")


@app.exception_handler(StarletteHTTPException)
def _http_xato(_, xato: StarletteHTTPException) -> JSONResponse:
    """Returns every HTTP error in the same shape."""
    return JSONResponse(status_code=xato.status_code,
                        content={"xato": str(xato.detail), "izoh": ""})


@app.exception_handler(Exception)
def _kutilmagan_xato(_, xato: Exception) -> JSONResponse:
    """An unexpected error — a short message for the user, the detail in the log.

    Internal details (paths, the traceback) are never sent to the browser.
    """
    traceback.print_exception(type(xato), xato, xato.__traceback__)
    return JSONResponse(
        status_code=500,
        content={"xato": "Serverda kutilmagan xato yuz berdi",
                 "izoh": type(xato).__name__})


def main() -> int:
    import uvicorn

    print(f"  Hujjat tahlili → http://127.0.0.1:8000     "
          f"(max {c.MAKS_FAYL_MB} MB, OCR {c.OCR_DPI} dpi / {c.OCR_TIL})")
    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="warning")
    return 0


if __name__ == "__main__":
    sys.exit(main())
