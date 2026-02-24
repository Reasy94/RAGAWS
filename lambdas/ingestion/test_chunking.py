import sys
import pdfplumber
from langchain_text_splitters import RecursiveCharacterTextSplitter


def table_to_text(table: list) -> str:
    if not table:
        return ""

    header = table[0]  # ["", "2022", "2023", "2024e", "2025f", ...]
    rows = []
    print("HEADER GREZZO:", table[0])
    print("PRIMA RIGA:", table[1] if len(table) > 1 else "vuota")
    for row in table[1:]:
        if not row:
            continue
        
        # Prima cella = nome paese/regione
        row_label = str(row[0]).strip() if row[0] else ""
        
        pairs = []
        # Parti dalla seconda cella in poi
        for h, cell in zip(header[1:], row[1:]):
            h_clean = str(h).strip() if h else "?"
            cell_clean = str(cell).strip() if cell else ""
            if cell_clean:
                pairs.append(f"{h_clean}: {cell_clean}")
        
        if row_label and pairs:
            rows.append(f"{row_label} | " + " | ".join(pairs))
        elif pairs:
            rows.append(" | ".join(pairs))

    return "\n".join(rows)


def chunk_pdf(pdf_path: str, chunk_size: int = 400, chunk_overlap: int = 50) -> list[str]:
    all_chunks = []

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=["\n\n", "\n", ". ", " ", ""],
    )

    with pdfplumber.open(pdf_path) as pdf:
        if not pdf.pages:
            raise ValueError("Il PDF non contiene pagine.")

        for page in pdf.pages:
            page_chunks = []

            #tables = page.find_tables()
            tables = page.find_tables(table_settings={
                "vertical_strategy": "lines",
                "horizontal_strategy": "lines",
                "snap_tolerance": 5,
                "join_tolerance": 5,
                "edge_min_length": 10,
            })
            table_bboxes = [t.bbox for t in tables]
            extracted_tables = [t.extract() for t in tables]

            # Testo escludendo le aree delle tabelle
            if table_bboxes:
                filtered_page = page.filter(
                    lambda obj: not any(
                        obj["x0"] >= bbox[0] and obj["top"] >= bbox[1] and
                        obj["x1"] <= bbox[2] and obj["bottom"] <= bbox[3]
                        for bbox in table_bboxes
                    )
                )
                page_text = filtered_page.extract_text()
            else:
                page_text = page.extract_text()

            # Chunk del testo della pagina
            if page_text and page_text.strip():
                text_chunks = splitter.split_text(page_text.strip())
                page_chunks.extend(text_chunks)

            # Tabelle della pagina subito dopo il testo — ordine preservato
            for table in extracted_tables:
                table_text = table_to_text(table)
                if table_text:
                    page_chunks.append(f"[TABLE]\n{table_text}\n[/TABLE]")

            all_chunks.extend(page_chunks)

    if not all_chunks:
        raise ValueError("Nessun contenuto estraibile. Il PDF potrebbe essere scansionato.")

    return all_chunks


def run_test(pdf_path: str, chunk_size: int = 400, chunk_overlap: int = 50) -> None:
    print(f"Analisi in corso: {pdf_path}")

    try:
        chunks = chunk_pdf(pdf_path, chunk_size=chunk_size, chunk_overlap=chunk_overlap)

        # Nome file output basato sul PDF
        output_path = pdf_path.replace(".pdf", "_chunks.txt")

        with open(output_path, "w", encoding="utf-8") as f:
            f.write(f"{'='*60}\n")
            f.write(f"ANALISI PDF: {pdf_path}\n")
            f.write(f"Chunks generati: {len(chunks)}\n")
            f.write(f"{'='*60}\n\n")

            for i, chunk in enumerate(chunks, start=1):
                tag = "[TABLE]" if chunk.startswith("[TABLE]") else "[TEXT]"
                f.write(f"--- CHUNK {i} {tag} ({len(chunk)} caratteri) ---\n")
                f.write(chunk)
                f.write(f"\n\n{'-'*40}\n\n")

        print(f"Done! {len(chunks)} chunks salvati in: {output_path}")

    except FileNotFoundError:
        print(f"Errore: file '{pdf_path}' non trovato.")
    except ValueError as e:
        print(f"Errore sul contenuto del PDF: {e}")
    except Exception as e:
        print(f"Errore inatteso: {type(e).__name__}: {e}")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        run_test(sys.argv[1])
    else:
        print("Uso: python test.py nome_file.pdf")