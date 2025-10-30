import json  # at top of file if not already

fulfillment_params = {
    "correlation_id": correlation_id,
    "prospect_account_key": body["prospectAccountKey"],
    "prospect_account_key_type": body["prospectAccountKeyType"],
    "prospect_sor_id": body["sorId"],
    "internal_program_key": body["programCode"],
    "referral_code": body["referralCode"],
    "customer_fulfillment_reference_id": referralReferenceKeyName,
    "customer_fulfillment_reference_source_id": referralReferenceKeyValue,
    "tenant_id": tenant_id,
    "creation_user_id": created_user,
    "last_updated_user_id": last_user,
    "event_id": event_id,
}

logger.info("Creating FulfillmentEvent with params=%s",
            json.dumps(fulfillment_params, default=str, sort_keys=True))

fulfillment = FulfillmentEvent(**fulfillment_params)
