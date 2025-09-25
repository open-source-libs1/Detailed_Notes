def _json_loads_relaxed(raw: str) -> Any:
    """Parses a JSON string with tolerance for double-encoded or nested JSON.

    Attempts up to 3 passes of json.loads. If a later pass fails, returns the
    last successfully parsed object. If parsing fails entirely, returns the
    original string unchanged.

    Args:
        raw: The raw string that may represent JSON.

    Returns:
        A Python object (dict, list, str, int, etc.) if successfully parsed,
        otherwise the original string.

    Example:
        >>> _json_loads_relaxed('"123"')
        '123'
        >>> _json_loads_relaxed('"{"a":1}"')
        {'a': 1}
        >>> _json_loads_relaxed('not-json')
        'not-json'
    """
    # implementation ...


def _extract_records_tree(obj: Any) -> List[Dict[str, Any]]:
    """Normalizes various shapes into a list of record dictionaries.

    Handles cases where the object is:
      - A dict with a "records" list
      - A list of dicts containing "records"
      - A single record dict
      - Anything else → returns empty list

    Args:
        obj: A parsed Python object (dict, list, str, etc.).

    Returns:
        A list of dictionaries representing records.

    Example:
        >>> _extract_records_tree({"records":[{"payload":{"x":1}},{"payload":{"x":2}}]})
        [{'payload': {'x': 1}}, {'payload': {'x': 2}}]

        >>> _extract_records_tree([{"records":[{"payload":1}]}])
        [{'payload': 1}]
    """
    # implementation ...


def extract_messages_from_body(body: str) -> List[str]:
    """Extracts individual messages from one SQS record body.

    Prefers the "payload" field if present; otherwise serializes the whole record.
    Always returns messages as compact JSON strings.

    Args:
        body: The raw body string from an SQS record.

    Returns:
        A list of JSON strings, one per extracted message.

    Example:
        >>> body = '{"records":[{"payload":{"account_key":"AK1"}},{"payload":{"account_key":"AK2"}}]}'
        >>> extract_messages_from_body(body)
        ['{"account_key":"AK1"}', '{"account_key":"AK2"}']
    """
    # implementation ...


def explode_sqs_event_to_messages(event: Dict[str, Any]) -> List[Tuple[str, str]]:
    """Expands an SQS event into a flat list of (messageId, messageBody) pairs.

    Each outer record in the event may contain multiple inner messages, which
    are extracted and paired with the outer "messageId".

    Args:
        event: The full Lambda event payload containing Records.

    Returns:
        A list of (source_message_id, body_json_string) tuples.

    Example:
        >>> event = {
        ...   "Records": [
        ...     {"messageId":"A","body":'{"records":[{"payload":{"id":1}},{"payload":{"id":2}}]}'},
        ...     {"messageId":"B","body":'{"records":[{"payload":{"id":3}}]}'}
        ...   ]
        ... }
        >>> explode_sqs_event_to_messages(event)
        [('A','{"id":1}'), ('A','{"id":2}'), ('B','{"id":3}')]
    """
    # implementation ...


def build_batch_item_failures(
    flattened_pairs: List[Tuple[str, str]],
    failed_bodies: List[str],
) -> List[Dict[str, str]]:
    """Builds the Lambda response for failed SQS messages.

    Maps failed inner message bodies back to their original outer messageIds.
    Ensures only one failure per outer messageId is reported, as required by SQS.

    Args:
        flattened_pairs: List of (messageId, body) pairs from explode_sqs_event_to_messages.
        failed_bodies: List of message bodies that failed to enqueue.

    Returns:
        A list of dicts in the format required by Lambda:
        [{"itemIdentifier": "<outer-messageId>"}, ...]

    Example:
        >>> flattened = [('A','{"id":1}'), ('A','{"id":2}'), ('B','{"id":3}')]
        >>> failed_bodies = ['{"id":2}','{"id":3}']
        >>> build_batch_item_failures(flattened, failed_bodies)
        [{'itemIdentifier': 'A'}, {'itemIdentifier': 'B'}]
    """
    # implementation ...

