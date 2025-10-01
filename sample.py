

def _salvage_payloads(text: str) -> Iterator[Jsonable]:
    ...
    def _find_matching_brace(s: str, start: int) -> int | None:
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

    def _iter_payload_objects(raw: str) -> Iterator[str]:
        i = 0
        while True:
            key_idx = raw.find('"payload"', i)
            if key_idx == -1:
                return
            colon = raw.find(":", key_idx + len('"payload"'))
            if colon == -1:
                return

            # Start scanning after the colon
            j = colon + 1

            # Skip whitespace, then an optional opening quote, then whitespace again
            while j < len(raw) and raw[j] in " \t\r\n":
                j += 1
            if j < len(raw) and raw[j] == '"':
                j += 1
                while j < len(raw) and raw[j] in " \t\r\n":
                    j += 1

            # Be *tolerant*: if it's not '{' yet, hunt forward to the next '{'
            if j >= len(raw) or raw[j] != "{":
                k = raw.find("{", j)
                if k == -1:
                    # No object here; continue from after the key to seek the next payload
                    i = key_idx + len('"payload"')
                    continue
                j = k

            end = _find_matching_brace(raw, j)
            if end is None:
                i = key_idx + len('"payload"')
                continue

            yield raw[j : end + 1]
            i = end + 1

    for obj_str in _iter_payload_objects(text):
        parsed = _loads_multipass(obj_str)
        if isinstance(parsed, (dict, list)):
            yield parsed

