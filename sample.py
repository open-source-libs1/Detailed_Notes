def _salvage_payloads(text: str) -> Iterator[Jsonable]:
    """Extract `payload` objects from a malformed body text.

    Explanation:
        When the outer body string is broken JSON but contains embedded
        `"payload":"{...}"` (quoted object) or `"payload":{...}` (unquoted object),
        this function finds each payload value and returns the parsed object.

        IMPORTANT: For the **quoted** case we first extract the quoted substring
        with proper escape-aware scanning and then parse that substring with
        `_loads_multipass`. For the **unquoted** case we locate the next `{` and
        slice the balanced `{...}` using a small brace matcher.

    Args:
        text: Malformed outer body string (still a str after _loads_multipass).

    Returns:
        Iterator of parsed payload objects (usually dicts).

    Example:
        >>> list(_salvage_payloads('"payload":"{\\"a\\":1}","x":0,"payload":{"b":2}'))
        [{'a': 1}, {'b': 2}]
    """
    def find_matching_brace(s: str, start: int) -> int | None:
        """Return index of matching '}' for the '{' at `start` or None if unbalanced.

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

    i = 0
    key_literal = '"payload"'
    while True:
        key_idx = text.find(key_literal, i)
        if key_idx == -1:
            return
        colon = text.find(":", key_idx + len(key_literal))
        if colon == -1:
            return

        # Advance to start of the value
        j = colon + 1
        while j < len(text) and text[j] in " \t\r\n":
            j += 1

        # CASE 1: Quoted payload value:  "payload":"{ ... }"
        if j < len(text) and text[j] == '"':
            j += 1  # enter quoted region (value begins here)
            start = j
            esc = False
            k = j
            while k < len(text):
                ch = text[k]
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':  # closing quote of the value
                    break
                k += 1
            # If no closing quote, skip this occurrence
            if k >= len(text) or text[k] != '"':
                i = key_idx + len(key_literal)
                continue

            # Extract quoted substring (without the outer quotes)
            inner = text[start:k]
            parsed = _loads_multipass(inner)
            if isinstance(parsed, (dict, list)):
                yield parsed
            i = k + 1  # continue after closing quote
            continue

        # CASE 2: Unquoted payload object: "payload":{ ... }
        # Hunt to first '{' after colon and slice a balanced object
        obj_start = text.find("{", j)
        if obj_start == -1:
            i = key_idx + len(key_literal)
            continue
        obj_end = find_matching_brace(text, obj_start)
        if obj_end is None:
            i = key_idx + len(key_literal)
            continue

        parsed = _loads_multipass(text[obj_start : obj_end + 1])
        if isinstance(parsed, (dict, list)):
            yield parsed
        i = obj_end + 1
