import json
import os
import sys
import unittest
from pathlib import Path

import requests
from pact import Pact


CURRENT_DIR = Path(__file__).resolve().parent
REPO_ROOT = CURRENT_DIR.parents[1]

sys.path.insert(0, str(REPO_ROOT))

PACT_DIR = Path(os.getenv("PACT_DIR", REPO_ROOT / "pacts"))
PACT_DIR.mkdir(parents=True, exist_ok=True)


def _normalize_content_type_headers_for_pactflow():
    """
    Pact Python v3 generates Content-Type headers as plain strings.

    PactFlow/OpenAPI comparison in this provider setup is expecting the
    header value to contain a 'value' property. So we normalize only the
    generated Content-Type headers after Pact writes the contract file.
    """
    for pact_file in PACT_DIR.glob("*.json"):
        with pact_file.open("r", encoding="utf-8") as file:
            pact_json = json.load(file)

        for interaction in pact_json.get("interactions", []):
            _normalize_headers(interaction.get("request", {}))
            _normalize_headers(interaction.get("response", {}))

        with pact_file.open("w", encoding="utf-8") as file:
            json.dump(pact_json, file, indent=2)
            file.write("\n")


def _normalize_headers(message):
    headers = message.setdefault("headers", {})

    content_type_key = None
    for header_name in headers:
        if header_name.lower() == "content-type":
            content_type_key = header_name
            break

    if content_type_key is None:
        content_type_key = "Content-Type"
        headers[content_type_key] = "application/json"

    current_value = headers.get(content_type_key)

    if isinstance(current_value, dict) and "value" in current_value:
        return

    if isinstance(current_value, list) and current_value:
        content_type_value = current_value[0]
    elif isinstance(current_value, str):
        content_type_value = current_value
    else:
        content_type_value = "application/json"

    headers[content_type_key] = {
        "value": content_type_value,
    }


class DepositsPromoContract(unittest.TestCase):
    def test_promo_validate(self):
        consumer_name = os.getenv(
            "CONSUMER_NAME",
            "asvofferfulfillmentengine-offerretroactiveonboard-bankoffersretroactiveonboard",
        )

        provider_name = os.getenv(
            "PROVIDER_NAME_1",
            "deposits-promotions-6.1",
        )

        pact = Pact(
            consumer=consumer_name,
            provider=provider_name,
        )

        request_body = {
            "clientCorrelationId": "test-correlation-id",
            "validatedEligibilityRequest": {},
            "eligiblePromotion": {},
        }

        expected_body = {
            "isPromotionValid": True,
            "promotionCode": "string",
            "promotionMessages": [
                {
                    "applicationKey": "string",
                    "messageContent": "string",
                    "messageCriteria": "string",
                    "messagePlacement": "string",
                    "messagePlatform": "string",
                    "messagePriority": "string",
                    "messageType": "INFORMATION",
                    "promotionMessageId": "string",
                }
            ],
            "businessReferenceId": "string",
            "lineOfBusiness": "string",
        }

        (
            pact
            .upon_receiving(
                "a request to validate customer eligibility based on promotion criteria"
            )
            .with_request("POST", "/deposits/promotions/promo/validate")
            .with_header("Content-Type", "application/json")
            .with_body(request_body)
            .will_respond_with(200)
            .with_header("Content-Type", "application/json")
            .with_body(expected_body)
        )

        with pact.serve() as mockserver:
            response = requests.post(
                f"{mockserver.url}/deposits/promotions/promo/validate",
                json=request_body,
                headers={"Content-Type": "application/json"},
                timeout=5,
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected_body)

        pact.write_file(str(PACT_DIR), overwrite=True)

        _normalize_content_type_headers_for_pactflow()

        generated_pact_files = list(PACT_DIR.glob("*.json"))
        self.assertTrue(
            generated_pact_files,
            f"No pact files were generated under {PACT_DIR}",
        )


if __name__ == "__main__":
    unittest.main()






No, this is not intended to swap out the existing client for all feature flags.
The existing oauthWebClient path is still being passed into FeatureFlagServiceImpl, and the new openFeatureClient is only being added so we can evaluate the new Optimizely-backed flag.
Existing flags do not all need to be created in Optimizely as part of this change.
This PR is meant to support the new targeted incentive eligibility flag only, while preserving current behavior for the existing flags.
