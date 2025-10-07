import os
from tqdm import tqdm
from .config import RedactionConfig
from .knowledge_base import KnowledgeBase
from .rule_learner import RuleLearner
from .redactor import Redactor
from .ner import NERModelLoader
from .logger import get_logger
logger = get_logger(__name__)

class PDFProcessor:
    """High level orchestration: open PDF, learn rules, apply redaction, save."""

    def __init__(self, config: RedactionConfig, kb: KnowledgeBase, nlp_pipeline=None):
        self.config = config
        self.kb = kb
        self.nlp = nlp_pipeline
        self.learner = RuleLearner()
        self.redactor = Redactor(config)

    def process_pdf_final(self, input_pdf, output_pdf):
        """
        Process a single PDF file and save result.

        Logs input/output absolute paths and whether save succeeded (file exists and size).
        """
        try:
            import fitz
            in_path = os.path.abspath(input_pdf)
            out_path = os.path.abspath(output_pdf)
            logger.info("Processing input=%s output=%s", in_path, out_path)

            doc = fitz.open(in_path)
            logger.info("Opened document %s (pages=%d)", in_path, len(doc))
            fingerprint = KnowledgeBase.create_fingerprint(doc)
            logger.debug("Document fingerprint=%s", fingerprint)

            if fingerprint and fingerprint in self.kb.data:
                total_redactions = self.redactor.apply_rules(doc, self.kb.data[fingerprint], self.nlp)
            else:
                new_rules = self.learner.learn(doc, self.nlp)
                if new_rules:
                    total_redactions = self.redactor.apply_rules(doc, new_rules, self.nlp)
                    if fingerprint:
                        sanitized = []
                        for r in new_rules:
                            r2 = r.copy()
                            r2["anchor"] = KnowledgeBase.sanitize_anchor_text(r2.get("anchor", ""))
                            sanitized.append(r2)
                        self.kb.data[fingerprint] = sanitized
                else:
                    total_redactions = 0

            # Ensure output directory exists
            try:
                out_dir = os.path.dirname(out_path) or os.getcwd()
                os.makedirs(out_dir, exist_ok=True)
            except Exception:
                logger.exception("Failed to prepare output directory for %s", out_path)

            # Attempt to save and then verify file existence
            try:
                logger.info("Saving processed document to: %s", out_path)
                doc.save(out_path, garbage=4, deflate=True, clean=True)
            except Exception:
                logger.exception("Failed to save output PDF %s", out_path)
            finally:
                try:
                    doc.close()
                except Exception:
                    logger.exception("Failed to close document %s", in_path)

            # Verify the saved file
            try:
                if os.path.exists(out_path):
                    size = os.path.getsize(out_path)
                    logger.info("Output file exists: %s (size=%d bytes). redactions=%d", out_path, size, total_redactions)
                else:
                    logger.error("Output file was not created: %s", out_path)
            except Exception:
                logger.exception("Failed to verify output file %s", out_path)

            return total_redactions
        except Exception:
            logger.exception("Error processing %s", input_pdf)
            return 0

if __name__ == "__main__":
    if os.environ.get("RULES_ONLY", "0") == "1":
        nlp = None
    else:
        nlp = NERModelLoader().load()
    kb = KnowledgeBase()
    cfg = RedactionConfig()
    proc = PDFProcessor(cfg, kb, nlp_pipeline=nlp)
    output_directory = "hop_dong_da_che_AI_Final"
    os.makedirs(output_directory, exist_ok=True)
    pdf_files = [f for f in os.listdir("./contract") if f.lower().endswith(".pdf") and not f.startswith("che_")]
    for filename in tqdm(pdf_files, desc="Processing PDFs"):
        input_path = os.path.join("./contract", filename)
        output_filename = os.path.join(output_directory, f"che_{filename}")
        proc.process_pdf_final(input_path, output_filename)
    kb.save()