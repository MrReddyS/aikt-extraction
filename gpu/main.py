"""
Docling PDF extraction API (GPU variant).

- EasyOCR with GPU when CUDA is available (EasyOcrOptions(use_gpu=True));
  falls back to CPU EasyOCR if not.
- Same batching settings as CPU (settings.perf); see
  https://github.com/docling-project/docling/issues/3163
- convert_all() for a single temp PDF path; merges markdown if multiple
  results are returned.
"""

from __future__ import annotations

import os
import tempfile
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any
from urllib.parse import unquote

import torch
from docling.datamodel.pipeline_options import (
    AcceleratorDevice,
    AcceleratorOptions,
    EasyOcrOptions,
    PdfPipelineOptions,
)
from docling.datamodel.settings import settings
from docling.document_converter import DocumentConverter, PdfFormatOption
from fastapi import FastAPI, File, Header, HTTPException, Request, UploadFile
from pydantic import BaseModel, Field

_converter: Any | None = None


def _expected_api_key() -> str | None:
    return os.environ.get("API_KEY") or os.environ.get("OPEN_WEBUI_API_KEY")


def _verify_bearer(authorization: str | None) -> None:
    expected = _expected_api_key()
    if not expected:
        return
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization")
    token = authorization.removeprefix("Bearer ").strip()
    if token != expected:
        raise HTTPException(status_code=401, detail="Invalid API key")


def _cuda_available() -> bool:
    try:
        return bool(torch.cuda.is_available())
    except Exception:
        return False


def _ocr_langs() -> list[str]:
    raw = os.environ.get("DOCLING_OCR_LANG", "en")
    langs = [x.strip() for x in raw.split(",") if x.strip()]
    return langs or ["en"]


def _apply_perf_settings() -> None:
    concurrency = int(os.environ.get("DOCLING_PERF_DOC_BATCH_CONCURRENCY", "10"))
    batch_size = int(os.environ.get("DOCLING_PERF_DOC_BATCH_SIZE", str(max(concurrency, 10))))
    settings.perf.doc_batch_concurrency = max(1, concurrency)
    settings.perf.doc_batch_size = max(settings.perf.doc_batch_concurrency, batch_size)


def _pdf_pipeline_options() -> Any:
    num_threads = int(os.environ.get("DOCLING_NUM_THREADS", str(os.cpu_count() or 4)))
    use_cpu_only = os.environ.get("DOCLING_USE_CPU_ONLY", "").lower() in ("1", "true", "yes")
    cuda_ok = _cuda_available()

    if use_cpu_only:
        device = AcceleratorDevice.CPU
        easy_use_gpu = False
        print("Using CPU accelerator (DOCLING_USE_CPU_ONLY set).", flush=True)
    elif cuda_ok:
        device = AcceleratorDevice.GPU
        easy_use_gpu = True
        print("Using GPU accelerator (CUDA available); EasyOCR use_gpu=True.", flush=True)
    else:
        device = AcceleratorDevice.CPU
        easy_use_gpu = False
        print(
            "CUDA not available — using CPU accelerator and EasyOCR on CPU. "
            "For GPU: install CUDA-enabled torch (see gpu/pyproject.toml) and ensure CUDA is visible.",
            flush=True,
        )

    accelerator_options = AcceleratorOptions(
        device=device,
        num_threads=max(1, num_threads),
    )
    ocr_options = EasyOcrOptions(
        lang=_ocr_langs(),
        use_gpu=easy_use_gpu,
    )
    pipeline_options = PdfPipelineOptions(
        do_ocr=True,
        do_table_structure=True,
        ocr_options=ocr_options,
        accelerator_options=accelerator_options,
        generate_page_images=False,
        generate_picture_images=False,
    )
    chunk = int(os.environ.get("DOCLING_PAGE_CHUNK_SIZE", "50"))
    fields = getattr(type(pipeline_options), "model_fields", {})
    if "page_chunk_size" in fields:
        pipeline_options = pipeline_options.model_copy(update={"page_chunk_size": chunk})
    return pipeline_options


def create_converter() -> Any:
    _apply_perf_settings()
    pipeline_options = _pdf_pipeline_options()
    return DocumentConverter(
        format_options={
            "pdf": PdfFormatOption(pipeline_options=pipeline_options),
        }
    )


