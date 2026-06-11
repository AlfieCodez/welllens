"""Entrypoint: `py run.py` (dev) or via flask/gunicorn (prod).

Host/port are env-configurable. Set HOST=0.0.0.0 to allow other devices on your
network (e.g. your phone) to reach the dev server.
"""
import os

from welllens import create_app

app = create_app()

if __name__ == "__main__":
    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "5000"))
    app.run(host=host, port=port, debug=app.config["DEBUG"])
