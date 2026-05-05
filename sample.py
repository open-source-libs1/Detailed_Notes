import os
import sys
import unittest
from pathlib import Path

import requests

try:
    from pact.v2 import Consumer, Provider
except ImportError:
    from pact import Consumer, Provider


CURRENT_DIR = Path(__file__).resolve().parent
REPO_ROOT = CURRENT_DIR.parents[1]

sys.path.insert(0, str(REPO_ROOT))

PACT_DIR = Path(os.getenv("PACT_DIR", REPO_ROOT / "pacts"))
PACT_DIR.mkdir(parents=True, exist_ok=True)


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

        pact = Consumer(consumer_name).has_pact_with(
            Provider(provider_name),
            pact_dir=str(PACT_DIR),
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

        pact.start_service()

        try:
            (
                pact
                .upon_receiving(
                    "a request to validate customer eligibility based on promotion criteria"
                )
                .with_request(
                    method="POST",
                    path="/deposits/promotions/promo/validate",
                    headers={"Content-Type": "application/json"},
                    body=request_body,
                )
                .will_respond_with(
                    status=200,
                    headers={"Content-Type": "application/json"},
                    body=expected_body,
                )
            )

            with pact:
                response = requests.post(
                    f"{pact.uri}/deposits/promotions/promo/validate",
                    json=request_body,
                    headers={"Content-Type": "application/json"},
                    timeout=5,
                )

            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json(), expected_body)

        finally:
            pact.stop_service()

        generated_pact_files = list(PACT_DIR.glob("*.json"))
        self.assertTrue(
            generated_pact_files,
            f"No pact files were generated under {PACT_DIR}",
        )


if __name__ == "__main__":
    unittest.main()
