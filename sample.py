def _json_loads_relaxed(raw: str) -> Any:
    """
    Parse `raw` as JSON, tolerating double-encoded strings (up to 3 passes).
    If parsing ultimately fails after at least one successful pass, return the
    last successfully parsed value; otherwise return the original string.
    """
    text = raw
    last_parsed = None
    for _ in range(3):
        try:
            parsed = json.loads(text)
            last_parsed = parsed
        except Exception:
            # If we've parsed at least once, return that; else fall back to raw
            return last_parsed if last_parsed is not None else raw
        if isinstance(parsed, str):
            # It was a JSON string whose content might itself be JSON; try again.
            text = parsed
            continue
        # Parsed into a non-string (dict/list/number/bool/null) -> done.
        return parsed
    # Exhausted attempts: return last successful parse if any, else raw
    return last_parsed if last_parsed is not None else raw
