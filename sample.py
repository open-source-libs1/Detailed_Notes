# pull first pair safely (None/None if missing)
keys = payload.get("referralReferenceKeys")
first = keys[0] if isinstance(keys, list) and keys and isinstance(keys[0], dict) else {}

referralReferenceKeyName  = first.get("referralReferenceKeyName")
referralReferenceKeyValue = first.get("referralReferenceKeyValue")
