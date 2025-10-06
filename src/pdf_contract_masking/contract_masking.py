import fitz  # PyMuPDF
import re
import os
import json
import hashlib
from tqdm import tqdm
import torch
# DÒNG SỬA LỖI: Thêm AutoTokenizer và AutoModelForTokenClassification vào đây
from transformers import pipeline, AutoTokenizer, AutoModelForTokenClassification

# --- PHẦN 1: TẢI MÔ HÌNH VÀ ĐỊNH NGHĨA CÁC HẰNG SỐ ---

def load_ner_model():
    """Tải và khởi tạo mô hình AI NER tiếng Việt từ Hugging Face."""
    print("Đang tải mô hình AI-NER từ Hugging Face (chỉ mất thời gian ở lần chạy đầu tiên)...")
    try:
        # Sử dụng mô hình PhoBERT mạnh mẽ và ổn định
        model_name = "vinai/phobert-base-v2"
        
        # Tải tokenizer và model riêng để có toàn quyền kiểm soát
        tokenizer = AutoTokenizer.from_pretrained(model_name)
        model = AutoModelForTokenClassification.from_pretrained(model_name)
        
        ner_pipeline = pipeline(
            "ner",
            model=model,
            tokenizer=tokenizer,
            device=0 if torch.cuda.is_available() else -1,
            aggregation_strategy="simple" # Gom các token lại thành từ hoàn chỉnh
        )
        print("Tải mô hình AI-NER hoàn tất.")
        return ner_pipeline
    except Exception as e:
        print(f"Lỗi khi tải mô hình từ Hugging Face: {e}")
        return None

# Các từ khóa và Regex
# Load customer keywords from config (fallback to sensible defaults)
try:
    _rc = load_redaction_config()
    CUSTOMER_KEYWORDS = _rc.get('customer_keywords', ['khách hàng', 'bên mua', 'bên b', 'bên được bảo hiểm', 'người mua'])
except Exception:
    CUSTOMER_KEYWORDS = ['khách hàng', 'bên mua', 'bên b', 'bên được bảo hiểm', 'người mua']
ID_REGEX = re.compile(r"(\b\d{9}\b|\b\d{12}\b)")
PHONE_REGEX = re.compile(r"(\b(?:84|0)\d{9}\b)")
KNOWLEDGE_BASE_FILE = "customer_redaction_rules.json"
REDACTION_CONFIG_FILE = "redaction_config.json"

