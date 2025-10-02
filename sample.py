
def _salvage_payloads(text: str) -> Iterator[Jsonable]:
    """Extract `payload` objects from malformed outer body text.

    Handles both `"payload":"{...}"` and `"payload":{...}`. Robust to escaped
    quotes (`\"`) inside the quoted case by using an escape-aware brace matcher.
    """
    def find_matching_brace(s: str, start: int) -> Optional[int]:
        """Return index of the matching '}' for the '{' at `start`, or None.

        The scanner:
          - Treats quotes inside strings correctly (handles `\"`).
          - When NOT in a string, ignores a quote that is escaped by an odd
            number of preceding backslashes (so `\"` outside doesn't flip modes).
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
                    # Count consecutive backslashes immediately before this quote
                    bs = 0
                    k = i - 1
                    while k >= 0 and s[k] == "\\":
                        bs += 1
                        k -= 1
                    if bs % 2 == 0:  # unescaped quote -> enter string
                        in_str = True
                    # else: escaped quote outside string -> ignore
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

        # Move to start of the value; allow whitespace and an optional opening quote.
        j = colon + 1
        while j < n and text[j] in " \t\r\n":
            j += 1
        if j < n and text[j] == '"':
            j += 1
            while j < n and text[j] in " \t\r\n":
                j += 1

        # Hunt forward to the next '{' and slice a balanced object.
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
