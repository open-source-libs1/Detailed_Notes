def _flatten_records(records_field: Any) -> Iterator[dict]:
    """Yield dict items from `records`, tolerating:
       - list, list-of-lists, tuples, and deeper nesting
       - stringified JSON (including CloudWatch-style with \\n / \")
       - containers that themselves expose a `records` key (extra wrapper)
    """
    def _walk(obj: Any) -> Iterator[dict]:
        # Peel strings that look like JSON
        if isinstance(obj, str) and _looks_like_json(obj):
            obj = _loads_multipass(obj)

        # If we’re handed a container that *itself* has a `records` key, dive into it.
        # (This fixes cases where we got an extra wrapper like {"records":[...]} by mistake.)
        if isinstance(obj, dict) and "records" in obj:
            yield from _walk(obj["records"])
            return

        if isinstance(obj, dict):
            # A leaf item in the records list
            yield obj
            return

        if isinstance(obj, (list, tuple)):
            for item in obj:
                yield from _walk(item)
            return

        # Any other scalar -> ignore silently
        return

    yield from _walk(records_field)
