import os
from tqdm import tqdm
from pdf_contract_masking.processor import PDFProcessor
from pdf_contract_masking.ner import NERModelLoader
from pdf_contract_masking.knowledge_base import KnowledgeBase
from pdf_contract_masking.config import RedactionConfig

def main():
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

    pdf_files = [f for f in os.listdir("./contract")
                 if f.lower().endswith(".pdf") and not f.startswith("che_")]

    if not pdf_files:
        print("Không tìm thấy file PDF nào để xử lý.")
        return

    print(f"Tìm thấy {len(pdf_files)} file PDF. Bắt đầu xử lý...")
    for filename in tqdm(pdf_files, desc="Tổng tiến trình"):
        input_path = os.path.join("./contract", filename)
        output_filename = os.path.join(output_directory, f"che_{filename}")
        proc.process_pdf_final(input_path, output_filename)

    kb.save()
    print("--- Hoàn tất! Đã cập nhật cơ sở tri thức. ---")

if __name__ == "__main__":
    main()