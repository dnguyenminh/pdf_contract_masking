from pdf_contract_masking.processor import PDFProcessor
from pdf_contract_masking.knowledge_base import KnowledgeBase
from pdf_contract_masking.config import RedactionConfig
from pdf_contract_masking.ner import NERModelLoader
import os

# Minimal script to process one file to a specific output path
if os.environ.get("RULES_ONLY", "0") == "1":
    nlp = None
else:
    nlp = NERModelLoader().load()

kb = KnowledgeBase()
cfg = RedactionConfig()
proc = PDFProcessor(cfg, kb, nlp_pipeline=nlp)

input_pdf = r"contract\42669366_10000009_[DN VAY VON KIEM HOP DONG TIN DUNG.pdf].pdf"
output_pdf = r"hop_dong_da_che_AI_Final\che_42669366_test_console.pdf"

print(f"Processing {input_pdf} -> {output_pdf}")
proc.process_pdf_final(input_pdf, output_pdf)
print("Done")