def get_converter() -> Any:
    global _converter
    if _converter is None:
        _converter = create_converter()
    return _converter


def convert_pdf_bytes(data: bytes, filename: str) -> dict:
    """Run docling on PDF bytes; returns Open WebUI-shaped dict."""
    if not data:
        raise HTTPException(status_code=400, detail="Empty body")
    lower = filename.lower()
    if not lower.endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only .pdf files are supported")

    converter = get_converter()
    t0 = time.time()

    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp.write(data)
        tmp_path = tmp.name

    try:
        results = list(converter.convert_all([tmp_path]))
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Conversion failed: {e!s}") from e
    finally:
        Path(tmp_path).unlink(missing_ok=True)

    if not results:
        raise HTTPException(status_code=422, detail="Conversion produced no result")

    extraction_time = time.time() - t0
    markdown = "\n\n".join(r.document.export_to_markdown() for r in results)
    pages = 0
    for r in results:
        if hasattr(r.document, "pages") and r.document.pages is not None:
            pages += len(r.document.pages)
    if pages == 0:
        pages = "?"

    return {
        "page_content": markdown,
        "metadata": {
            "source": filename,
            "pages": pages,
            "extraction_time_s": round(extraction_time, 2),
            "output_size_kb": round(len(markdown) / 1024, 2),
        },
    }


@asynccontextmanager
async def lifespan(app: FastAPI):
    print(
        "ASGI ready. Docling/Torch load on first /process or /extract (often 1–5+ min, little console output).",
        flush=True,
    )
    yield


app = FastAPI(
    title="Docling PDF extraction (GPU)",
    description="Extract PDF to markdown (EasyOCR + CUDA when available, convert_all).",
    lifespan=lifespan,
)


class ExtractResponse(BaseModel):
    filename: str
    markdown: str
    pages: int | str = Field(description="Page count when available")
    extraction_time_s: float
    output_size_kb: float


@app.get("/health")
def health():
    """Liveness: no Docling/Torch import — returns immediately after Unit starts."""
    return {
        "status": "ok",
        "device": "gpu",
        "converter_loaded": _converter is not None,
    }


@app.get("/health/details")
def health_details():
    """Optional: imports Torch + Docling settings."""
    _apply_perf_settings()
    cuda = _cuda_available()
    chunk_supported = "page_chunk_size" in getattr(PdfPipelineOptions, "model_fields", {})
    return {
        "status": "ok",
        "device": "gpu",
        "converter_loaded": _converter is not None,
        "cuda_available": cuda,
        "ocr": "easyocr",
        "easyocr_use_gpu": cuda
        and os.environ.get("DOCLING_USE_CPU_ONLY", "").lower() not in ("1", "true", "yes"),
        "doc_batch_concurrency": settings.perf.doc_batch_concurrency,
        "doc_batch_size": settings.perf.doc_batch_size,
        "page_chunk_size_configured": bool(chunk_supported),
    }


@app.put("/process")
async def open_webui_process(
    request: Request,
    authorization: str | None = Header(None),
    x_filename: str | None = Header(None, alias="X-Filename"),
):
    """
    Open WebUI external document loader contract:
    PUT with raw file bytes; JSON { page_content, metadata }.
    """
    _verify_bearer(authorization)
    data = await request.body()
    name = "document.pdf"
    if x_filename:
        try:
            name = unquote(x_filename)
        except Exception:
            name = x_filename
    return convert_pdf_bytes(data, name)


@app.post("/extract", response_model=ExtractResponse)
async def extract(
    file: UploadFile = File(..., description="PDF file"),
    authorization: str | None = Header(None),
):
    _verify_bearer(authorization)
    if not file.filename:
        raise HTTPException(status_code=400, detail="Missing filename")
    data = await file.read()
    out = convert_pdf_bytes(data, file.filename)
    return ExtractResponse(
        filename=file.filename,
        markdown=out["page_content"],
        pages=out["metadata"]["pages"],
        extraction_time_s=out["metadata"]["extraction_time_s"],
        output_size_kb=out["metadata"]["output_size_kb"],
    )
