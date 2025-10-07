import os
import json
import hashlib
import re
import fitz  # PyMuPDF
from .constants import KNOWLEDGE_BASE_FILE
from .logger import get_logger
logger = get_logger(__name__)

class KnowledgeBase:
    """Load/save KB and create document fingerprint."""

    def __init__(self, path=KNOWLEDGE_BASE_FILE):
        self.path = path
        self.data = self.load()

    def load(self):
        if os.path.exists(self.path):
            try:
                with open(self.path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.exception("KnowledgeBase.load: failed to read KB file")
                return {}
        return {}

    def save(self):
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(self.data, f, indent=4, ensure_ascii=False)

    @staticmethod
    def create_fingerprint(doc):
        fingerprint_text = ""
        if len(doc) > 0:
            page = doc[0]
            fingerprint_text += page.get_text(
                "text", clip=fitz.Rect(0, 0, page.rect.width, 150)
            )
        if not fingerprint_text:
            return None
        return hashlib.sha256(fingerprint_text.encode("utf-8")).hexdigest()

    @staticmethod
    def sanitize_anchor_text(anchor: str) -> str:
        if not anchor:
            return anchor
        a = anchor
        a = re.sub(r"\b\d{9,12}\b", "<ID>", a)
        a = re.sub(r"\b(?:84|0)\d{8,10}\b", "<PHONE>", a)
        a = re.sub(r"\b\d{6,}\b", "<NUM>", a)
        return a