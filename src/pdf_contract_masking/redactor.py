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
        # IMEI/EMEI exclusion settings -- load from config if present
        try:
            imei_cfg = self.config.get_exclusion('imei', {}) if self.config else {}
        except Exception:
            imei_cfg = {}
        # enabled flag
        self._imei_exclude_enabled = bool(imei_cfg.get('enabled', True))
        # label variants to detect nearby IMEI labels (normalized lower-case)
        self._imei_variants = [s.lower() for s in imei_cfg.get('labels', ['imei', 'emei', 'số imei', 'so imei', 'sốemei', 'eimei', 'e-mei', 'e me i'])]
        # minimum digit length to treat a bare token as IMEI-like
        try:
            self._imei_min_digits = int(imei_cfg.get('min_digits', 13))
        except Exception:
            self._imei_min_digits = 13
        # Compile phone/id patterns from config when available so behavior
        # follows `redaction_config.json` instead of only the constants.
        try:
            phone_pat = (self.config.cfg.get('phone', {}) or {}).get('pattern') if getattr(self.config, 'cfg', None) is not None else None
            self._phone_re = re.compile(phone_pat) if phone_pat else PHONE_REGEX
        except Exception:
            self._phone_re = PHONE_REGEX
        try:
            id_pat = (self.config.cfg.get('id', {}) or {}).get('pattern') if getattr(self.config, 'cfg', None) is not None else None
            self._id_re = re.compile(id_pat) if id_pat else ID_REGEX
        except Exception:
            self._id_re = ID_REGEX

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
        method = None
        try:
            page.draw_rect(rect, color=(0, 0, 0), fill=(0, 0, 0))
            method = 'draw_rect'
            logger.debug("Redactor._draw_filled_rect: drew rect using draw_rect: %s", rect)
            return True
        except Exception:
            logger.exception("Redactor._draw_filled_rect: page.draw_rect failed for %s", rect)
            try:
                s = page.new_shape()
                s.draw_rect(rect)
                s.finish(fill=(0, 0, 0))
                s.commit()
                method = 'shape'
                logger.debug("Redactor._draw_filled_rect: drew rect using shape fallback: %s", rect)
                return True
            except Exception:
                logger.exception("Redactor._draw_filled_rect: shape fallback failed for %s", rect)
                try:
                    page.add_redact_annot(rect, fill=(0, 0, 0))
                    method = 'add_redact_annot'
                    logger.debug("Redactor._draw_filled_rect: added redact annot as last resort: %s", rect)
                    return True
                except Exception:
                    logger.exception("Redactor._draw_filled_rect: add_redact_annot failed for %s", rect)
                    return False

    # Helper: compute redact rect, draw it, append overlay entry and return whether added
    def _compute_and_record(self, page, area, token, pattern_str, overlays):
        left_keep, right_keep = self._compute_keep(pattern_str, token)
        redact_rect = self._get_mid_redact_rect(page, area, token, left_keep, right_keep)
        # Keep a snapshot of the mid-region computed from character/proportional
        # logic so subsequent padding/clamping never remove the actual mid-area
        # that must be redacted to remove underlying text.
        try:
            mid_rect = fitz.Rect(redact_rect)
        except Exception:
            mid_rect = redact_rect
        # If this looks like a phone token, expand the redact rect slightly to
        # account for OCR/spacing/layout differences so the black box fully
        # covers the visible glyphs. This helps in builds where per-char
        # rectangles are unavailable or imprecise.
        try:
            if pattern_str == getattr(self._phone_re, 'pattern', None) or self._phone_re.fullmatch(re.sub(r"\D", "", token)):
                # Use asymmetric padding for phone tokens: avoid expanding left side
                # (which would hide configured leading digits). Add a small right
                # padding and minimal left inset so the visible left_keep digits
                # remain uncovered even when char-level rects are unavailable.
                pad_right = max(3.0, redact_rect.width * 0.12)
                pad_left = min(1.0, redact_rect.width * 0.03)
                pad_y = max(1.0, redact_rect.height * 0.20)
                # Move left edge slightly to the right (pad_left) and expand right edge
                redact_rect = fitz.Rect(redact_rect.x0 + pad_left, redact_rect.y0 - pad_y, redact_rect.x1 + pad_right, redact_rect.y1 + pad_y)
            # ID tokens (CMND/CCCD) sometimes get their left digits covered by
            # padding when per-char rects are unavailable. Apply a mild asymmetric
            # padding similar to phones but smaller so left_keep digits remain visible.
            elif pattern_str == getattr(self._id_re, 'pattern', None) or self._id_re.fullmatch(re.sub(r"\D", "", token)):
                id_pad_right = max(2.0, redact_rect.width * 0.06)
                id_pad_left = min(0.8, redact_rect.width * 0.02)
                id_pad_y = max(1.0, redact_rect.height * 0.12)
                redact_rect = fitz.Rect(redact_rect.x0 + id_pad_left, redact_rect.y0 - id_pad_y, redact_rect.x1 + id_pad_right, redact_rect.y1 + id_pad_y)
            # After applying any padding, ensure the left edge of the redact rect
            # does not move left of the computed boundary that preserves the
            # configured left_keep digits. Use character boxes when available
            # for accuracy; otherwise fall back to a proportional per-digit width.
            try:
                digits = re.sub(r"\D", "", token)
                if digits:
                    # Prefer char-box based boundary when possible
                    left_boundary = None
                    if getattr(self, '_supports_chars', False):
                        try:
                            chars = page.get_text("chars")
                            digit_chars = [
                                (fitz.Rect(c[0], c[1], c[2], c[3]), c[4])
                                for c in chars
                                if fitz.Rect(c[0], c[1], c[2], c[3]).intersects(area) and c[4].isdigit()
                            ]
                            # mid region starts after left_keep digits
                            if len(digit_chars) > left_keep:
                                # start x of the first mid character
                                left_boundary = digit_chars[left_keep][0].x0
                        except Exception:
                            # fall back to proportional if char retrieval fails
                            left_boundary = None
                    if left_boundary is None:
                        # proportional per-digit width fallback
                        try:
                            char_w = area.width / max(1, len(digits))
                            left_boundary = area.x0 + char_w * left_keep
                        except Exception:
                            left_boundary = None
                    if left_boundary is not None:
                        # Ensure we don't start left of the boundary (i.e., we won't cover
                        # the configured left_keep digits). If padding incorrectly moved
                        # the rect leftward, clamp it to the boundary.
                        # Don't clamp so aggressively that we remove the mid-region.
                        # Allow left_boundary to be at most mid_rect.x0.
                        try:
                            left_boundary = min(left_boundary, mid_rect.x0)
                        except Exception:
                            pass
                        if redact_rect.x0 < left_boundary:
                            redact_rect = fitz.Rect(left_boundary, redact_rect.y0, redact_rect.x1, redact_rect.y1)
                    # Now compute a right boundary so we don't expand rightwards and
                    # cover the configured right_keep digits. Use the same char-box
                    # preference and proportional fallback.
                    right_boundary = None
                    if getattr(self, '_supports_chars', False):
                        try:
                            chars = page.get_text("chars")
                            digit_chars = [
                                (fitz.Rect(c[0], c[1], c[2], c[3]), c[4])
                                for c in chars
                                if fitz.Rect(c[0], c[1], c[2], c[3]).intersects(area) and c[4].isdigit()
                            ]
                            if len(digit_chars) > right_keep:
                                # x1 of the last mid character is at index len(digit_chars)-right_keep-1
                                idx = max(0, len(digit_chars) - right_keep - 1)
                                right_boundary = digit_chars[idx][0].x1
                        except Exception:
                            right_boundary = None
                    if right_boundary is None:
                        try:
                            char_w = area.width / max(1, len(digits))
                            right_boundary = area.x0 + char_w * (len(digits) - right_keep)
                        except Exception:
                            right_boundary = None
                    if right_boundary is not None:
                        # Don't clamp so aggressively that we remove the mid-region.
                        # Ensure right_boundary is at least mid_rect.x1.
                        try:
                            right_boundary = max(right_boundary, mid_rect.x1)
                        except Exception:
                            pass
                        # If padding expanded the rect too far right, clamp it so
                        # the last visible digit(s) are not covered.
                        if redact_rect.x1 > right_boundary:
                            redact_rect = fitz.Rect(redact_rect.x0, redact_rect.y0, right_boundary, redact_rect.y1)
            except Exception:
                # keep original if anything goes wrong here, but log
                logger.exception("Redactor._compute_and_record: left_keep boundary clamp failed for token=%r", token)
        except Exception:
            logger.exception("Redactor._compute_and_record: expanding phone redact rect failed")
        overlay = self._visible_token_overlay(token, pattern_str)
        # Clip redact rect to the page bounds to avoid add_redact_annot rejecting
        # out-of-bounds rectangles (padding can push a rect off the page).
        try:
            page_rect = page.rect
            redact_rect = redact_rect & page_rect
        except Exception:
            # If clipping fails for some reason, keep the original rect
            pass

        # If the clipped rect is empty, skip
        try:
            if redact_rect.is_empty or redact_rect.get_area() == 0:
                return 0
        except Exception:
            pass

        ok = self._draw_filled_rect(page, redact_rect)
        # Also try to add a redact annotation so we can apply redactions reliably
        added_annot = False
        try:
            page.add_redact_annot(redact_rect, fill=(0, 0, 0))
            added_annot = True
            logger.debug("Redactor._compute_and_record: add_redact_annot succeeded for %s", redact_rect)
        except Exception:
            # add_redact_annot may fail on some page types; attempt a safe fallback
            logger.exception("Redactor._compute_and_record: add_redact_annot failed for %s", redact_rect)
            try:
                # Try adding a slightly smaller clipped rect as a last resort
                small = fitz.Rect(max(redact_rect.x0, page.rect.x0), max(redact_rect.y0, page.rect.y0), min(redact_rect.x1, page.rect.x1), min(redact_rect.y1, page.rect.y1))
                if small.get_area() > 0:
                    page.add_redact_annot(small, fill=(0,0,0))
                    added_annot = True
                    logger.debug("Redactor._compute_and_record: fallback add_redact_annot succeeded for %s", small)
            except Exception:
                logger.exception("Redactor._compute_and_record: fallback add_redact_annot also failed for %s", redact_rect)

        # If we were able to add a redact annotation, try applying redactions on
        # this page immediately to remove the underlying text. Some PyMuPDF
        # builds/platforms behave inconsistently with doc-level apply_redactions;
        # applying per-page is a robust fallback.
        applied_now = False
        if added_annot:
            try:
                if hasattr(page, 'apply_redactions'):
                    page.apply_redactions()
                    applied_now = True
                    logger.debug("Redactor._compute_and_record: applied redactions on page %s for rect %s", page.number, redact_rect)
            except Exception:
                logger.exception("Redactor._compute_and_record: page.apply_redactions failed for page %s rect %s", page.number, redact_rect)

        # Record which method wrote the visible black box and whether a redact annot exists
        overlays.append((page.number, redact_rect, overlay, pattern_str, token, {'drawn': ok, 'annot_added': added_annot, 'applied_now': applied_now}))
        # Also print to console so the caller (user) can see which tokens were redacted
        try:
            # small, human-readable summary
            print(f"REDACTED: token={token!r} pattern={pattern_str!r} page={page.number} rect={redact_rect} overlay={overlay!r} drawn={ok} annot_added={added_annot} applied_now={applied_now}")
        except Exception:
            # avoid raising during redaction
            logger.exception("Redactor._compute_and_record: failed to print redaction summary for token=%r", token)
        return 1 if ok or added_annot or applied_now else 0

    def apply_rules(self, doc, rules, nlp_pipeline=None):
        total_redactions = 0
        overlays = []
        REQUIRE_NEAR_PERSON = os.environ.get("REQUIRE_NEAR_PERSON", "0") == "1" and (nlp_pipeline is not None)
        person_rects_by_page = self._gather_person_rects(doc, nlp_pipeline) if REQUIRE_NEAR_PERSON else {}
        # expose to instance for scoring heuristics
        try:
            self._person_rects = person_rects_by_page
        except Exception:
            self._person_rects = {}

        # Diagnostic: when DEBUG logging is enabled, enumerate phone-like matches found in page text
        # and report whether page.search_for returns any bounding areas for each token.
        try:
            if logger.isEnabledFor(10):  # logging.DEBUG == 10
                for pnum, page in enumerate(doc):
                    try:
                        page_text = page.get_text("text")
                    except Exception:
                        logger.exception("Diagnostic: failed to extract page_text for page %d", pnum)
                        continue
                    try:
                        for m in self._phone_re.finditer(page_text):
                            token = m.group(0)
                            try:
                                areas = page.search_for(token)
                                logger.debug("DIAG phone_match page=%d token=%r areas=%d", pnum, token, len(areas))
                            except Exception:
                                logger.exception("Diagnostic: page.search_for failed for token=%r on page %d", token, pnum)
                    except Exception:
                        logger.exception("Diagnostic: PHONE_REGEX finditer failed on page %d", pnum)
        except Exception:
            logger.exception("Diagnostic: phone-match diagnostic block failed")

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

    def _is_imei_context(self, page, area, token):
        """Return True when the token appears to be an IMEI/EMEI and a nearby label
        indicates it should not be redacted (e.g., the label contains 'IMEI'/'EMEI')."""
        if not getattr(self, '_imei_exclude_enabled', True):
            return False
        try:
            digits = re.sub(r"\D", "", token)
        except Exception:
            return False
        try:
            # Check blocks that intersect the area for IMEI labels
            blocks = page.get_text('blocks')
            for b in blocks:
                br = fitz.Rect(b[:4])
                if br.intersects(area):
                    txt = b[4].lower()
                    norm = re.sub(r"[\s:._\-()]+", "", txt)
                    # check both raw and normalized forms against configured variants
                    if any(v in txt for v in self._imei_variants) or any(v in norm for v in [x.replace(' ', '') for x in self._imei_variants]):
                        return True
            # Also check a small surrounding clip for label text
            clip = fitz.Rect(max(0, area.x0 - 40), max(0, area.y0 - 20), area.x1 + 40, area.y1 + 20)
            try:
                ctx = page.get_text(clip=clip).lower()
                norm2 = re.sub(r"[\s:._\-()]+", "", ctx)
                if any(v in ctx for v in self._imei_variants) or any(v in norm2 for v in [x.replace(' ', '') for x in self._imei_variants]):
                    return True
            except Exception:
                pass
            # If no explicit IMEI label found nearby, use a conservative length check
            # to determine whether the token itself is likely an IMEI/EMEI.
            if len(digits) >= getattr(self, '_imei_min_digits', 13):
                # IMEI/EMEI typically are 14-16 digits (commonly 15); treat tokens
                # longer than configured threshold as IMEI-like and skip redaction.
                return True
        except Exception:
            return False
        return False

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
                        # Skip IMEI/EMEI tokens explicitly
                        if self._is_imei_context(page, area, token):
                            logger.debug("Skipping IMEI-context token in _handle_sanitized_anchor: %r", token)
                            continue
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
            logger.debug("anchor_rect=%s anchor=%r sensitive_text=%r match=%s", an_rect, anchor, sensitive_text, bool(match))
            if match:
                token = match.group(0)
                for area in self._safe_search_for(page, token, clip=search_rect):
                    added += self._compute_and_record(page, area, token, pattern.pattern, overlays)
                    break
            else:
                # Fallback: sometimes clipped sensitive_text misses parts of a token
                # because of line-wrapping or strange layout. Search the whole page
                # for the pattern and redact any matches that appear to be on the
                # same line and to the right of the anchor rect.
                try:
                    page_text_full = page.get_text("text")
                    # variants to detect phone label mention in nearby text
                    phone_variants = ['điện thoại', 'sđt', 'số điện thoại', 'đt', 'dt', 'sdt', 'tel', 'phone', 'mobile', 'mobi', 'đthoai', 'dienthoai']
                    for m2 in pattern.finditer(page_text_full):
                        token2 = m2.group(0)
                        # check a small text window around the match for explicit phone labels
                        ctx_start = max(0, m2.start() - 40)
                        ctx_end = min(len(page_text_full), m2.end() + 10)
                        ctx = page_text_full[ctx_start:ctx_end].lower()
                        has_phone_label_nearby = any(v in ctx for v in phone_variants)
                        # Collect candidate areas and pick the best-scoring one instead of
                        # taking the first acceptable area. Scoring prefers areas that
                        # overlap phone-label blocks, are vertically close to the anchor,
                        # or intersect detected person rects (if present).
                        try:
                            candidates = list(page.search_for(token2))
                        except Exception:
                            candidates = []
                        # If exact search didn't find anything, try some robust fallbacks:
                        # - stripped whitespace version (tokens broken by linebreaks)
                        # - digits-only version
                        # - finally, fall back to using text block rects that contain the digits
                        if not candidates:
                            token_clean = re.sub(r"\s+", "", token2)
                            try:
                                if token_clean != token2:
                                    candidates = list(page.search_for(token_clean))
                            except Exception:
                                candidates = []
                        if not candidates:
                            digits_only = re.sub(r"\D", "", token2)
                            try:
                                if digits_only:
                                    # try searching the digit-only string (some PDFs store numbers without separators)
                                    candidates = list(page.search_for(digits_only))
                            except Exception:
                                pass
                        if not candidates:
                            # As a last resort, look through text blocks and use block rects that
                            # contain the digits/token (handles heavy line-wrapping / OCR splits).
                            try:
                                blocks = page.get_text('blocks')
                                for b in blocks:
                                    br = fitz.Rect(b[:4])
                                    btxt = b[4]
                                    if digits_only and re.sub(r"\D", "", btxt).find(digits_only) != -1:
                                        candidates.append(br)
                                    elif token_clean and token_clean and btxt.replace(" ", "").find(token_clean) != -1:
                                        candidates.append(br)
                            except Exception:
                                pass
                        best = None
                        best_score = -1.0
                        for area in candidates:
                            try:
                                mid_area_y_dbg = (area.y0 + area.y1) / 2.0
                                mid_an_y_dbg = (an_rect.y0 + an_rect.y1) / 2.0
                                dist_dbg = abs(mid_area_y_dbg - mid_an_y_dbg)
                            except Exception:
                                dist_dbg = 9999.0
                            logger.debug("fallback token=%r candidate area=%s mid_dist=%s has_phone_label_nearby=%s", token2, area, dist_dbg, has_phone_label_nearby)
                            # base score: prefer close vertical distance
                            score = max(0.0, 200.0 - dist_dbg)
                            # boost if label heuristics think it's correct
                            ok_label = self._is_label_token_ok(page, an_rect, area, pattern.pattern, token2)
                            if ok_label:
                                score += 200.0
                            if has_phone_label_nearby:
                                score += 100.0
                            # boost if the candidate overlaps a text block that contains phone keywords
                            try:
                                blocks = page.get_text('blocks')
                                for b in blocks:
                                    br = fitz.Rect(b[:4])
                                    if br.intersects(area):
                                        txt = b[4].lower()
                                        if any(v in txt for v in ['điện thoại', 'sđt', 'số điện thoại', 'đt', 'dt', 'sdt', 'tel', 'phone']):
                                            score += 150.0
                                            break
                            except Exception:
                                pass
                            # small boost if the area intersects any person rects (if available)
                            try:
                                # person rects may be gathered into self._person_cache by caller; optional
                                person_rects = getattr(self, '_person_rects', {})
                                pr = person_rects.get(page.number, [])
                                for r in pr:
                                    if r.intersects(area):
                                        score += 120.0
                                        break
                            except Exception:
                                pass
                            if score > best_score:
                                best_score = score
                                best = area
                        if best is not None and best_score > 0:
                            # Skip IMEI-context tokens
                            if self._is_imei_context(page, best, token2):
                                logger.debug("Skipping IMEI-context token in _apply_anchor_rects fallback: %r", token2)
                            else:
                                added += self._compute_and_record(page, best, token2, pattern.pattern, overlays)
                            # only redact first matching occurrence near this anchor rect
                            raise StopIteration
                except StopIteration:
                    pass
                except Exception:
                    logger.exception("Redactor._apply_anchor_rects: fallback page-wide search failed")
                # Targeted: if the anchor itself looks like a phone label, run PHONE_REGEX
                # across the whole page and redact matches near the anchor rect.
                try:
                    normalized_anchor = re.sub(r"[\s:._\-()]+", "", anchor or "").lower()
                    phone_anchor_variants = ['đt', 'dt', 'sđt', 'sdt', 'sốđiệnthoại', 'sodienthoai', 'sốđiệnthoạ i', 'sodienthoai']
                    if any(v in normalized_anchor for v in phone_anchor_variants):
                        page_text_full = page.get_text("text")
                        for m3 in self._phone_re.finditer(page_text_full):
                            token3 = m3.group(0)
                            for area in page.search_for(token3):
                                # check vertical proximity
                                mid_area_y = (area.y0 + area.y1) / 2.0
                                mid_an_y = (an_rect.y0 + an_rect.y1) / 2.0
                                if abs(mid_area_y - mid_an_y) <= 20:
                                    added += self._compute_and_record(page, area, token3, getattr(self._phone_re, 'pattern', None), overlays)
                                    raise StopIteration
                except StopIteration:
                    pass
                except Exception:
                    logger.exception("Redactor._apply_anchor_rects: targeted phone-anchor full-page search failed")
            try:
                anchor_text = page.get_text(clip=an_rect).strip()
            except Exception:
                anchor_text = ""
                logger.exception("Redactor._apply_anchor_rects: failed to get anchor text clip")
            match2 = pattern.search(anchor_text)
            logger.debug("anchor_rect=%s anchor=%r anchor_text=%r match2=%s", an_rect, anchor, anchor_text, bool(match2))
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
                # Skip IMEI tokens on page-wide pass
                if self._is_imei_context(page, area, token):
                    logger.debug("Skipping IMEI-context token in _page_wide_redact: %r", token)
                    continue
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

        # Normalize label text (remove whitespace and common punctuation) to catch compacted labels like 'sốđiện thoại' or 'ĐT'
        normalized_label = re.sub(r"[\s:.\-()]+", "", label_text)

        # Expanded phone label variants (diacritics-aware and ASCII approximations)
        phone_variants_in_label = [
            'điện thoại', 'sđt', 'số điện thoại', 'sđt:', 'đt', 'dt', 'sdt', 'sđt',
            'tel', 'phone', 'mobile', 'mobi', 'đthoai', 'dienthoai', 'đt:', 'đt.','đt,'
        ]
        # Check both original label_text and normalized compact form for many variants
        allow_phone_label = any(v in label_text for v in phone_variants_in_label) or any(v in normalized_label for v in [v.replace(' ', '') for v in phone_variants_in_label])
        allow_id_label = any(x in label_text for x in ['cmnd', 'căn cước', 'cccd', 'số cmnd', 'số cmt'])

        logger.debug("label_text=%r normalized_label=%r pattern_str=%r token=%r digits_only=%r same_line=%s to_right=%s allow_phone_label=%s allow_id_label=%s",
                     label_text, normalized_label, pattern_str, token, digits_only, same_line, to_right, allow_phone_label, allow_id_label)

        if (pattern_str == getattr(self._phone_re, 'pattern', None) or self._phone_re.fullmatch(digits_only)) and not allow_phone_label:
            return False
        if (pattern_str == getattr(self._id_re, 'pattern', None) or self._id_re.fullmatch(digits_only)) and not allow_id_label:
            return False
        return True

    def _compute_keep(self, pattern_str, token):
        digits = re.sub(r"\D", "", token)
        if (pattern_str == getattr(self._id_re, 'pattern', None) or self._id_re.fullmatch(digits)) and len(digits) >= 4:
            return self.config.get_keep("id")
        if (pattern_str == getattr(self._phone_re, 'pattern', None) or self._phone_re.fullmatch(digits)) and len(digits) >= 6:
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
            # Prefer configuration-driven keep counts when available
            if pattern_str == getattr(self._id_re, 'pattern', None) or self._id_re.fullmatch(digits):
                left_keep, right_keep = self.config.get_keep('id')
                # use >= so tokens with length equal to left+right still show left...right
                if len(digits) >= left_keep + right_keep and (left_keep > 0 or right_keep > 0):
                    left = digits[:left_keep] if left_keep > 0 else ''
                    right = digits[-right_keep:] if right_keep > 0 else ''
                    return f"{left}...{right}"
            if pattern_str == getattr(self._phone_re, 'pattern', None) or self._phone_re.fullmatch(digits):
                left_keep, right_keep = self.config.get_keep('phone')
                # enforce strict policy: show configured left/right even when token length == left+right
                if len(digits) >= left_keep + right_keep and (left_keep > 0 or right_keep > 0):
                    left = digits[:left_keep] if left_keep > 0 else ''
                    right = digits[-right_keep:] if right_keep > 0 else ''
                    return f"{left}...{right}"
        except Exception as e:
            logger.exception("Redactor._visible_token_overlay: formatting overlay failed")
        if len(digits) > 2:
            return f"{digits[0]}...{digits[-1]}"
        return digits

    def _draw_overlays(self, doc, overlays):
        for item in overlays:
            # overlays entries may now include meta info as the 6th element
            try:
                if len(item) == 5:
                    pnum, rect, text, pat, token = item
                    meta = {}
                else:
                    pnum, rect, text, pat, token, meta = item
            except Exception:
                logger.exception("Redactor._draw_overlays: unexpected overlay item format: %r", item)
                continue
            try:
                page = doc[pnum]
                fontsize = max(6, int(rect.height * 0.7))
                page.insert_textbox(rect, text, fontsize=fontsize, color=(1,1,1), align=1)
                logger.debug("Redactor._draw_overlays: inserted overlay text=%r on page=%s rect=%s meta=%r", text, pnum, rect, meta)
            except Exception:
                logger.exception("Redactor._draw_overlays: insert_textbox failed for page=%s rect=%s", pnum, rect)