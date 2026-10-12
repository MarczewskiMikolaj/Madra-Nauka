from cryptography.fernet import Fernet
import os


SECRET_KEY = os.environ.get('SECRET_KEY', 'your-secret-key-change-this-in-production')

ENCRYPTION_KEY = os.environ.get('ENCRYPTION_KEY', '').encode()
cipher = Fernet(ENCRYPTION_KEY)

USERS_FILE = 'users.json'
SETS_FILE = 'sets.json'

BUCKET_NAME = os.environ.get("USERS_BUCKET_NAME", "python-fiszki-users")
USERS_FILE_NAME = "users.json"
SETS_FILE_NAME = "sets.json"

# Sprawdź czy używać Cloud Storage (produkcja) czy lokalnych plików (development)
USE_CLOUD_STORAGE = os.environ.get("USE_CLOUD_STORAGE", "false").lower() == "true"

SCHEDULER_SECRET = os.environ.get('SCHEDULER_SECRET', 'change-me-in-production')

VAPID_PUBLIC_KEY = os.environ.get('VAPID_PUBLIC_KEY', '')
VAPID_PRIVATE_KEY = os.environ.get('VAPID_PRIVATE_KEY', '')
VAPID_CLAIMS = {'sub': os.environ.get('VAPID_CLAIMS_SUB', 'mailto:admin@madranauka.online')}
