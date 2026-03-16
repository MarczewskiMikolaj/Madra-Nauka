from cryptography.fernet import Fernet
import os


SECRET_KEY = os.environ.get('SECRET_KEY', 'your-secret-key-change-this-in-production')

# Encryption key - in production, store this securely (environment variable, key management service)
ENCRYPTION_KEY = b'ENCRYPTION_KEY_REMOVED'  # Example key - change in production
cipher = Fernet(ENCRYPTION_KEY)

USERS_FILE = 'users.json'
SETS_FILE = 'sets.json'

BUCKET_NAME = os.environ.get("USERS_BUCKET_NAME", "python-fiszki-users")
USERS_FILE_NAME = "users.json"
SETS_FILE_NAME = "sets.json"

# Sprawdź czy używać Cloud Storage (produkcja) czy lokalnych plików (development)
USE_CLOUD_STORAGE = os.environ.get("USE_CLOUD_STORAGE", "false").lower() == "true"

SCHEDULER_SECRET = os.environ.get('SCHEDULER_SECRET', 'change-me-in-production')

VAPID_PUBLIC_KEY = 'VAPID_KEY_REMOVED'
VAPID_PRIVATE_KEY = '-----BEGIN EC PRIVATE KEY-----\nPRIVATE_KEY_REMOVED\nPRIVATE_KEY_REMOVED2\nPRIVATE_KEY_REMOVED3\n-----END EC PRIVATE KEY-----\n'
VAPID_CLAIMS = {'sub': 'mailto:admin@madranaucka.pl'}
