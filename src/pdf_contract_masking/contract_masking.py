import os
import argparse
from tqdm import tqdm
from pdf_contract_masking.processor import PDFProcessor
from pdf_contract_masking.ner import NERModelLoader
from pdf_contract_masking.knowledge_base import KnowledgeBase
from pdf_contract_masking.config import RedactionConfig


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Process and redact PDFs in ./contract or a single file")
    parser.add_argument("--input", "-i", help="Path to a single input PDF to process")
    parser.add_argument("--output", "-o", help="Exact path to write the processed PDF when --input is given")
    args = parser.parse_args(argv)

    # Allow RULES_ONLY to skip model download
    if os.environ.get("RULES_ONLY", "0") == "1":
        nlp = None
    else:
        nlp = NERModelLoader().load()

    kb = KnowledgeBase()
    cfg = RedactionConfig()
    proc = PDFProcessor(cfg, kb, nlp_pipeline=nlp)

    output_directory = "hop_dong_da_che_AI_Final"
    os.makedirs(output_directory, exist_ok=True)

    # If input provided, process single file and honor output if given
    if args.input:
        input_path = args.input
        if args.output:
            output_path = args.output
        else:
            # default: put into output_directory with che_ prefix
            output_path = os.path.join(output_directory, f"che_{os.path.basename(input_path)}")
        print(f"Processing single file: {input_path} -> {output_path}")
        proc.process_pdf_final(input_path, output_path)
    else:
        # Batch mode: process all PDFs under ./contract
        pdf_files = [f for f in os.listdir("./contract")
                     if f.lower().endswith(".pdf") and not f.startswith("che_")]

        if not pdf_files:
            print("Không tìm thấy file PDF nào để xử lý.")
            return 0

        print(f"Tìm thấy {len(pdf_files)} file PDF. Bắt đầu xử lý...")
        for filename in tqdm(pdf_files, desc="Tổng tiến trình"):
            input_path = os.path.join("./contract", filename)
            output_filename = os.path.join(output_directory, f"che_{filename}")
            proc.process_pdf_final(input_path, output_filename)

    kb.save()
    print("--- Hoàn tất! Đã cập nhật cơ sở tri thức. ---")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())