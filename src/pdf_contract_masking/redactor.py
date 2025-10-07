import re
import os
import fitz  # PyMuPDF
from .constants import ID_REGEX, PHONE_REGEX, DEFAULT_CUSTOMER_KEYWORDS
from .logger import get_logger
logger = get_logger(__name__)

class Redactor:
    """Apply learned rules to redact a PDF document."""

    def __init__(self, config, customer_keywords=None):
        self.config = config
        self.customer_keywords = customer_keywords or DEFAULT_CUSTOMER_KEYWORDS
        # None = unknown, False = not supported, True = supported
        self._supports_chars = None
        # Set to True after we've logged a chars-related AssertionError to avoid log spam
        self._chars_error_logged = False

    # Helper: safe wrapper around page.search_for that logs failures
    def _safe_search_for(self, page, text, clip=None):
        try:
            if clip is not None:
                return page.search_for(text, clip=clip)
            return page.search_for(text)
        except Exception:
            logger.exception("Redactor._safe_search_for failed for text=%s", text)
            return []

    # Helper: draw a filled black rect with fallbacks; returns True if any drawing succeeded
    def _draw_filled_rect(self, page, rect):
        try:
            page.draw_rect(rect, color=(0, 0, 0), fill=(0, 0, 0))
            return True
        except Exception:
            logger.exception("Redactor._draw_filled_rect: page.draw_rect failed")
            try:
                s = page.new_shape()
                s.draw_rect(rect)
                s.finish(fill=(0, 0, 0))
                s.commit()
                return True
            except Exception:
                logger.exception("Redactor._draw_filled_rect: shape fallback failed")
                try:
                    page.add_redact_annot(rect, fill=(0, 0, 0))
                    return True
                except Exception:
                    logger.exception("Redactor._draw_filled_rect: add_redact_annot failed")
                    return False

    # Helper: compute redact rect, draw it, append overlay entry and return whether added
    def _compute_and_record(self, page, area, token, pattern_str, overlays):
        left_keep, right_keep = self._compute_keep(pattern_str, token)
        redact_rect = self._get_mid_redact_rect(page, area, token, left_keep, right_keep)
        overlay = self._visible_token_overlay(token, pattern_str)
        ok = self._draw_filled_rect(page, redact_rect)
        overlays.append((page.number, redact_rect, overlay, pattern_str, token))
        return 1 if ok else 0

    def apply_rules(self, doc, rules, nlp_pipeline=None):
        total_redactions = 0
        overlays = []
        REQUIRE_NEAR_PERSON = os.environ.get("REQUIRE_NEAR_PERSON", "0") == "1" and (nlp_pipeline is not None)
        person_rects_by_page = self._gather_person_rects(doc, nlp_pipeline) if REQUIRE_NEAR_PERSON else {}
        for rule in rules:
            page_num, anchor, pattern_str = rule["page"], rule["anchor"], rule["pattern"]
            pattern = re.compile(pattern_str)
            if page_num >= len(doc):
                continue
            page = doc[page_num]
            anchor_rects = page.search_for(anchor)
            if anchor and not anchor_rects and any(x in anchor for x in ["<ID>", "<PHONE>", "<NUM>"]):
                total_redactions += self._handle_sanitized_anchor(page, pattern_str, anchor, overlays)
                continue
            if anchor and anchor_rects:
                _, add_count = self._apply_anchor_rects(page_num, page, anchor_rects, pattern, anchor, overlays)
                total_redactions += add_count
                continue
            if os.environ.get("ALLOW_PAGE_WIDE_FALLBACK", "0") == "1":
                total_redactions += self._page_wide_redact(page_num, page, pattern, overlays)
        self._draw_overlays(doc, overlays)
        return total_redactions

    def _gather_person_rects(self, doc, nlp_pipeline):
        rects_by_page = {}
        for pnum, page in enumerate(doc):
            txt = page.get_text("text")
            if not txt.strip():
                rects_by_page[pnum] = []
                continue
            try:
                ner_res = nlp_pipeline(txt)
            except Exception as e:
                logger.exception("Redactor._gather_person_rects: nlp_pipeline failed")
                ner_res = []
            names = [ent["word"] for ent in ner_res if ent.get("entity_group") == "PER"]
            rects = []
            for name in set(names):
                try:
                    rects.extend(page.search_for(name))
                except Exception as e:
                    logger.exception("Redactor._gather_person_rects: page.search_for(name) failed for '%s'", name)
                    continue
            rects_by_page[pnum] = rects
        return rects_by_page

    def _handle_sanitized_anchor(self, page, pattern_str, anchor, overlays):
        added = 0
        try:
            page_text = page.get_text("text")
            label_text = anchor.replace("<ID>", "").replace("<PHONE>", "").replace("<NUM>", "").strip()
            if not label_text:
                return 0
            label_rects = []
            try:
                label_rects = page.search_for(label_text)
            except Exception as e:
                logger.exception("Redactor._handle_sanitized_anchor: page.search_for(label_text) failed")
                label_rects = []
            if not label_rects:
                alt = label_text.split()[:3]
                if alt:
                    try:
                        label_rects = page.search_for(" ".join(alt))
                    except Exception as e:
                        logger.exception("Redactor._handle_sanitized_anchor: fallback search_for failed")
                        label_rects = []
            for lr in label_rects:
                for m in re.finditer(pattern_str, page_text):
                    token = m.group(0)
                    for area in page.search_for(token):
                        if not self._is_label_token_ok(page, lr, area, pattern_str, token):
                            continue
                        left_keep, right_keep = self._compute_keep(pattern_str, token)
                        redact_rect = self._get_mid_redact_rect(page, area, token, left_keep, right_keep)
                        overlay = self._visible_token_overlay(token, pattern_str)
                        added += self._compute_and_record(page, area, token, pattern_str, overlays)
        except Exception as e:
            logger.exception("Redactor._handle_sanitized_anchor failed")
        return added

    def _apply_anchor_rects(self, page_num, page, anchor_rects, pattern, anchor, overlays):
        added = 0
        for an_rect in anchor_rects:
            search_rect = fitz.Rect(an_rect.x1, an_rect.y0 - 5, an_rect.x1 + 200, an_rect.y1 + 5)
            try:
                sensitive_text = page.get_text(clip=search_rect).strip()
            except Exception:
                sensitive_text = ""
                logger.exception("Redactor._apply_anchor_rects: failed to get clipped text for search_rect")
            match = pattern.search(sensitive_text)
            if match:
                token = match.group(0)
                for area in self._safe_search_for(page, token, clip=search_rect):
                    added += self._compute_and_record(page, area, token, pattern.pattern, overlays)
                    break
            try:
                anchor_text = page.get_text(clip=an_rect).strip()
            except Exception:
                anchor_text = ""
                logger.exception("Redactor._apply_anchor_rects: failed to get anchor text clip")
            match2 = pattern.search(anchor_text)
            if match2:
                token = match2.group(0)
                for area in self._safe_search_for(page, token, clip=an_rect):
                    added += self._compute_and_record(page, area, token, pattern.pattern, overlays)
        return False, added

    def _page_wide_redact(self, page_num, page, pattern, overlays):
        added = 0
        page_text = page.get_text("text")
        for m in pattern.finditer(page_text):
            token = m.group(0)
            for area in page.search_for(token):
                left_keep, right_keep = self._compute_keep(pattern.pattern, token)
                redact_rect = self._get_mid_redact_rect(page, area, token, left_keep, right_keep)
                added += self._compute_and_record(page, area, token, pattern.pattern, overlays)
        return added

    def _is_label_token_ok(self, page, lr, area, pattern_str, token):
        try:
            label_text = page.get_text(clip=lr).lower()
        except Exception as e:
            logger.exception("Redactor._is_label_token_ok: failed to get label text")
            label_text = ""
        money_keywords = ['số tiền', 'khoản vay', 'khoản', 'giá trị', 'thanh toán']
        if any(k in label_text for k in money_keywords):
            return False
        mid_area_y = (area.y0 + area.y1) / 2.0
        mid_lr_y = (lr.y0 + lr.y1) / 2.0
        same_line = abs(mid_area_y - mid_lr_y) <= 14
        to_right = area.x0 >= (lr.x1 - 2)
        if not (same_line and to_right):
            return False
        digits_only = re.sub(r"\D", "", token)
        allow_phone_label = any(x in label_text for x in ['điện thoại', 'sđt'])
        allow_id_label = any(x in label_text for x in ['cmnd', 'căn cước', 'cccd'])
        if (pattern_str == PHONE_REGEX.pattern or PHONE_REGEX.fullmatch(digits_only)) and not allow_phone_label:
            return False
        if (pattern_str == ID_REGEX.pattern or ID_REGEX.fullmatch(digits_only)) and not allow_id_label:
            return False
        return True

    def _compute_keep(self, pattern_str, token):
        digits = re.sub(r"\D", "", token)
        if (pattern_str == ID_REGEX.pattern or ID_REGEX.fullmatch(digits)) and len(digits) >= 4:
            return self.config.get_keep("id")
        if (pattern_str == PHONE_REGEX.pattern or PHONE_REGEX.fullmatch(digits)) and len(digits) >= 6:
            return self.config.get_keep("phone")
        return 0, 0

    def _get_mid_redact_rect(self, page, area: fitz.Rect, token: str, left_keep: int, right_keep: int):
        """
        Try to compute a redact rect that covers the middle characters of a token.
        Prefer per-character boxes when supported by the PyMuPDF build; otherwise fall
        back to a proportional split across the token bounding area.
        """
        digits = re.sub(r"\D", "", token)
        if not digits:
            return area

        # Detect/remember whether page.get_text("chars") is supported to avoid repeated AssertionErrors
        if self._supports_chars is None:
            try:
                _ = page.get_text("chars")
                self._supports_chars = True
            except AssertionError:
                self._supports_chars = False
                if not self._chars_error_logged:
                    logger.exception("Redactor._get_mid_redact_rect: 'chars' not supported by PyMuPDF; disabling char-based computation")
                    self._chars_error_logged = True
            except Exception:
                if not self._chars_error_logged:
                    logger.exception("Redactor._get_mid_redact_rect: checking 'chars' support failed")
                    self._chars_error_logged = True
                self._supports_chars = False

        if self._supports_chars:
            try:
                chars = page.get_text("chars")
                digit_chars = [
                    (fitz.Rect(c[0], c[1], c[2], c[3]), c[4])
                    for c in chars
                    if fitz.Rect(c[0], c[1], c[2], c[3]).intersects(area) and c[4].isdigit()
                ]
                if len(digit_chars) >= left_keep + right_keep + 1:
                    mid_chars = digit_chars[left_keep: len(digit_chars) - right_keep]
                    if mid_chars:
                        r0 = mid_chars[0][0]
                        for rc, ch in mid_chars[1:]:
                            r0 |= rc
                        return r0
            except AssertionError:
                # PyMuPDF build may raise AssertionError for unsupported 'chars' option.
                # Disable char-based attempts and log once to reduce noise.
                self._supports_chars = False
                if not self._chars_error_logged:
                    logger.exception("Redactor._get_mid_redact_rect: char-based 'chars' call raised AssertionError; disabling char-based computation")
                    self._chars_error_logged = True
            except Exception:
                if not self._chars_error_logged:
                    logger.exception("Redactor._get_mid_redact_rect: char-based rect computation failed")
                    self._chars_error_logged = True
                # disable for future attempts to reduce noise
                self._supports_chars = False

        # fallback: split area width proportionally across digits
        try:
            char_w = area.width / max(1, len(digits))
            x0 = area.x0 + char_w * left_keep
            x1 = area.x0 + char_w * (len(digits) - right_keep)
            if x1 > x0 + 1:
                return fitz.Rect(x0, area.y0, x1, area.y1)
        except Exception:
            logger.exception("Redactor._get_mid_redact_rect: fallback proportional split failed")

        return area

    def _visible_token_overlay(self, token: str, pattern_str: str) -> str:
        digits = re.sub(r"\D", "", token)
        if not digits:
            return token
        try:
            if pattern_str == ID_REGEX.pattern or ID_REGEX.fullmatch(digits):
                if len(digits) >= 4:
                    return f"{digits[:2]}...{digits[-2:]}"
            if pattern_str == PHONE_REGEX.pattern or PHONE_REGEX.fullmatch(digits):
                if len(digits) >= 6:
                    return f"{digits[:4]}...{digits[-2:]}"
        except Exception as e:
            logger.exception("Redactor._visible_token_overlay: formatting overlay failed")
        if len(digits) > 2:
            return f"{digits[0]}...{digits[-1]}"
        return digits

    def _draw_overlays(self, doc, overlays):
        for pnum, rect, text, pat, token in overlays:
            try:
                page = doc[pnum]
                fontsize = max(6, int(rect.height * 0.7))
                page.insert_textbox(rect, text, fontsize=fontsize, color=(1,1,1), align=1)
            except Exception as e:
                logger.exception("Redactor._draw_overlays: insert_textbox failed")