import sys
import os
import fitz
import pdfplumber
from pathlib import Path
from langchain_text_splitters import RecursiveCharacterTextSplitter


# ─── CONFIGURAZIONE ────────────────────────────────────────────────────────────

CHUNK_SIZE        = 500
CHUNK_OVERLAP     = 50
IMAGE_MIN_SIZE    = 200
DRAWING_THRESHOLD = 150
MIN_TABLE_ROWS    = 2
DPI               = 120
JPEG_QUALITY      = 85

IMAGES_OUTPUT_DIR = r"C:\Users\desal\Desktop\ProgettoRAGAWS\PDF\IMF Economy\Images_extracted"


# ─── PAGE INSPECTOR ────────────────────────────────────────────────────────────

def _has_table_heuristic(fitz_page) -> bool:
    drawings = fitz_page.get_drawings()
    h_lines  = [d for d in drawings if d["type"] == "l" and d["rect"].height < 2]
    v_lines  = [d for d in drawings if d["type"] == "l" and d["rect"].width  < 2]
    return len(h_lines) > 3 and len(v_lines) > 3


def _inspect_page(fitz_page, fitz_doc, page_num: int) -> dict:
    has_text  = bool(fitz_page.get_text().strip())
    images    = fitz_page.get_images(full=True)
    has_image = any(
        fitz_doc.extract_image(img[0]).get("width", 0) > IMAGE_MIN_SIZE
        for img in images
    ) if images else False

    drawings   = fitz_page.get_drawings()
    has_vector = len(drawings) > DRAWING_THRESHOLD
    has_table  = _has_table_heuristic(fitz_page)

    # ── DEBUG — stampa il conteggio drawing per ogni pagina ───────────────────
    print(f"  [DEBUG] Page {page_num:3d} → drawings: {len(drawings):4d} | "
          f"text={has_text} image={has_image} "
          f"vector={has_vector} table={has_table}")

    return {
        "has_text":   has_text,
        "has_image":  has_image,
        "has_vector": has_vector,
        "has_table":  has_table,
        "images":     images,
    }


# ─── IMAGE SAVING ──────────────────────────────────────────────────────────────

def _save_vector_graphic(fitz_page, pdf_stem: str, page_num: int) -> str:
    pix      = fitz_page.get_pixmap(dpi=DPI)
    filename = f"{pdf_stem}_page{page_num:03d}_VECTOR_GRAPHIC.jpg"
    out_path = Path(IMAGES_OUTPUT_DIR) / filename
    pix.save(str(out_path), jpg_quality=JPEG_QUALITY)
    size_kb  = out_path.stat().st_size / 1024
    return f"{filename} ({size_kb:.1f} KB)"


def _save_image(image_bytes: bytes, ext: str, pdf_stem: str, page_num: int, img_idx: int) -> str:
    filename = f"{pdf_stem}_page{page_num:03d}_IMAGE_{img_idx:02d}.{ext}"
    out_path = Path(IMAGES_OUTPUT_DIR) / filename
    with open(out_path, "wb") as f:
        f.write(image_bytes)
    size_kb = out_path.stat().st_size / 1024
    return f"{filename} ({size_kb:.1f} KB)"


# ─── CHUNKING ──────────────────────────────────────────────────────────────────

