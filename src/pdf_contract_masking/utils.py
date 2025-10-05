def mask_text(text: str, keep_last: int = 4) -> str:
    """Return text where all but the last `keep_last` characters are replaced with `*`.

    Examples:
        mask_text("1234567890") -> "******7890"
    """
    if text is None:
        return ""
    if keep_last < 0:
        raise ValueError("keep_last must be >= 0")
    n = len(text)
    if keep_last == 0:
        return "*" * n
    if n <= keep_last:
        return text
    return "*" * (n - keep_last) + text[-keep_last:]
