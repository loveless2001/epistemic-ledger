"""Document ingestion and snapshotting for Epistemic Ledger pipeline.

Supports local `.txt`/`.md`, local `.pdf` (via `pdftotext`), and `arxiv:<id>`.
Produces normalized text plus SHA-256 hash so every audit report is bound to an
exact document snapshot.
"""

from __future__ import annotations

import hashlib
import re
import subprocess
import urllib.request
from dataclasses import dataclass
from pathlib import Path

ARXIV_ID_RE = re.compile(r"^[0-9]{4}\.[0-9]{4,5}(v[0-9]+)?$")


@dataclass(frozen=True)
class IngestedDocument:
    source_ref: str
    resolved_path: Path
    sha256: str
    raw_text: str
    normalized_text: str
    dehyphenated_text: str


def normalize_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def dehyphenate_and_normalize(text: str) -> str:
    # Join PDF soft line-break hyphens (e.g. "repre-\nsentation" -> "representation")
    joined = re.sub(r"([A-Za-z])-\s*\n\s*([A-Za-z])", r"\1\2", text)
    return normalize_whitespace(joined)


def _extract_pdf_text(pdf_path: Path) -> str:
    try:
        proc = subprocess.run(
            ["pdftotext", str(pdf_path), "-"],
            check=True,
            capture_output=True,
            text=True,
        )
        return proc.stdout
    except FileNotFoundError as exc:
        raise RuntimeError(
            "pdftotext is required to ingest PDF files but was not found in PATH"
        ) from exc
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(f"pdftotext failed on {pdf_path}: {exc.stderr.strip()}") from exc


def _fetch_arxiv_pdf(arxiv_id: str, cache_dir: Path) -> Path:
    if not ARXIV_ID_RE.match(arxiv_id):
        raise ValueError(f"Invalid arXiv identifier: {arxiv_id!r}")
    cache_dir.mkdir(parents=True, exist_ok=True)
    target = cache_dir / f"arxiv_{arxiv_id}.pdf"
    if not target.exists():
        url = f"https://arxiv.org/pdf/{arxiv_id}.pdf"
        req = urllib.request.Request(url, headers={"User-Agent": "epistemic-ledger-pipeline/0.1"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = resp.read()
        if not data.startswith(b"%PDF"):
            raise RuntimeError(f"Downloaded content from {url} is not a valid PDF")
        target.write_bytes(data)
    return target


def ingest_document(source_ref: str, cache_dir: Path | None = None) -> IngestedDocument:
    """Ingest a local file (.md/.txt/.pdf) or `arxiv:<id>`."""
    if source_ref.startswith("arxiv:"):
        arxiv_id = source_ref[len("arxiv:") :].strip()
        resolved = _fetch_arxiv_pdf(arxiv_id, cache_dir or Path("/tmp/epistemic-ledger-cache"))
    else:
        resolved = Path(source_ref).expanduser().resolve()
        if not resolved.is_file():
            raise FileNotFoundError(f"Document not found: {resolved}")

    raw_bytes = resolved.read_bytes()
    digest = hashlib.sha256(raw_bytes).hexdigest()

    if resolved.suffix.lower() == ".pdf":
        raw_text = _extract_pdf_text(resolved)
    else:
        raw_text = raw_bytes.decode("utf-8")

    return IngestedDocument(
        source_ref=source_ref,
        resolved_path=resolved,
        sha256=digest,
        raw_text=raw_text,
        normalized_text=normalize_whitespace(raw_text),
        dehyphenated_text=dehyphenate_and_normalize(raw_text),
    )
