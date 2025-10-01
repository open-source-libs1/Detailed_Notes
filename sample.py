


def _json_loads_relaxed(raw: Any) -> Any:
    """Parses JSON with tolerance for double-encoded, escaped, or newline-padded content.

    Strategy:
      • Non-strings are returned unchanged.
      • For strings, try a sequence of sanitized candidates:
          1) original stripped
          2) remove CR/LF
          3) collapse multi-backslashes (e.g., '\\\\' → '\\')
          4) unescape quotes ( '\\"' → '"' )
          5) **AGGRESSIVE**: decode escapes via `unicode_escape`
        For each candidate, attempt up to 3 json.loads passes (unwrap double encoding).
      • If any candidate yields a non-string JSON value, return it.
      • Otherwise, if we decoded at least once to a string, return the last decoded string.
      • If all attempts fail, return the original input.
    """
    if not isinstance(raw, str):
        return raw

    base = raw.strip()
    candidates: List[str] = [base]

    # 1) remove CR/LF
    no_newlines = base.replace("\n", "").replace("\r", "")
    if no_newlines not in candidates:
        candidates.append(no_newlines)

    # 2) collapse multi backslashes
    collapsed = re.sub(r"\\{2,}", r"\\", no_newlines)
    if collapsed not in candidates:
        candidates.append(collapsed)

    # 3) unescape quotes
    unescape_quotes = collapsed.replace('\\"', '"')
    if unescape_quotes not in candidates:
        candidates.append(unescape_quotes)

    # 4) AGGRESSIVE: decode escape sequences (e.g., \\\" -> \", \\n -> newline)
    try:
        decoded_escape = no_newlines.encode("utf-8", "backslashreplace").decode("unicode_escape")
        # Keep it on one line for JSON parsing
        decoded_escape = decoded_escape.replace("\n", "").replace("\r", "")
        if decoded_escape not in candidates:
            candidates.append(decoded_escape)
    except Exception:
        pass

    last_str: Any = None
    for cand in candidates:
        parsed, ok = _try_json_unwrap(cand)
        if ok:
            return parsed
        if isinstance(parsed, str):
            last_str = parsed

    return last_str if last_str is not None else raw




##############################################



def test_backslashes_and_newlines_strong(self):
    s = '{\\\\\\"k\\\\\\":1}\\n'  # -> {\\\"k\\\":1}\n at runtime
    self.assertEqual(_json_loads_relaxed(s), {"k": 1})
