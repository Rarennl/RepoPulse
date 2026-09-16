"""Environment configuration; no credentials in source or browser storage."""
import os
from pathlib import Path
from cryptography.fernet import Fernet

DATABASE_URL = os.getenv('DATABASE_URL', 'sqlite:///./health.db')
REDIS_URL = os.getenv('REDIS_URL', 'redis://localhost:6379/0')
PUBLIC_ORIGIN = os.getenv('PUBLIC_ORIGIN', 'http://localhost:8000').rstrip('/')
SOURCECRAFT_TOKEN = os.getenv('SOURCECRAFT_TOKEN', '')
ORG_SLUGS = [s.strip() for s in os.getenv('SOURCECRAFT_ORGS', 'sourcecraft').split(',') if s.strip()]
CLIENT_ID = os.getenv('YANDEX_CLIENT_ID', '')
CLIENT_SECRET = os.getenv('YANDEX_CLIENT_SECRET', '')
SECURE_COOKIE = PUBLIC_ORIGIN.startswith('https://')
API_BASE = 'https://api.sourcecraft.tech'
DISCOVERY_MODE = os.getenv('DISCOVERY_MODE', 'all')
APPSEC_ENABLED = os.getenv('APPSEC_ENABLED', 'true').lower() == 'true'
APPSEC_TOKEN = os.getenv('APPSEC_TOKEN', '')
APPSEC_AUTH_SCHEME = os.getenv('APPSEC_AUTH_SCHEME', 'Bearer')

def cipher():
    key = os.getenv('TOKEN_ENCRYPTION_KEY')
    if not key:
        # A shared volume persists the local-development key across restarts.
        path = Path(os.getenv('KEY_FILE', '/state/token.key'))
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with path.open('xb') as f:
                os.chmod(path, 0o600)
                f.write(Fernet.generate_key())
        except FileExistsError:
            pass
        key = path.read_bytes()
    return Fernet(key)
