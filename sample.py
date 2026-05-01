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


class DepositsPromoContract(unittest.TestCase):
    def test_promo_validate(self):
        consumer_name = os.getenv(
            "CONSUMER_NAME",
            "asvofferfulfillmentengine-offerretroactiveonboard-bankoffersretroactiveonboard",
        )

        provider_name = os.getenv(
            "PROVIDER_NAME_1",
            "asvofferfulfillmentengine-offereligibilityapi-bankofferseligibilityapi-6.2",
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

        generated_pact_files = list(PACT_DIR.glob("*.json"))
        self.assertTrue(
            generated_pact_files,
            f"No pact files were generated under {PACT_DIR}",
        )


if __name__ == "__main__":
    unittest.main()
