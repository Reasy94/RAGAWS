import sys
import os
import fitz
import pdfplumber
from pathlib import Path
from langchain_text_splitters import RecursiveCharacterTextSplitter


# ─── CONFIGURAZIONE ────────────────────────────────────────────────────────────

CHUNK_SIZE        = 500
CHUNK_OVERLAP     = 50
IMAGE_MIN_SIZE    = 200  # pixel — below this threshold it's decorative
DRAWING_THRESHOLD = 50   # vector paths — above this threshold it's a chart
MIN_TABLE_ROWS    = 0   # below this threshold it's likely a false positive


# ─── PAGE INSPECTOR ────────────────────────────────────────────────────────────

def _has_table_heuristic(fitz_page) -> bool:
    """
    Lightweight heuristic to detect tables without opening pdfplumber.
    Checks for horizontal and vertical lines typical of table borders.
    Limitation: invisible tables (whitespace-aligned) won't be detected here —
    pdfplumber will still catch them via text coordinate analysis.
    """
    drawings = fitz_page.get_drawings()
    h_lines  = [d for d in drawings if d["type"] == "l" and d["rect"].height < 2]
    v_lines  = [d for d in drawings if d["type"] == "l" and d["rect"].width  < 2]
    return len(h_lines) > 3 and len(v_lines) > 3


def _inspect_page(fitz_page, fitz_doc) -> dict:
    """
    Uses fitz as a lightweight inspector to understand page content
    before deciding which library to invoke.
    Called ONCE per page — results reused across all processing steps.
    """
    has_text = bool(fitz_page.get_text().strip())

    # Cache get_images() to avoid calling it twice
    images    = fitz_page.get_images(full=True)
    has_image = any(
        fitz_doc.extract_image(img[0]).get("width", 0) > IMAGE_MIN_SIZE
        for img in images
    ) if images else False

    has_vector = len(fitz_page.get_drawings()) > DRAWING_THRESHOLD and not has_image
    has_table  = _has_table_heuristic(fitz_page)

    return {
        "has_text":   has_text,
        "has_image":  has_image,
        "has_vector": has_vector,
        "has_table":  has_table,
        "images":     images,  # cached — reused to avoid double call
    }


# ─── CHUNKING ──────────────────────────────────────────────────────────────────

def chunk_pdf(pdf_path: str) -> list[dict]:
    """
    Pipeline per page:
    1. fitz _inspect_page()  → lightweight scan, decides which library to invoke
    2. Each type is ADDITIVE — a page can produce TEXT + VECTOR_GRAPHIC together
    3. pdfplumber opened only when page has text or table (never for pure image pages)
    """
    all_chunks = []

    splitter = RecursiveCharacterTextSplitter(
        chunk_size    = CHUNK_SIZE,
        chunk_overlap = CHUNK_OVERLAP,
        separators    = ["\n\n", "\n", ". ", " ", ""],
    )

    plumber_pdf = pdfplumber.open(pdf_path)
    fitz_doc    = fitz.open(pdf_path)

    for i in range(len(fitz_doc)):
        page_num  = i + 1
        fitz_page = fitz_doc[i]

        # ── STEP 1: fitz inspects the page — one call, results cached ─────────
        page_info = _inspect_page(fitz_page, fitz_doc)

        # ── STEP 2: fitz — visual content (additive, no continue) ─────────────

        # Vector graphic — atomic chunk placeholder
        if page_info["has_vector"]:
            all_chunks.append({
                "type":    "VECTOR_GRAPHIC",
                "page":    page_num,
                "content": (
                    f"[VECTOR_GRAPHIC - page {page_num}]\n"
                    f"[PLACEHOLDER - production: Claude Vision caption]\n"
                    f"[/VECTOR_GRAPHIC]"
                ),
            })

        # Embedded images — atomic chunk placeholder
        if page_info["has_image"]:
            for img in page_info["images"]:  # reuse cached list
                xref = img[0]
                try:
                    info = fitz_doc.extract_image(xref)
                    w, h = info.get("width", 0), info.get("height", 0)
                    if w > IMAGE_MIN_SIZE and h > IMAGE_MIN_SIZE:
                        all_chunks.append({
                            "type":    "IMAGE",
                            "page":    page_num,
                            "content": (
                                f"[IMAGE - page {page_num}]\n"
                                f"[PLACEHOLDER - production: Claude Vision caption]\n"
                                f"[/IMAGE]"
                            ),
                        })
                except Exception:
                    pass

        # ── STEP 3: pdfplumber — text + tables (only if page has text) ────────
        if page_info["has_text"]:
            plumber_page = plumber_pdf.pages[i]
            table_bboxes = []

            # Tables — always let pdfplumber decide (heuristic is unreliable
            # on invisible tables built with whitespace alignment)
            tables       = plumber_page.find_tables()
            table_bboxes = [t.bbox for t in tables]

            if tables:
                for table in tables:
                    extracted = table.extract()
                    if not extracted:
                        continue
                    header = extracted[0]
                    rows   = []
                    for row in extracted[1:]:
                        pairs = []
                        for h, cell in zip(header, row):
                            h_clean    = str(h).strip()    if h    else "?"
                            cell_clean = str(cell).strip() if cell else ""
                            if h_clean and cell_clean:
                                pairs.append(f"{h_clean}: {cell_clean}")
                        if pairs:
                            rows.append(" | ".join(pairs))

                    # MIN_TABLE_ROWS filter — avoids false positives
                    if rows and len(rows) >= MIN_TABLE_ROWS:
                        all_chunks.append({
                            "type":    "TABLE",
                            "page":    page_num,
                            "content": "[TABLE]\n" + "\n".join(rows) + "\n[/TABLE]",
                        })

            # Text — exclude table bounding boxes to avoid duplication
            if table_bboxes:
                filtered  = plumber_page.filter(
                    lambda obj: not any(
                        obj["x0"] >= bbox[0] and obj["top"]    >= bbox[1] and
                        obj["x1"] <= bbox[2] and obj["bottom"] <= bbox[3]
                        for bbox in table_bboxes
                    )
                )
                page_text = filtered.extract_text()
            else:
                page_text = plumber_page.extract_text()

            if page_text and page_text.strip():
                for chunk in splitter.split_text(page_text.strip()):
                    all_chunks.append({
                        "type":    "TEXT",
                        "page":    page_num,
                        "content": chunk,
                    })

    plumber_pdf.close()
    fitz_doc.close()

    return all_chunks


