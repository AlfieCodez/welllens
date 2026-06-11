"""Production WSGI entrypoint (gunicorn): `gunicorn wsgi:app`.

Uses the hardened ProductionConfig. Dev still uses `py run.py`.
"""
from config import ProductionConfig
from welllens import create_app

app = create_app(ProductionConfig)
