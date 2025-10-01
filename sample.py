def _salvage_payloads(text: str) -> Iterator[Jsonable]:
    """Extract `payload` objects from a malformed body text.

    Explanation:
        Handles both `"payload":"{...}"` (quoted) and `"payload":{...}` (unquoted)
        even when the outer JSON is broken (e.g., inner quotes are not escaped).
        We DO NOT try to parse the quoted string boundary; instead we jump to the
        next '{' and slice the balanced object with a quote/escape-aware matcher.

    Args:
        text: Malformed outer body string (still a str after _loads_multipass).

    Returns:
        Iterator of parsed payload objects (usually dicts).

    Example:
        >>> list(_salvage_payloads('"payload":"{\\"a\\":1}","x":0,"payload":{"b":2}'))
        [{'a': 1}, {'b': 2}]
    """
    def find_matching_brace(s: str, start: int) -> int | None:
        """Index of matching '}' for '{' at `start`, or None if unbalanced.

        Tracks quotes and escapes so braces inside strings don't affect depth.
        """
        depth = 0
        i = start
        in_str = False
        esc = False
        while i < len(s):
            ch = s[i]
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
            else:
                if ch == '"':
                    in_str = True
                elif ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0:
                        return i
            i += 1
        return None

    key = '"payload"'
    i = 0
    n = len(text)
    while True:
        k = text.find(key, i)
        if k == -1:
            return
        colon = text.find(":", k + len(key))
        if colon == -1:
            return

        # Move to start of value; allow whitespace and an optional opening quote.
        j = colon + 1
        while j < n and text[j] in " \t\r\n":
            j += 1
        if j < n and text[j] == '"':
            j += 1
            while j < n and text[j] in " \t\r\n":
                j += 1

        # Be tolerant: hunt forward to the next '{'
        obj_start = text.find("{", j)
        if obj_start == -1:
            i = k + len(key)
            continue
        obj_end = find_matching_brace(text, obj_start)
        if obj_end is None:
            i = k + len(key)
            continue

        fragment = text[obj_start : obj_end + 1]
        parsed = _loads_multipass(fragment)
        if isinstance(parsed, (dict, list)):
            yield parsed

        i = obj_end + 1
