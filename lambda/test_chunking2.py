import sys
import os
import fitz
import pdfplumber
from pathlib import Path
from langchain_text_splitters import RecursiveCharacterTextSplitter


# ─── CONFIGURAZIONE ────────────────────────────────────────────────────────────

CHUNK_SIZE        = 500
CHUNK_OVERLAP     = 50
IMAGE_MIN_SIZE    = 200  # pixel — sotto questa soglia è decorativa
DRAWING_THRESHOLD = 50   # path vettoriali — sopra questa soglia è un grafico


# ─── CHUNKING ──────────────────────────────────────────────────────────────────

def chunk_pdf(pdf_path: str) -> list[dict]:
    """
    Processa un PDF e restituisce tutti i chunk con metadati.
    - Testo          → RecursiveCharacterTextSplitter
    - Tabelle        → chunk atomico (Textract in produzione)
    - Immagini       → chunk atomico (Claude Vision in produzione)
    - Grafici vett.  → chunk atomico (Claude Vision in produzione)
    """
    all_chunks = []

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        separators=["\n\n", "\n", ". ", " ", ""],
    )

    plumber_pdf = pdfplumber.open(pdf_path)
    fitz_doc    = fitz.open(pdf_path)

    for i in range(len(fitz_doc)):
        page_num     = i + 1
        plumber_page = plumber_pdf.pages[i]
        fitz_page    = fitz_doc[i]

        # ── TABELLE → chunk atomico ──
        tables       = plumber_page.find_tables()
        table_bboxes = [t.bbox for t in tables]

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
            if rows:
                all_chunks.append({
                    "type":    "TABLE",
                    "page":    page_num,
                    "content": "[TABLE]\n" + "\n".join(rows) + "\n[/TABLE]",
                })

        # ── IMMAGINI EMBEDDED → chunk atomico placeholder ──
        for img in fitz_page.get_images(full=True):
            xref = img[0]
            try:
                info = fitz_doc.extract_image(xref)
                w, h = info.get("width", 0), info.get("height", 0)
                if w > IMAGE_MIN_SIZE and h > IMAGE_MIN_SIZE:
                    all_chunks.append({
                        "type":    "IMAGE",
                        "page":    page_num,
                        "content": (
                            f"[IMAGE - pagina {page_num}]\n"
                            f"[PLACEHOLDER - in produzione: Claude Vision caption]\n"
                            f"[/IMAGE]"
                        ),
                    })
            except Exception:
                pass

        # ── GRAFICI VETTORIALI → chunk atomico placeholder ──
        drawings           = fitz_page.get_drawings()
        has_embedded_image = bool([
            img for img in fitz_page.get_images(full=True)
            if fitz_doc.extract_image(img[0]).get("width", 0) > IMAGE_MIN_SIZE
        ]) if fitz_page.get_images() else False

        if len(drawings) > DRAWING_THRESHOLD and not has_embedded_image:
            all_chunks.append({
                "type":    "VECTOR_GRAPHIC",
                "page":    page_num,
                "content": (
                    f"[VECTOR_GRAPHIC - pagina {page_num}]\n"
                    f"[PLACEHOLDER - in produzione: Claude Vision caption]\n"
                    f"[/VECTOR_GRAPHIC]"
                ),
            })

        # ── TESTO → recursive chunking (escludi aree tabelle) ──
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
    output_path = str(Path(pdf_path).with_suffix("")) + "_chunks.txt"

    print(f"Analisi: {pdf_name}")

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
            f.write(f"Chunks totali: {len(chunks)}\n")
            f.write(f"  TEXT:          {n_text}\n")
            f.write(f"  TABLE:         {n_tables}  (atomici)\n")
            f.write(f"  IMAGE:         {n_images}  (atomici)\n")
            f.write(f"  VECTOR_GRAPHIC:{n_vectors}  (atomici)\n")
            f.write(f"{'='*60}\n\n")

            for i, chunk in enumerate(chunks, start=1):
                f.write(f"--- CHUNK {i} [{chunk['type']}] pag.{chunk['page']} ({len(chunk['content'])} car.) ---\n")
                f.write(chunk["content"])
                f.write(f"\n\n{'─'*40}\n\n")

        print(f"  ✓ {len(chunks)} chunks → {output_path}")
        print(f"    TEXT: {n_text} | TABLE: {n_tables} | IMAGE: {n_images} | VECTOR: {n_vectors}")

    except FileNotFoundError:
        print(f"  ✗ File non trovato: {pdf_path}")
    except Exception as e:
        print(f"  ✗ Errore: {type(e).__name__}: {e}")


# ─── ENTRY POINT ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso:")
        print("  poetry run python test_chunking_local.py file.pdf")
        print("  poetry run python test_chunking_local.py cartella/")
        sys.exit(1)

    path = sys.argv[1]

    if os.path.isdir(path):
        pdf_files = sorted([
            os.path.join(path, f)
            for f in os.listdir(path)
            if f.lower().endswith(".pdf")
        ])
        if not pdf_files:
            print(f"Nessun PDF in: {path}")
            sys.exit(1)
        print(f"Trovati {len(pdf_files)} PDF\n")
        for pdf_file in pdf_files:
            run_test(pdf_file)
            print()
    else:
        run_test(path)