def load_redaction_config():
    if os.path.exists(REDACTION_CONFIG_FILE):
        try:
            with open(REDACTION_CONFIG_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            pass
    # default
    return {
        "id": {"left_keep": 2, "right_keep": 2},
        "phone": {"left_keep": 4, "right_keep": 2}
    }

REDACTION_CONFIG = load_redaction_config()

# --- (Các phần code còn lại giữ nguyên như phiên bản cuối cùng) ---
# --- PHẦN 2: CÁC HÀM TIỆN ÍCH ---
def create_fingerprint(doc):
    fingerprint_text = ""
    if len(doc) > 0:
        page = doc[0]
        fingerprint_text += page.get_text("text", clip=fitz.Rect(0, 0, page.rect.width, 150))
    if not fingerprint_text: return None
    return hashlib.sha256(fingerprint_text.encode('utf-8')).hexdigest()


def sanitize_anchor_text(anchor: str) -> str:
        """Sanitize anchor text before saving to KB: remove or mask digit sequences (IDs/phones)
        so we do not store raw PII inside the knowledge base file.
        Examples:
            'Số CMND: 012345678' -> 'Số CMND: <ID>'
            'Số điện thoại: 0912345678' -> 'Số điện thoại: <PHONE>'
        """
        if not anchor:
                return anchor
        a = anchor
        # replace long digit sequences (9+ digits) as ID
        a = re.sub(r"\b\d{9,12}\b", "<ID>", a)
        # replace phone-like sequences (9-11 digits with optional country) as PHONE
        a = re.sub(r"\b(?:84|0)\d{8,10}\b", "<PHONE>", a)
        # fallback: replace any remaining 6+ digit sequences
        a = re.sub(r"\b\d{6,}\b", "<NUM>", a)
        return a

def load_knowledge_base():
    if os.path.exists(KNOWLEDGE_BASE_FILE):
        with open(KNOWLEDGE_BASE_FILE, 'r', encoding='utf-8') as f: return json.load(f)
    return {}

def save_knowledge_base(data):
    with open(KNOWLEDGE_BASE_FILE, 'w', encoding='utf-8') as f: json.dump(data, f, indent=4, ensure_ascii=False)

def find_text_positions(page, text_to_find):
    return page.search_for(text_to_find)

# --- PHẦN 3: CÁC CHẾ ĐỘ XỬ LÝ ---
def learn_customer_rules_with_ai(doc, nlp_pipeline):
    print("  -> Chế độ Học: Phân tích sâu bằng AI để tạo quy tắc cho khách hàng...")
    rules = []
    
    for page_num, page in enumerate(doc):
        full_text = page.get_text("text")
        if not full_text.strip(): continue
        # Optionally skip NER (fast rules-only mode) when env var RULES_ONLY=1 or nlp_pipeline is None
        skip_ner = os.environ.get('RULES_ONLY', '0') == '1' or nlp_pipeline is None
        person_names = []
        if not skip_ner:
            try:
                ner_results = nlp_pipeline(full_text)
                person_names = [entity['word'] for entity in ner_results if entity.get('entity_group') == 'PER']
            except Exception as e:
                print(f"    - NER pipeline failed or returned no results: {e}")
                person_names = []

        customer_rects = []
        # If NER found person names, prefer that
        if person_names:
            for name in set(person_names):
                name_rects = find_text_positions(page, name)
                for name_rect in name_rects:
                    check_rect = name_rect + (-200, -20, 200, 20)
                    nearby_text = page.get_text(clip=check_rect).lower()
                    if any(keyword in nearby_text for keyword in CUSTOMER_KEYWORDS):
                        print(f"    - AI xác định khách hàng: '{name}' trên trang {page_num + 1}")
                        customer_rects.append(name_rect)

        # Fallback: if NER didn't find persons, look for customer keywords and use them as anchors
        if not customer_rects:
            lowered = full_text.lower()
            for kw in CUSTOMER_KEYWORDS:
                if kw in lowered:
                    kw_rects = page.search_for(kw)
                    if kw_rects:
                        print(f"    - Tìm thấy từ khóa khách hàng '{kw}' trên trang {page_num + 1} (fallback)")
                        for r in kw_rects:
                            customer_rects.append(r)

        # If we couldn't find explicit customer anchors, we will still try to learn rules
        # from label patterns or standalone sensitive tokens (less precise but better than nothing).
        if not customer_rects:
            customer_rects = []  # keep empty but allow downstream label/token rules

        # Gather sensitive candidates by scanning words (more robust than search_for)
        words = page.get_text("words")  # list of tuples (x0, y0, x1, y1, "word", block_no, line_no, word_no)
        sensitive_words = []
        for w in words:
            w_text = w[4].strip()
            if ID_REGEX.fullmatch(w_text) or PHONE_REGEX.fullmatch(w_text):
                sensitive_words.append({'text': w_text, 'rect': fitz.Rect(w[0], w[1], w[2], w[3])})

        # If no sensitive words found via word-scan, fall back to regex on full_text
        if not sensitive_words:
            for m in ID_REGEX.finditer(full_text):
                sensitive_words.append({'text': m.group(0), 'rects': []})
            for m in PHONE_REGEX.finditer(full_text):
                sensitive_words.append({'text': m.group(0), 'rects': []})

        # Additional fallback: look for label patterns like 'Số CMND: 012345678' or 'Số điện thoại: 0912345678'
        label_patterns = [
            (re.compile(r"số\s*cmnd[:\s]*([0-9]{9,12})", re.IGNORECASE), ID_REGEX.pattern),
            (re.compile(r"số\s*điện\s*thoại[:\s]*([0-9]{9,12})", re.IGNORECASE), PHONE_REGEX.pattern),
            (re.compile(r"sđt[:\s]*([0-9]{9,12})", re.IGNORECASE), PHONE_REGEX.pattern),
        ]
        for lp, pat in label_patterns:
            for lm in lp.finditer(full_text):
                val = lm.group(1)
                if val:
                    # try to find the rect on the page
                    rects = page.search_for(val)
                    if rects:
                        raw_anchor = lm.group(0)[:40]
                        lower_raw = raw_anchor.lower()
                        money_keywords = ['số tiền', 'khoản vay', 'khoản', 'giá trị', 'thanh toán', 'số tiền (vnđ)']
                        # do not create ID/phone rules for money/loan labels
                        if any(k in lower_raw for k in money_keywords):
                            continue
                        rule_anchor = sanitize_anchor_text(raw_anchor)
                        if not rule_anchor or not rule_anchor.strip():
                            # avoid saving empty anchors which cause page-wide matches
                            continue
                        rule = {"page": page_num, "anchor": rule_anchor, "pattern": pat}
                        if rule not in rules:
                            rules.append(rule)
                            print(f"      -> Đã học quy tắc (label): Tìm '{rule_anchor}' rồi tìm số theo mẫu {pat}.")

        for customer_rect in (customer_rects if customer_rects else [None]):
            for s in sensitive_words:
                s_text = s['text'] if isinstance(s, dict) and 'text' in s else s
                # try to get rects from word scan, otherwise search in page
                s_rects = s.get('rects') if isinstance(s, dict) and s.get('rects') else page.search_for(s_text)
                for sensitive_rect in s_rects:
                    # If we have a customer_rect, use proximity; otherwise accept label-driven matches
                    if customer_rect is not None:
                        if abs(customer_rect.y0 - sensitive_rect.y0) >= 120:
                            continue

                    # choose an anchor: nearby words left of sensitive_rect or customer keyword or label
                    anchor = None
                    try:
                        # look for *whole words* left of the sensitive rect on the same line
                        left_rect = fitz.Rect(sensitive_rect.x0 - 300, sensitive_rect.y0 - 5, sensitive_rect.x0 - 1, sensitive_rect.y1 + 5)
                        # Use the word-level extraction (gives word tokens and their rects) and pick words intersecting left_rect
                        page_words = page.get_text("words")  # (x0,y0,x1,y1, "word", block_no, line_no, word_no)
                        nearby_words = [w[4].strip() for w in page_words if fitz.Rect(w[0], w[1], w[2], w[3]).intersects(left_rect)]
                        # sanitize: strip surrounding punctuation and remove tiny fragments (len <= 1)
                        strip_chars = " .,;:-_()[]\"'`"
                        nearby_words = [w.strip(strip_chars) for w in nearby_words if w and len(w.strip(strip_chars)) > 1]
                        if nearby_words:
                            # take up to last 3 whole words as the anchor
                            anchor = " ".join(nearby_words[-3:])
                            # verify anchor exists on the page as a contiguous substring; if not, drop it
                            try:
                                if not page.search_for(anchor):
                                    anchor = None
                            except Exception:
                                # if search_for fails for whatever reason, keep the anchor (best-effort)
                                pass
                    except Exception:
                        anchor = None

                    if not anchor:
                        for kw in CUSTOMER_KEYWORDS:
                            if kw in full_text.lower():
                                anchor = kw
                                break

                    pattern = ID_REGEX.pattern if ID_REGEX.search(s_text) else PHONE_REGEX.pattern
                    # avoid creating empty or money/loan anchors which lead to broad false positives
                    if not anchor or not str(anchor).strip():
                        continue
                    lower_anchor = str(anchor).lower()
                    money_keywords = ['số tiền', 'khoản vay', 'khoản', 'giá trị', 'thanh toán']
                    if any(k in lower_anchor for k in money_keywords):
                        # anchor indicates monetary field; skip creating phone/ID redaction rules for it
                        continue

                    rule_anchor = sanitize_anchor_text(anchor or "")
                    if not rule_anchor or not rule_anchor.strip():
                        continue
                    rule = {"page": page_num, "anchor": rule_anchor, "pattern": pattern}
                    if rule not in rules:
                        rules.append(rule)
                        print(f"      -> Đã học quy tắc (words): Tìm '{rule_anchor}' rồi tìm số theo mẫu {pattern}.")
    return rules

def apply_rules(doc, rules, nlp_pipeline=None):
    print("  -> Chế độ Tái sử dụng: Áp dụng quy tắc đã học...")
    total_redactions = 0
    overlays = []  # list of tuples (page_num, rect, overlay_text, pattern_str, token)

    # Optional strict mode: require detected person name proximity before redacting.
    REQUIRE_NEAR_PERSON = os.environ.get('REQUIRE_NEAR_PERSON', '0') == '1' and (nlp_pipeline is not None)
    person_rects_by_page = {}
    if REQUIRE_NEAR_PERSON:
        try:
            for pnum, page in enumerate(doc):
                txt = page.get_text("text")
                if not txt.strip():
                    person_rects_by_page[pnum] = []
                    continue
                try:
                    ner_res = nlp_pipeline(txt)
                except Exception:
                    ner_res = []
                names = [ent['word'] for ent in ner_res if ent.get('entity_group') == 'PER']
                rects = []
                for name in set(names):
                    try:
                        for r in page.search_for(name):
                            rects.append(r)
                    except Exception:
                        continue
                person_rects_by_page[pnum] = rects
        except Exception:
            person_rects_by_page = {}

    def is_near_person(page_num, area: fitz.Rect) -> bool:
        # If no strict mode, always allow
        if not REQUIRE_NEAR_PERSON:
            return True
        rects = person_rects_by_page.get(page_num, [])
        if not rects:
            return False
        # expand person rects slightly and check intersection
        for pr in rects:
            exp = fitz.Rect(pr.x0 - 200, pr.y0 - 30, pr.x1 + 200, pr.y1 + 30)
            if exp.intersects(area):
                return True
        return False

    def has_nearby_customer_keyword(page, area: fitz.Rect) -> bool:
        try:
            check = area + (-200, -20, 200, 20)
            nearby = page.get_text(clip=check).lower()
            return any(kw in nearby for kw in CUSTOMER_KEYWORDS)
        except Exception:
            return False

    def allow_redaction(page_num, page, area: fitz.Rect, anchor: str) -> bool:
        # Allow if anchor is present (learned rule tied to anchor)
        if anchor and anchor.strip():
            return True
        # Allow if there's an explicit nearby customer keyword (heuristic)
        if has_nearby_customer_keyword(page, area):
            return True
        # Allow if strict NER proximity mode is enabled and token is near a detected person
        if REQUIRE_NEAR_PERSON and is_near_person(page_num, area):
            return True
        return False

    def mask_token_display(token: str, pattern_str: str) -> str:
        # normalize to digits for masking
        digits = re.sub(r"\D", "", token)
        try:
            if pattern_str == ID_REGEX.pattern or ID_REGEX.fullmatch(digits):
                # show first 2 and last 2
                if len(digits) >= 4:
                    middle = "*" * (len(digits) - 4)
                    return digits[:2] + middle + digits[-2:]
            if pattern_str == PHONE_REGEX.pattern or PHONE_REGEX.fullmatch(digits):
                # show first 4 and last 2
                if len(digits) >= 6:
                    middle = "*" * (len(digits) - 6)
                    return digits[:4] + middle + digits[-2:]
        except Exception:
            pass
        # generic fallback: mask middle chars
        if len(token) > 2:
            return token[0] + ("*" * (len(token) - 2)) + token[-1]
        return "*" * len(token)

    def visible_token_overlay(token: str, pattern_str: str) -> str:
        # return a short visible representation (first/last digits) for overlay on black box
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
        except Exception:
            pass
        if len(digits) > 2:
            return f"{digits[0]}...{digits[-1]}"
        return digits
    def get_mid_redact_rect(page, area: fitz.Rect, token: str, left_keep: int, right_keep: int):
        # Try to use per-character bounding boxes when available
        digits = re.sub(r"\D", "", token)
        if not digits:
            return area
        try:
            chars = page.get_text('chars')  # list of tuples with bbox and char
            # select chars that intersect the token area and are digits
            digit_chars = [ (fitz.Rect(c[0],c[1],c[2],c[3]), c[4]) for c in chars if fitz.Rect(c[0],c[1],c[2],c[3]).intersects(area) and c[4].isdigit() ]
            if len(digit_chars) >= left_keep + right_keep + 1:
                # keep first/last as requested, redact the middle chars
                mid_chars = digit_chars[left_keep: len(digit_chars)-right_keep]
                if mid_chars:
                    # union rects of mid_chars
                    r0 = mid_chars[0][0]
                    for rc, ch in mid_chars[1:]:
                        r0 |= rc
                    return r0
        except Exception:
            pass
        # fallback: split area width proportionally
        try:
            char_w = area.width / max(1, len(digits))
            x0 = area.x0 + char_w * left_keep
            x1 = area.x0 + char_w * (len(digits) - right_keep)
            if x1 > x0 + 1:
                return fitz.Rect(x0, area.y0, x1, area.y1)
        except Exception:
            pass
        return area

    for rule in rules:
        page_num, anchor, pattern_str = rule['page'], rule['anchor'], rule['pattern']
        pattern = re.compile(pattern_str)
        if page_num < len(doc):
            page = doc[page_num]
            anchor_rects = page.search_for(anchor)
            # If anchor was sanitized (contains placeholders like <ID> or <PHONE>)
            # page.search_for won't find the literal string. Try to find the labeled
            # token by searching page text for the label followed by the number pattern.
            if anchor and not anchor_rects and any(x in anchor for x in ['<ID>', '<PHONE>', '<NUM>']):
                try:
                    page_text = page.get_text('text')
                    # derive a readable label from the sanitized anchor (e.g. 'Số CMND', 'Số điện thoại')
                    label_text = anchor.replace('<ID>', '').replace('<PHONE>', '').replace('<NUM>', '').strip()
                    if label_text:
                        # try to find the label rect(s) on the page
                        try:
                            label_rects = page.search_for(label_text)
                        except Exception:
                            label_rects = []

                        # fallback: try some small fuzzy variants if exact label search fails
                        if not label_rects:
                            alt = label_text.split()[:3]
                            if alt:
                                lbl = " ".join(alt)
                                try:
                                    label_rects = page.search_for(lbl)
                                except Exception:
                                    label_rects = []

                        # If we have label rects, only redact tokens that are near those rects
                        if label_rects:
                            pnum = pattern_str
                            # find candidate tokens using the number pattern in the page text
                            for m in re.finditer(pnum, page_text):
                                token = m.group(0)
                                token_rects = page.search_for(token)
                                for area in token_rects:
                                    # check refined intersection/proximity with any label rect
                                    nearby = False
                                    for lr in label_rects:
                                        try:
                                            label_text = page.get_text(clip=lr).lower()
                                        except Exception:
                                            label_text = ""

                                        # If label clearly indicates money/loan, do not treat it as a phone/ID label
                                        money_keywords = ['số tiền', 'khoản vay', 'khoản', 'giá trị', 'thanh toán']
                                        if any(k in label_text for k in money_keywords):
                                            # skip this label for phone/ID redaction decisions
                                            continue

                                        # prefer tokens that are on the same line and to the right of the label
                                        mid_area_y = (area.y0 + area.y1) / 2.0
                                        mid_lr_y = (lr.y0 + lr.y1) / 2.0
                                        same_line = abs(mid_area_y - mid_lr_y) <= 14
                                        to_right = area.x0 >= (lr.x1 - 2)
                                        if not (same_line and to_right):
                                            # not the inline/right-of-label layout we expect
                                            continue

                                        # ensure label text semantically matches the pattern we intend to redact
                                        allow_phone_label = any(x in label_text for x in ['điện thoại', 'sđt'])
                                        allow_id_label = any(x in label_text for x in ['cmnd', 'căn cước', 'cccd'])
                                        digits_only = re.sub(r"\D", "", token)
                                        if (pattern_str == PHONE_REGEX.pattern or PHONE_REGEX.fullmatch(digits_only)) and not allow_phone_label:
                                            continue
                                        if (pattern_str == ID_REGEX.pattern or ID_REGEX.fullmatch(digits_only)) and not allow_id_label:
                                            continue

                                        # If we reach here, this token is inline/right-of the label and semantically permitted
                                        nearby = True
                                        break
                                    if not nearby:
                                        continue

                                    # compute how many digits to keep
                                    digits = re.sub(r"\D", "", token)
                                    if (pattern_str == ID_REGEX.pattern or ID_REGEX.fullmatch(digits)) and len(digits) >= 4:
                                        cfg = REDACTION_CONFIG.get('id', {})
                                        left_keep = int(cfg.get('left_keep', 2))
                                        right_keep = int(cfg.get('right_keep', 2))
                                    elif (pattern_str == PHONE_REGEX.pattern or PHONE_REGEX.fullmatch(digits)) and len(digits) >= 6:
                                        cfg = REDACTION_CONFIG.get('phone', {})
                                        left_keep = int(cfg.get('left_keep', 4))
                                        right_keep = int(cfg.get('right_keep', 2))
                                    else:
                                        left_keep, right_keep = 0, 0

                                    redact_rect = get_mid_redact_rect(page, area, token, left_keep, right_keep)
                                    overlay = visible_token_overlay(token, pattern_str)
                                    if allow_redaction(page_num, page, redact_rect, anchor):
                                        try:
                                            page.draw_rect(redact_rect, color=(0, 0, 0), fill=(0, 0, 0))
                                        except Exception:
                                            try:
                                                s2 = page.new_shape()
                                                s2.draw_rect(redact_rect)
                                                s2.finish(fill=(0,0,0))
                                                s2.commit()
                                            except Exception:
                                                page.add_redact_annot(redact_rect, fill=(0, 0, 0))
                                        overlays.append((page_num, redact_rect, overlay, pattern_str, token))
                                        total_redactions += 1
                        # else: if we couldn't find the label on page, fall through and let other anchors/rules handle it
                except Exception:
                    pass
            if anchor and anchor_rects:
                matched_any = False
                for an_rect in anchor_rects:
                    # primary: look to the right of the anchor (typical layout)
                    search_rect = fitz.Rect(an_rect.x1, an_rect.y0 - 5, an_rect.x1 + 200, an_rect.y1 + 5)
                    sensitive_text = page.get_text(clip=search_rect).strip()
                    match = pattern.search(sensitive_text)
                    if match:
                        token = match.group(0)
                        masked = mask_token_display(token, pattern_str)
                        redaction_areas = page.search_for(token, clip=search_rect)
                        def get_mid_redact_rect(page, area: fitz.Rect, token: str, left_keep: int, right_keep: int):
                            # Try to use per-character bounding boxes when available
                            digits = re.sub(r"\D", "", token)
                            if not digits:
                                return area
                            try:
                                chars = page.get_text('chars')  # list of tuples with bbox and char
                                # select chars that intersect the token area and are digits
                                digit_chars = [ (fitz.Rect(c[0],c[1],c[2],c[3]), c[4]) for c in chars if fitz.Rect(c[0],c[1],c[2],c[3]).intersects(area) and c[4].isdigit() ]
                                if len(digit_chars) >= left_keep + right_keep + 1:
                                    # keep first/last as requested, redact the middle chars
                                    mid_chars = digit_chars[left_keep: len(digit_chars)-right_keep]
                                    if mid_chars:
                                        # union rects of mid_chars
                                        r0 = mid_chars[0][0]
                                        for rc, ch in mid_chars[1:]:
                                            r0 |= rc
                                        return r0
                            except Exception:
                                pass
                            # fallback: split area width proportionally
                            try:
                                char_w = area.width / max(1, len(digits))
                                x0 = area.x0 + char_w * left_keep
                                x1 = area.x0 + char_w * (len(digits) - right_keep)
                                if x1 > x0 + 1:
                                    return fitz.Rect(x0, area.y0, x1, area.y1)
                            except Exception:
                                pass
                            return area

                        for area in redaction_areas:
                            # compute how many digits to keep at sides
                            digits = re.sub(r"\D", "", token)
                            if (pattern_str == ID_REGEX.pattern or ID_REGEX.fullmatch(digits)) and len(digits) >= 4:
                                cfg = REDACTION_CONFIG.get('id', {})
                                left_keep = int(cfg.get('left_keep', 2))
                                right_keep = int(cfg.get('right_keep', 2))
                            elif (pattern_str == PHONE_REGEX.pattern or PHONE_REGEX.fullmatch(digits)) and len(digits) >= 6:
                                cfg = REDACTION_CONFIG.get('phone', {})
                                left_keep = int(cfg.get('left_keep', 4))
                                right_keep = int(cfg.get('right_keep', 2))
                            else:
                                left_keep, right_keep = 0, 0

                            redact_rect = get_mid_redact_rect(page, area, token, left_keep, right_keep)
                            overlay = visible_token_overlay(token, pattern_str)
                            if allow_redaction(page_num, page, redact_rect, anchor):
                                try:
                                    page.draw_rect(redact_rect, color=(0, 0, 0), fill=(0, 0, 0))
                                except Exception:
                                    try:
                                        s2 = page.new_shape()
                                        s2.draw_rect(redact_rect)
                                        s2.finish(fill=(0,0,0))
                                        s2.commit()
                                    except Exception:
                                        page.add_redact_annot(redact_rect, fill=(0, 0, 0))
                                overlays.append((page_num, redact_rect, overlay, pattern_str, token))
                                total_redactions += 1
                        matched_any = True
                        continue

                    # second: sometimes the anchor contains the token (e.g. 'Số điện thoại: 0912...')
                    anchor_text = page.get_text(clip=an_rect).strip()
                    match2 = pattern.search(anchor_text)
                    if match2:
                        token = match2.group(0)
                        masked = mask_token_display(token, pattern_str)
                        redaction_areas = page.search_for(token, clip=an_rect)
                        for area in redaction_areas:
                            # compute mid redact rect for this area
                            digits = re.sub(r"\D", "", token)
                            if (pattern_str == ID_REGEX.pattern or ID_REGEX.fullmatch(digits)) and len(digits) >= 4:
                                cfg = REDACTION_CONFIG.get('id', {})
                                left_keep = int(cfg.get('left_keep', 2))
                                right_keep = int(cfg.get('right_keep', 2))
                            elif (pattern_str == PHONE_REGEX.pattern or PHONE_REGEX.fullmatch(digits)) and len(digits) >= 6:
                                cfg = REDACTION_CONFIG.get('phone', {})
                                left_keep = int(cfg.get('left_keep', 4))
                                right_keep = int(cfg.get('right_keep', 2))
                            else:
                                left_keep, right_keep = 0, 0
                            redact_rect = get_mid_redact_rect(page, area, token, left_keep, right_keep)
                            overlay = visible_token_overlay(token, pattern_str)
                            if allow_redaction(page_num, page, redact_rect, anchor):
                                try:
                                    page.draw_rect(redact_rect, color=(0,0,0), fill=(0,0,0))
                                except Exception:
                                    try:
                                        s4 = page.new_shape()
                                        s4.draw_rect(redact_rect)
                                        s4.finish(fill=(0,0,0))
                                        s4.commit()
                                    except Exception:
                                        page.add_redact_annot(redact_rect, fill=(0,0,0))
                                overlays.append((page_num, redact_rect, overlay, pattern_str, token))
                                total_redactions += 1
                        matched_any = True
                        continue

                # if none of the anchor rects matched, avoid doing a page-wide blind search
                # by default because it causes many false positives (redacting numbers
                # that are not related to the customer). To enable the old behavior set
                # environment variable ALLOW_PAGE_WIDE_FALLBACK=1.
                if not matched_any:
                    if os.environ.get('ALLOW_PAGE_WIDE_FALLBACK', '0') != '1':
                        # skip aggressive page-wide fallback to favor precision
                        continue
                    page_text = page.get_text("text")
                    for m in pattern.finditer(page_text):
                        token = m.group(0)
                        masked = mask_token_display(token, pattern_str)
                        redaction_areas = page.search_for(token)
                        for area in redaction_areas:
                            # compute mid redact rect for this area
                            digits = re.sub(r"\D", "", token)
                            if (pattern_str == ID_REGEX.pattern or ID_REGEX.fullmatch(digits)) and len(digits) >= 4:
                                cfg = REDACTION_CONFIG.get('id', {})
                                left_keep = int(cfg.get('left_keep', 2))
                                right_keep = int(cfg.get('right_keep', 2))
                            elif (pattern_str == PHONE_REGEX.pattern or PHONE_REGEX.fullmatch(digits)) and len(digits) >= 6:
                                cfg = REDACTION_CONFIG.get('phone', {})
                                left_keep = int(cfg.get('left_keep', 4))
                                right_keep = int(cfg.get('right_keep', 2))
                            else:
                                left_keep, right_keep = 0, 0
                            redact_rect = get_mid_redact_rect(page, area, token, left_keep, right_keep)
                            overlay = visible_token_overlay(token, pattern_str)
                            # For page-wide fallback, anchor variable may not be defined here; pass ''
                            if allow_redaction(page_num, page, redact_rect, ''):
                                try:
                                    page.draw_rect(redact_rect, color=(0,0,0), fill=(0,0,0))
                                except Exception:
                                    try:
                                        s5 = page.new_shape()
                                        s5.draw_rect(redact_rect)
                                        s5.finish(fill=(0,0,0))
                                        s5.commit()
                                    except Exception:
                                        page.add_redact_annot(redact_rect, fill=(0,0,0))
                                overlays.append((page_num, redact_rect, overlay, pattern_str, token))
                                total_redactions += 1
            else:
                # Fallback: search entire page text for pattern and redact all matches
                page_text = page.get_text("text")
                for m in pattern.finditer(page_text):
                    token = m.group(0)
                    masked = mask_token_display(token, pattern_str)
                    redaction_areas = page.search_for(token)
                    for area in redaction_areas:
                            digits = re.sub(r"\D", "", token)
                            if (pattern_str == ID_REGEX.pattern or ID_REGEX.fullmatch(digits)) and len(digits) >= 4:
                                cfg = REDACTION_CONFIG.get('id', {})
                                left_keep = int(cfg.get('left_keep', 2))
                                right_keep = int(cfg.get('right_keep', 2))
                            elif (pattern_str == PHONE_REGEX.pattern or PHONE_REGEX.fullmatch(digits)) and len(digits) >= 6:
                                cfg = REDACTION_CONFIG.get('phone', {})
                                left_keep = int(cfg.get('left_keep', 4))
                                right_keep = int(cfg.get('right_keep', 2))
                            else:
                                left_keep, right_keep = 0, 0
                            redact_rect = get_mid_redact_rect(page, area, token, left_keep, right_keep)
                            overlay = visible_token_overlay(token, pattern_str)
                            if allow_redaction(page_num, page, redact_rect, ''):
                                try:
                                    page.draw_rect(redact_rect, color=(0,0,0), fill=(0,0,0))
                                except Exception:
                                    try:
                                        s6 = page.new_shape()
                                        s6.draw_rect(redact_rect)
                                        s6.finish(fill=(0,0,0))
                                        s6.commit()
                                    except Exception:
                                        page.add_redact_annot(redact_rect, fill=(0,0,0))
                                overlays.append((page_num, redact_rect, overlay, pattern_str, token))
                                total_redactions += 1
    # We draw filled rects directly (no apply_redactions)

    # Draw overlays (white text) centered in each redaction rect so they appear on top
    for pnum, rect, text, pat, token in overlays:
        try:
            page = doc[pnum]
            # If this is an ID pattern, draw two small white boxes on left/right and write black digits
            digits = re.sub(r"\D", "", token)
            if pat == ID_REGEX.pattern or ID_REGEX.fullmatch(digits):
                # show first 2 and last 2 as a centered white overlay (e.g. '01...78')
                try:
                    overlay_text = f"{digits[:2]}...{digits[-2:]}" if len(digits) >= 4 else digits
                except Exception:
                    overlay_text = digits
                fontsize = max(6, int(rect.height * 0.7))
                try:
                    page.insert_textbox(rect, overlay_text, fontsize=fontsize, color=(1, 1, 1), align=1)
                except Exception:
                    pass
            else:
                # default: centered white overlay text
                fontsize = max(6, int(rect.height * 0.7))
                page.insert_textbox(rect, text, fontsize=fontsize, color=(1, 1, 1), align=1)
        except Exception:
            # ignore overlay drawing errors
            pass

    return total_redactions

# --- PHẦN 4: HÀM ĐIỀU PHỐI CHÍNH ---
def process_pdf_final(input_pdf, output_pdf, nlp_pipeline, knowledge_base):
    try:
        doc = fitz.open(input_pdf)
        print(f"--- Đang xử lý file: {input_pdf} ---")
        fingerprint = create_fingerprint(doc)
        if fingerprint and fingerprint in knowledge_base:
            total_redactions = apply_rules(doc, knowledge_base[fingerprint], nlp_pipeline)
        else:
            new_rules = learn_customer_rules_with_ai(doc, nlp_pipeline)
            if new_rules:
                total_redactions = apply_rules(doc, new_rules, nlp_pipeline)
                if fingerprint:
                    # sanitize anchors defensively before persisting KB
                    sanitized_rules = []
                    for r in new_rules:
                        r2 = r.copy()
                        r2['anchor'] = sanitize_anchor_text(r2.get('anchor', ''))
                        sanitized_rules.append(r2)
                    knowledge_base[fingerprint] = sanitized_rules
                    print(f"  -> Đã học và lưu bộ quy tắc mới với ID: {fingerprint[:10]}...")
            else:
                total_redactions = 0
        if total_redactions > 0:
            doc.save(output_pdf, garbage=4, deflate=True, clean=True)
            print(f"Đã che {total_redactions} thông tin. Đã lưu vào: {output_pdf}\n")
        else:
            print("Không tìm thấy thông tin cần che của khách hàng.\n")
        doc.close()
    except Exception as e:
        print(f"Lỗi khi xử lý file {input_pdf}: {e}\n")

# --- PHẦN 5: THỰC THI ---
if __name__ == "__main__":
    # Allow a fast, rules-only mode (no model download) by setting RULES_ONLY=1
    if os.environ.get('RULES_ONLY', '0') == '1':
        print('Chạy ở chế độ RULES_ONLY=1: bỏ qua tải mô hình NER, dùng quy tắc và regex thay thế (nhanh).')
        nlp = None
    else:
        nlp = load_ner_model()

    knowledge_base = load_knowledge_base()
    # Always proceed with processing; learn_customer_rules_with_ai accepts nlp_pipeline=None
    output_directory = "hop_dong_da_che_AI_Final"
    os.makedirs(output_directory, exist_ok=True)
    pdf_files = [f for f in os.listdir('./contract') if f.lower().endswith('.pdf') and not f.startswith("che_")]

    if not pdf_files:
        print("Không tìm thấy file PDF nào để xử lý.")
    else:
        print(f"Tìm thấy {len(pdf_files)} file PDF. Bắt đầu xử lý...")
        for filename in tqdm(pdf_files, desc="Tổng tiến trình"):
            input_path = os.path.join('./contract', filename)
            output_filename = os.path.join(output_directory, f"che_{filename}")
            process_pdf_final(input_path, output_filename, nlp, knowledge_base)

        save_knowledge_base(knowledge_base)
        print("--- Hoàn tất! Đã cập nhật cơ sở tri thức. ---")