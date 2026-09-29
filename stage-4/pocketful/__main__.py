import os

from .http_api import serve

serve(int(os.environ.get("PORT") or 8080))
