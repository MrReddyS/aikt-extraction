"""
Send a PDF to the extraction API (default: http://localhost → port 80, PUT /process).

Reports client-side round-trip time and, when present, server-reported
``metadata.extraction_time_s``. Optional writes under ``tests/output/`` (gitignored).
"""

from __future__ import annotations

import argparse
import json
import os
import random
import sys
import time
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

TESTS_DIR = Path(__file__).resolve().parent


def _resolve_data_dir(data_dir: Path) -> Path:
    if data_dir.exists():
        return data_dir
    if os.name == "nt" and data_dir.as_posix().startswith("/"):
        alt = Path(data_dir.as_posix().lstrip("/"))
        if alt.exists():
            return alt
        alt2 = Path.cwd() / alt
        if alt2.exists():
            return alt2
    return data_dir


def _pick_pdf(data_dir: Path, pdf_glob: str, pick_random: bool) -> Path:
    pdfs = sorted(data_dir.glob(pdf_glob))
    if not pdfs:
        raise FileNotFoundError(f"No PDFs in {data_dir} matching {pdf_glob!r}")
    if pick_random:
        return random.choice(pdfs)
    return pdfs[0]


def _put_process(process_url: str, pdf_bytes: bytes, filename: str) -> tuple[int, dict[str, Any]]:
    headers: dict[str, str] = {
        "Content-Type": "application/pdf",
        "X-Filename": filename,
    }
    token = os.environ.get("API_KEY") or os.environ.get("OPEN_WEBUI_API_KEY")
    if token:
        headers["Authorization"] = f"Bearer {token}"

    req = Request(url=process_url, data=pdf_bytes, method="PUT", headers=headers)
    try:
        with urlopen(req, timeout=60 * 60) as resp:
            status = resp.status
            body = resp.read().decode("utf-8", errors="replace")
    except HTTPError as e:
        status = e.code or 500
        body = e.read().decode("utf-8", errors="replace") if e.fp else str(e)
        raise RuntimeError(f"HTTP {status}: {body[:800]}") from e
    except URLError as e:
        raise RuntimeError(f"Request failed: {e!s}") from e

    return status, json.loads(body)


def run(
    base_url: str,
    data_dir: Path,
    out_dir: Path | None,
    pdf_glob: str,
    random_pick: bool,
    seed: int | None,
) -> int:
    data_dir = _resolve_data_dir(data_dir)
    if not data_dir.is_dir():
        raise FileNotFoundError(f"Data directory not found: {data_dir}")

    if seed is not None:
        random.seed(seed)

    base = base_url.rstrip("/")
    process_url = f"{base}/process"

    pdf_path = _pick_pdf(data_dir, pdf_glob, random_pick)
    pdf_bytes = pdf_path.read_bytes()
    filename = pdf_path.name

    t0 = time.perf_counter()
    status, payload = _put_process(process_url, pdf_bytes, filename)
    client_s = time.perf_counter() - t0

    markdown = payload.get("page_content")
    if not isinstance(markdown, str):
        raise RuntimeError("Response missing string `page_content`")

    metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
    server_s = metadata.get("extraction_time_s")

    report: dict[str, Any] = {
        "process_url": process_url,
        "http_status": status,
        "input": {"file": filename, "bytes": len(pdf_bytes)},
        "extraction_time_client_s": round(client_s, 4),
        "extraction_time_server_s": server_s,
        "metadata": metadata,
    }

    print(json.dumps(report, indent=2))

    if out_dir is not None:
        out_dir.mkdir(parents=True, exist_ok=True)
        stem = pdf_path.stem
        md_path = out_dir / f"{stem}.md"
        json_path = out_dir / f"{stem}_timings.json"
        md_path.write_text(markdown, encoding="utf-8")
        json_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"Wrote {md_path}", file=sys.stderr)
        print(f"Wrote {json_path}", file=sys.stderr)

    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="PUT a PDF to the extraction server (default base URL uses port 80)."
    )
    parser.add_argument(
        "--base-url",
        default="http://localhost",
        help="Server origin, no trailing slash (default: http://localhost → port 80)",
    )
    default_data = "/data" if os.name != "nt" else str(TESTS_DIR / "data")
    parser.add_argument("--data-dir", default=default_data, help="Directory containing PDFs")
    parser.add_argument(
        "--out-dir",
        default=None,
        help="Write markdown and JSON timings here (e.g. tests/output — ignored by git)",
    )
    parser.add_argument("--glob", default="*.pdf", help="PDF glob under --data-dir")
    parser.add_argument(
        "--first",
        action="store_true",
        help="Use first PDF by name instead of random",
    )
    parser.add_argument("--seed", type=int, default=None, help="RNG seed when picking random PDF")

    args = parser.parse_args()

    out_dir = Path(args.out_dir).resolve() if args.out_dir else None

    os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

    try:
        return run(
            base_url=args.base_url,
            data_dir=Path(args.data_dir),
            out_dir=out_dir,
            pdf_glob=args.glob,
            random_pick=not args.first,
            seed=args.seed,
        )
    except (FileNotFoundError, RuntimeError, json.JSONDecodeError) as e:
        print(str(e), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
