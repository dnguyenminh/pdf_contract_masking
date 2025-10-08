import re
from pdf_contract_masking.config import RedactionConfig
from pdf_contract_masking.redactor import Redactor


def test_phone_overlay_respects_config():
    cfg = RedactionConfig()
    r = Redactor(cfg)
    # example Vietnamese phone with country code 84 prefix
    token = '84948749411'
    # pattern_str used by code is the compiled pattern's pattern attribute
    pat = getattr(r._phone_re, 'pattern', None)
    overlay = r._visible_token_overlay(token, pat)
    # derive expected from config so test adapts to config changes
    left_keep, right_keep = cfg.get_keep('phone')
    digits = re.sub(r"\D", "", token)
    if len(digits) >= left_keep + right_keep and (left_keep > 0 or right_keep > 0):
        expected = f"{digits[:left_keep]}...{digits[-right_keep:]}"
    elif len(digits) > 2:
        expected = f"{digits[0]}...{digits[-1]}"
    else:
        expected = digits
    assert overlay == expected


def test_id_overlay_respects_config():
    cfg = RedactionConfig()
    r = Redactor(cfg)
    token = '38123482'
    pat = getattr(r._id_re, 'pattern', None)
    overlay = r._visible_token_overlay(token, pat)
    # configured id left_keep=2, right_keep=2 -> expect '38...82'
    assert overlay == '38...82'


def test_short_phone_overlay_behaviour():
    cfg = RedactionConfig()
    r = Redactor(cfg)
    token = '8412'  # only 4 digits
    pat = getattr(r._phone_re, 'pattern', None)
    overlay = r._visible_token_overlay(token, pat)
    # derive expected from config so test adapts to config changes
    left_keep, right_keep = cfg.get_keep('phone')
    digits = re.sub(r"\D", "", token)
    if len(digits) >= left_keep + right_keep and (left_keep > 0 or right_keep > 0):
        expected = f"{digits[:left_keep]}...{digits[-right_keep:]}"
    elif len(digits) > 2:
        expected = f"{digits[0]}...{digits[-1]}"
    else:
        expected = digits
    assert overlay == expected
