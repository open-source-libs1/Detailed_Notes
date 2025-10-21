

import os, sys

# Add the project root that CONTAINS the 'src' package
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))  # -> lambda/
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from src.database.db import create_referral_fulfillment



pipenv run pytest --maxfail=1 --disable-warnings --cov=src --cov-report=term-missing -q