# ─── TEST ──────────────────────────────────────────────────────────────────────

def run_test(pdf_path: str) -> None:
    pdf_name    = Path(pdf_path).name
    output_path = str(Path(pdf_path).with_suffix("")) + "_chunks_v2.txt"

    print(f"Processing: {pdf_name}")

    try:
        chunks = chunk_pdf(pdf_path)

        n_text    = sum(1 for c in chunks if c["type"] == "TEXT")
        n_tables  = sum(1 for c in chunks if c["type"] == "TABLE")
        n_images  = sum(1 for c in chunks if c["type"] == "IMAGE")
        n_vectors = sum(1 for c in chunks if c["type"] == "VECTOR_GRAPHIC")

        with open(output_path, "w", encoding="utf-8") as f:
            f.write(f"{'='*60}\n")
            f.write(f"PDF: {pdf_name}\n")
            f.write(f"Chunk size: {CHUNK_SIZE} | Overlap: {CHUNK_OVERLAP}\n")
            f.write(f"Total chunks: {len(chunks)}\n")
            f.write(f"  TEXT:          {n_text}\n")
            f.write(f"  TABLE:         {n_tables}  (atomic)\n")
            f.write(f"  IMAGE:         {n_images}  (atomic)\n")
            f.write(f"  VECTOR_GRAPHIC:{n_vectors}  (atomic)\n")
            f.write(f"{'='*60}\n\n")

            for i, chunk in enumerate(chunks, start=1):
                f.write(f"--- CHUNK {i} [{chunk['type']}] page {chunk['page']} ({len(chunk['content'])} chars) ---\n")
                f.write(chunk["content"])
                f.write(f"\n\n{'─'*40}\n\n")

        print(f"  ✓ {len(chunks)} chunks → {output_path}")
        print(f"    TEXT: {n_text} | TABLE: {n_tables} | IMAGE: {n_images} | VECTOR: {n_vectors}")

    except FileNotFoundError:
        print(f"  ✗ File not found: {pdf_path}")
    except Exception as e:
        print(f"  ✗ Error: {type(e).__name__}: {e}")


# ─── ENTRY POINT ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage:")
        print("  poetry run python test_chunking_v2.py file.pdf")
        print("  poetry run python test_chunking_v2.py folder/")
        sys.exit(1)

    path = sys.argv[1]

    if os.path.isdir(path):
        pdf_files = sorted([
            os.path.join(path, f)
            for f in os.listdir(path)
            if f.lower().endswith(".pdf")
        ])
        if not pdf_files:
            print(f"No PDFs found in: {path}")
            sys.exit(1)
        print(f"Found {len(pdf_files)} PDFs\n")
        for pdf_file in pdf_files:
            run_test(pdf_file)
            print()
    else:
        run_test(path)
