import torch
from transformers import pipeline, AutoTokenizer, AutoModelForTokenClassification
from .logger import get_logger
logger = get_logger(__name__)

class NERModelLoader:
    """Load a Vietnamese NER pipeline (lazy)."""

    def __init__(self, model_name="vinai/phobert-base-v2"):
        self.model_name = model_name
        self.pipeline = None

    def load(self):
        if self.pipeline is not None:
            return self.pipeline
        try:
            tokenizer = AutoTokenizer.from_pretrained(self.model_name)
            model = AutoModelForTokenClassification.from_pretrained(self.model_name)
            self.pipeline = pipeline(
                "ner",
                model=model,
                tokenizer=tokenizer,
                device=0 if torch.cuda.is_available() else -1,
                aggregation_strategy="simple",
            )
            return self.pipeline
        except Exception as e:
            logger.exception("NERModelLoader.load failed")
            return None