def chunk_pdf(pdf_path: str) -> list[dict]:
    all_chunks = []
    pdf_stem   = Path(pdf_path).stem

    Path(IMAGES_OUTPUT_DIR).mkdir(parents=True, exist_ok=True)

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
        page_info = _inspect_page(fitz_page, fitz_doc, page_num)

        # ── VECTOR GRAPHIC → pagina intera come JPEG ──────────────────────────
        if page_info["has_vector"]:
            saved = _save_vector_graphic(fitz_page, pdf_stem, page_num)
            all_chunks.append({
                "type":    "VECTOR_GRAPHIC",
                "page":    page_num,
                "content": (
                    f"[VECTOR_GRAPHIC - page {page_num}]\n"
                    f"[PLACEHOLDER - production: Claude Vision Haiku caption]\n"
                    f"[saved: {saved}]\n"
                    f"[/VECTOR_GRAPHIC]"
                ),
            })
            continue

        # ── IMAGE PURA (no testo) → immagine estratta ─────────────────────────
        if page_info["has_image"] and not page_info["has_text"]:
            img_idx = 0
            for img in page_info["images"]:
                xref = img[0]
                try:
                    info = fitz_doc.extract_image(xref)
                    w, h = info.get("width", 0), info.get("height", 0)
                    if w > IMAGE_MIN_SIZE and h > IMAGE_MIN_SIZE:
                        img_idx += 1
                        ext   = info.get("ext", "png")
                        saved = _save_image(info["image"], ext, pdf_stem, page_num, img_idx)
                        all_chunks.append({
                            "type":    "IMAGE",
                            "page":    page_num,
                            "content": (
                                f"[IMAGE - page {page_num}]\n"
                                f"[PLACEHOLDER - production: Claude Vision Haiku caption]\n"
                                f"[saved: {saved}]\n"
                                f"[/IMAGE]"
                            ),
                        })
                except Exception as e:
                    print(f"  ⚠ Error extracting image on page {page_num}: {e}")
            continue

        # ── IMAGE MISTA (has_text = True) → immagine estratta + testo ─────────
        if page_info["has_image"]:
            img_idx = 0
            for img in page_info["images"]:
                xref = img[0]
                try:
                    info = fitz_doc.extract_image(xref)
                    w, h = info.get("width", 0), info.get("height", 0)
                    if w > IMAGE_MIN_SIZE and h > IMAGE_MIN_SIZE:
                        img_idx += 1
                        ext   = info.get("ext", "png")
                        saved = _save_image(info["image"], ext, pdf_stem, page_num, img_idx)
                        all_chunks.append({
                            "type":    "IMAGE",
                            "page":    page_num,
                            "content": (
                                f"[IMAGE - page {page_num}]\n"
                                f"[PLACEHOLDER - production: Claude Vision Haiku caption]\n"
                                f"[saved: {saved}]\n"
                                f"[/IMAGE]"
                            ),
                        })
                except Exception as e:
                    print(f"  ⚠ Error extracting image on page {page_num}: {e}")

        # ── TEXT + TABLE → pdfplumber ──────────────────────────────────────────
        if page_info["has_text"]:
            plumber_page = plumber_pdf.pages[i]
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

                    if rows and len(rows) >= MIN_TABLE_ROWS:
                        all_chunks.append({
                            "type":    "TABLE",
                            "page":    page_num,
                            "content": "[TABLE]\n" + "\n".join(rows) + "\n[/TABLE]",
                        })

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
    output_path = str(Path(pdf_path).with_suffix("")) + "_chunks_final.txt"

    print(f"\nProcessing: {pdf_name}")
    print(f"DRAWING_THRESHOLD: {DRAWING_THRESHOLD}")
    print("─" * 60)

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
            f.write(f"DPI: {DPI} | JPEG quality: {JPEG_QUALITY}\n")
            f.write(f"Drawing threshold: {DRAWING_THRESHOLD}\n")
            f.write(f"Images output dir: {IMAGES_OUTPUT_DIR}\n")
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

        print(f"\n  ✓ {len(chunks)} chunks → {output_path}")
        print(f"    TEXT: {n_text} | TABLE: {n_tables} | IMAGE: {n_images} | VECTOR: {n_vectors}")
        print(f"    Images saved to: {IMAGES_OUTPUT_DIR}")

    except FileNotFoundError:
        print(f"  ✗ File not found: {pdf_path}")
    except Exception as e:
        print(f"  ✗ Error: {type(e).__name__}: {e}")


# ─── ENTRY POINT ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage:")
        print("  poetry run python test_chunking_v2_final.py file.pdf")
        print("  poetry run python test_chunking_v2_final.py folder/")
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
