# Compatibility wrapper re-exporting split classes/functions
from .config import RedactionConfig
from .ner import NERModelLoader
from .knowledge_base import KnowledgeBase
from .rule_learner import RuleLearner
from .redactor import Redactor
from .processor import PDFProcessor

__all__ = [
    "RedactionConfig",
    "NERModelLoader",
    "KnowledgeBase",
    "RuleLearner",
    "Redactor",
    "PDFProcessor",
]

# Small compatibility helpers mapping previous top-level functions
def load_ner_model(model_name="vinai/phobert-base-v2"):
    return NERModelLoader(model_name=model_name).load()

def load_redaction_config(path=None):
    return RedactionConfig(path=path or None).cfg

def load_knowledge_base(path=None):
    return KnowledgeBase(path=path or None).data

def save_knowledge_base(kb_obj):
    if isinstance(kb_obj, KnowledgeBase):
        kb_obj.save()
    elif isinstance(kb_obj, dict):
        kb = KnowledgeBase()
        kb.data = kb_obj
        kb.save()