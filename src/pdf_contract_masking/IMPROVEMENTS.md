# Improvements to reduce duplicated code and expensive calls

Observed: repeated calls to the same PyMuPDF APIs (page.get_text, page.search_for, page.draw_rect / fallbacks). This causes duplicated code, harder maintenance, and performance overhead.

Recommended changes (high level)
- Cache per-page text and search results to avoid repeated expensive calls.
- Centralize drawing/fallback logic (already present as _draw_filled_rect) — reuse it everywhere.
- Centralize token -> redact workflow (compute keep, compute redact rect, draw, record overlay).
- Replace repeated inline try/except blocks with helper functions that log errors consistently.
- Where patterns are applied repeatedly, pre-compile regexes and reuse them.

Examples and suggested helpers

- Add per-run (per apply_rules) caches and helpers:
```python
# python
def _get_page_text(self, page, cache):
    # cache: dict mapping page.number -> text
    if page.number in cache:
        return cache[page.number]
    try:
        txt = page.get_text("text") or ""
    except Exception as e:
        logger.exception("Failed to get page text for page %s", page.number)
        txt = ""
    cache[page.number] = txt
    return txt

def _search_cached(self, page, text, cache, clip=None):
    # cache: dict mapping (page.number, text, clip_repr) -> results
    key = (page.number, text, None if clip is None else (clip.x0, clip.y0, clip.x1, clip.y1))
    if key in cache:
        return cache[key]
    try:
        res = page.search_for(text) if clip is None else page.search_for(text, clip=clip)
    except Exception:
        logger.exception("search_for failed for text=%s on page %s", text, page.number)
        res = []
    cache[key] = res
    return res
```

- Consolidate token processing (deduplicates many blocks):
```python
# python
def _process_token(self, page, token, pattern_str, overlays, page_text_cache, search_cache):
    # returns 1 if redaction drawn, else 0
    # 1) locate areas for token using cached search
    areas = self._search_cached(page, token, search_cache)
    count = 0
    for area in areas:
        # optionally validate context using page text cache if needed
        left_keep, right_keep = self._compute_keep(pattern_str, token)
        redact_rect = self._get_mid_redact_rect(page, area, token, left_keep, right_keep)
        ok = self._draw_filled_rect(page, redact_rect)
        overlay = self._visible_token_overlay(token, pattern_str)
        overlays.append((page.number, redact_rect, overlay, pattern_str, token))
        if ok:
            count += 1
    return count
```

- Use these helpers inside `apply_rules` and other methods:
  - Create fresh caches at start of apply_rules:
    - page_text_cache = {}
    - search_cache = {}
  - Replace inline page.get_text and page.search_for calls with `_get_page_text` and `_search_cached`.
  - Replace repeated draw blocks with `_compute_and_record` or `_process_token`.

Why this helps
- Performance: avoids repeated text extraction and search_for calls which are O(page-content) and can be costly.
- Readability: fewer nested try/except blocks scattered across methods.
- Observability: single place to log errors with detailed context.
- Testability: helpers can be unit-tested in isolation.

Small operational notes
- Keep caches per run (do not persist across files) to limit memory usage.
- For text/word-level operations that rely on per-character boxes (`page.get_text("chars")`), guard against PyMuPDF versions that don't support "chars" and fallback to proportional split. Log the assertion (already added).
- Pre-compile regex patterns up-front where reused.

Follow-up
- I can apply a targeted refactor that:
  - Adds `_get_page_text` and `_search_cached` to `Redactor`.
  - Replaces a few hotspots in `redactor.py` (`_handle_sanitized_anchor`, `_apply_anchor_rects`, `_page_wide_redact`) to use the helpers.
  - Adds small benchmarks (timing) to `processor.py` to measure improvements.

If you want me to implement the refactor now, confirm and I'll update `src/pdf_contract_masking/redactor.py` (and any callers) accordingly.