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


def _remove_content_type_headers_from_generated_pacts():
    for pact_file in PACT_DIR.glob("*.json"):
        with pact_file.open("r", encoding="utf-8") as file:
            pact_json = json.load(file)

        for interaction in pact_json.get("interactions", []):
            request_headers = interaction.get("request", {}).get("headers", {})
            response_headers = interaction.get("response", {}).get("headers", {})

            for header_name in list(request_headers.keys()):
                if header_name.lower() == "content-type":
                    request_headers.pop(header_name, None)

            for header_name in list(response_headers.keys()):
                if header_name.lower() == "content-type":
                    response_headers.pop(header_name, None)

            if not request_headers:
                interaction.get("request", {}).pop("headers", None)

            if not response_headers:
                interaction.get("response", {}).pop("headers", None)

        with pact_file.open("w", encoding="utf-8") as file:
            json.dump(pact_json, file, indent=2)
            file.write("\n")


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
            .with_body(request_body)
            .will_respond_with(200)
            .with_body(expected_body)
        )

        with pact.serve() as mockserver:
            response = requests.post(
                f"{mockserver.url}/deposits/promotions/promo/validate",
                json=request_body,
                timeout=5,
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), expected_body)

        pact.write_file(str(PACT_DIR), overwrite=True)

        _remove_content_type_headers_from_generated_pacts()

        generated_pact_files = list(PACT_DIR.glob("*.json"))
        self.assertTrue(
            generated_pact_files,
            f"No pact files were generated under {PACT_DIR}",
        )


if __name__ == "__main__":
    unittest.main()
