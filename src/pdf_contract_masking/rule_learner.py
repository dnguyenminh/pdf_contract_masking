import re
import fitz  # PyMuPDF
from .constants import ID_REGEX, PHONE_REGEX, DEFAULT_CUSTOMER_KEYWORDS
from .knowledge_base import KnowledgeBase
from .logger import get_logger
logger = get_logger(__name__)

class RuleLearner:
    """Learn simple anchor+pattern rules from a PDF document."""

    def __init__(self, customer_keywords=None):
        self.customer_keywords = customer_keywords or DEFAULT_CUSTOMER_KEYWORDS

    def _extract_person_names(self, page_text, nlp_pipeline):
        if not nlp_pipeline:
            return []
        try:
            ner_results = nlp_pipeline(page_text)
            return [ent["word"] for ent in ner_results if ent.get("entity_group") == "PER"]
        except Exception as e:
            logger.exception("RuleLearner._extract_person_names failed")
            return []

    def _gather_sensitive_from_words(self, page):
        words = page.get_text("words")
        sensitive = []
        for w in words:
            w_text = w[4].strip()
            if ID_REGEX.fullmatch(w_text) or PHONE_REGEX.fullmatch(w_text):
                sensitive.append({"text": w_text, "rect": fitz.Rect(w[0], w[1], w[2], w[3])})
        return sensitive

    def _add_label_rules(self, page, full_text, rules):
        label_patterns = [
            (re.compile(r"số\s*cmnd[:\s]*([0-9]{9,12})", re.IGNORECASE), ID_REGEX.pattern),
            (re.compile(r"số\s*điện\s*thoại[:\s]*([0-9]{9,12})", re.IGNORECASE), PHONE_REGEX.pattern),
            (re.compile(r"sđt[:\s]*([0-9]{9,12})", re.IGNORECASE), PHONE_REGEX.pattern),
        ]
        for lp, pat in label_patterns:
            for lm in lp.finditer(full_text):
                val = lm.group(1)
                if not val:
                    continue
                rects = page.search_for(val)
                if not rects:
                    continue
                raw_anchor = lm.group(0)[:40]
                lower_raw = raw_anchor.lower()
                money_keywords = ['số tiền', 'khoản vay', 'khoản', 'giá trị', 'thanh toán', 'số tiền (vnđ)']
                if any(k in lower_raw for k in money_keywords):
                    continue
                rule_anchor = KnowledgeBase.sanitize_anchor_text(raw_anchor)
                if rule_anchor and rule_anchor.strip():
                    rule = {"page": page.number, "anchor": rule_anchor, "pattern": pat}
                    if rule not in rules:
                        rules.append(rule)
        return rules

    def learn(self, doc, nlp_pipeline=None):
        rules = []
        for page_num, page in enumerate(doc):
            full_text = page.get_text("text")
            if not full_text.strip():
                continue
            skip_ner = __import__("os").environ.get("RULES_ONLY", "0") == "1" or nlp_pipeline is None
            person_names = [] if skip_ner else self._extract_person_names(full_text, nlp_pipeline)
            customer_rects = []
            if person_names:
                for name in set(person_names):
                    try:
                        for name_rect in page.search_for(name):
                            check_rect = name_rect + (-200, -20, 200, 20)
                            nearby_text = page.get_text(clip=check_rect).lower()
                            if any(keyword in nearby_text for keyword in self.customer_keywords):
                                customer_rects.append(name_rect)
                    except Exception as e:
                        logger.exception("RuleLearner.learn: error searching for person name")
                        continue
            if not customer_rects:
                lowered = full_text.lower()
                for kw in self.customer_keywords:
                    if kw in lowered:
                        for r in page.search_for(kw):
                            customer_rects.append(r)
            sensitive_words = self._gather_sensitive_from_words(page)
            if not sensitive_words:
                for m in ID_REGEX.finditer(full_text):
                    sensitive_words.append({"text": m.group(0), "rects": []})
                for m in PHONE_REGEX.finditer(full_text):
                    sensitive_words.append({"text": m.group(0), "rects": []})
            rules = self._add_label_rules(page, full_text, rules)
            for customer_rect in (customer_rects if customer_rects else [None]):
                for s in sensitive_words:
                    s_text = s.get("text") if isinstance(s, dict) else s
                    s_rects = s.get("rects") if isinstance(s, dict) and s.get("rects") else page.search_for(s_text)
                    for sensitive_rect in s_rects:
                        if customer_rect is not None:
                            if abs(customer_rect.y0 - sensitive_rect.y0) >= 120:
                                continue
                        anchor = self._choose_anchor(page, sensitive_rect)
                        if not anchor:
                            for kw in self.customer_keywords:
                                if kw in full_text.lower():
                                    anchor = kw
                                    break
                        pattern = ID_REGEX.pattern if ID_REGEX.search(s_text) else PHONE_REGEX.pattern
                        if not anchor or not str(anchor).strip():
                            continue
                        lower_anchor = str(anchor).lower()
                        money_keywords = ['số tiền', 'khoản vay', 'khoản', 'giá trị', 'thanh toán']
                        if any(k in lower_anchor for k in money_keywords):
                            continue
                        rule_anchor = KnowledgeBase.sanitize_anchor_text(anchor or "")
                        if not rule_anchor or not rule_anchor.strip():
                            continue
                        rule = {"page": page_num, "anchor": rule_anchor, "pattern": pattern}
                        if rule not in rules:
                            rules.append(rule)
        return rules

    def _choose_anchor(self, page, sensitive_rect):
        try:
            left_rect = fitz.Rect(sensitive_rect.x0 - 300, sensitive_rect.y0 - 5,
                                  sensitive_rect.x0 - 1, sensitive_rect.y1 + 5)
            page_words = page.get_text("words")
            strip_chars = " .,;:-_()[]\"'`"
            nearby_words = [w[4].strip(strip_chars) for w in page_words
                            if fitz.Rect(w[0], w[1], w[2], w[3]).intersects(left_rect)]
            nearby_words = [w for w in nearby_words if w and len(w) > 1]
            if nearby_words:
                anchor = " ".join(nearby_words[-3:])
                try:
                    if not page.search_for(anchor):
                        return None
                except Exception as e:
                    logger.exception("RuleLearner._choose_anchor: page.search_for failed")
                    pass
                return anchor
        except Exception as e:
            logger.exception("RuleLearner._choose_anchor failed")
            return None
        return None