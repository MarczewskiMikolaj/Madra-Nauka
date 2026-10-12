from google.cloud import storage
from google.api_core import exceptions as gcp_exceptions
import os
import json
import time
import traceback

from config import (
    cipher,
    USE_CLOUD_STORAGE,
    USERS_FILE,
    SETS_FILE,
    BUCKET_NAME,
    USERS_FILE_NAME,
    SETS_FILE_NAME,
)


_gcs_client = None

def get_storage_client():
    global _gcs_client
    if _gcs_client is None:
        _gcs_client = storage.Client()
    return _gcs_client

def load_users():
    """Wczytaj użytkowników - z GCS (produkcja) lub lokalnie (development).
    Zwraca tuple: (users_data, generation) dla GCS lub (users_data, None) dla lokalnego."""
    if not USE_CLOUD_STORAGE:
        # Wersja lokalna - pliki na dysku
        if not os.path.exists(USERS_FILE):
            return ([], None)
        try:
            with open(USERS_FILE, 'rb') as f:
                encrypted_data = f.read()
                if not encrypted_data:
                    return ([], None)
                decrypted_data = cipher.decrypt(encrypted_data)
                data = json.loads(decrypted_data.decode('utf-8'))

                if isinstance(data, dict) and 'users' in data and isinstance(data['users'], list):
                    return (data['users'], None)
                if isinstance(data, dict):
                    migrated = []
                    for login, info in data.items():
                        item = {
                            'login': login,
                            'haslo': info.get('haslo') or info.get('password'),
                            'data_utworzenia': info.get('data_utworzenia')
                        }
                        migrated.append(item)
                    return (migrated, None)
                if isinstance(data, list):
                    return (data, None)
                return ([], None)
        except (OSError, IOError) as e:
            print(f"Błąd I/O podczas wczytywania użytkowników (lokalnie): {e}")
            return ([], None)
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            print(f"Błąd dekodowania danych użytkowników (lokalnie): {e}")
            return ([], None)
        except Exception as e:
            print(f"Błąd podczas wczytywania użytkowników (lokalnie): {e}")
            traceback.print_exc()
            return ([], None)

    # Wersja cloud - Google Cloud Storage
    try:
        client = get_storage_client()
        bucket = client.bucket(BUCKET_NAME)
        blob = bucket.blob(USERS_FILE_NAME)

        if not blob.exists():
            print(f"Plik {USERS_FILE_NAME} nie istnieje w bucket {BUCKET_NAME}")
            return ([], None)

        # Pobierz dane wraz z generacją
        blob.reload()
        encrypted_data = blob.download_as_bytes()
        generation = blob.generation

        if not encrypted_data:
            return ([], generation)

        decrypted_data = cipher.decrypt(encrypted_data)
        data = json.loads(decrypted_data.decode('utf-8'))

        # Obsługa formatu: {"users": [...]}
        if isinstance(data, dict) and 'users' in data and isinstance(data['users'], list):
            users_list = data['users']
            # Walidacja: upewnij się że każdy element to słownik
            valid_users = []
            for item in users_list:
                if isinstance(item, dict):
                    valid_users.append(item)
                else:
                    print(f"OSTRZEŻENIE: Nieprawidłowy format użytkownika: {item}")
            return (valid_users, generation)

        # Obsługa starego formatu: {"login": {"haslo": ..., "data_utworzenia": ...}, ...}
        if isinstance(data, dict):
            migrated = []
            for login, info in data.items():
                item = {
                    'login': login,
                    'haslo': info.get('haslo') or info.get('password'),
                    'data_utworzenia': info.get('data_utworzenia')
                }
                migrated.append(item)
            return (migrated, generation)

        # Jeśli już lista
        if isinstance(data, list):
            return (data, generation)

        return ([], generation)
    except Exception as e:
        print(f"Błąd podczas wczytywania użytkowników (cloud): {e}")
        traceback.print_exc()
        return ([], None)

def save_users(users_data, expected_generation=None, max_retries=3):
    """Zapisz użytkowników - do GCS (produkcja) lub lokalnie (development).

    Args:
        users_data: dane do zapisania
        expected_generation: oczekiwana generacja dla optymistic locking (tylko GCS)
        max_retries: maksymalna liczba prób w przypadku konfliktu

    Returns:
        True jeśli zapis się powiódł, False w przeciwnym razie
    """
    if not USE_CLOUD_STORAGE:
        # Wersja lokalna - pliki na dysku
        try:
            wrapper = {'users': users_data}
            json_data = json.dumps(wrapper, indent=2, ensure_ascii=False).encode('utf-8')
            encrypted_data = cipher.encrypt(json_data)
            with open(USERS_FILE, 'wb') as f:
                f.write(encrypted_data)
            return True
        except (OSError, IOError) as e:
            print(f"Błąd I/O podczas zapisywania użytkowników (lokalnie): {e}")
            return False
        except Exception as e:
            print(f"Błąd podczas zapisywania użytkowników (lokalnie): {e}")
            return False

    # Wersja cloud - Google Cloud Storage z retry logic
    for attempt in range(max_retries):
        try:
            wrapper = {'users': users_data}
            json_data = json.dumps(wrapper, indent=2, ensure_ascii=False).encode('utf-8')
            encrypted_data = cipher.encrypt(json_data)

            client = get_storage_client()
            bucket = client.bucket(BUCKET_NAME)
            blob = bucket.blob(USERS_FILE_NAME)

            # Użyj if_generation_match dla optymistic locking
            if expected_generation is not None:
                blob.upload_from_string(
                    encrypted_data,
                    content_type='application/octet-stream',
                    if_generation_match=expected_generation
                )
            else:
                blob.upload_from_string(encrypted_data, content_type='application/octet-stream')

            return True

        except gcp_exceptions.PreconditionFailed:
            # Konflikt - ktoś inny zmodyfikował plik
            print(f"Konflikt przy zapisie użytkowników (próba {attempt + 1}/{max_retries})")
            if attempt < max_retries - 1:
                time.sleep(0.1 * (attempt + 1))  # Exponential backoff
                continue
            else:
                print("Nie udało się zapisać użytkowników po wszystkich próbach")
                return False

        except Exception as e:
            print(f"Błąd podczas zapisywania użytkowników (cloud): {e}")
            return False

    return False

def load_sets():
    """Wczytaj zestawy fiszek - z GCS (produkcja) lub lokalnie (development).
    Zwraca tuple: (sets_data, generation) dla GCS lub (sets_data, None) dla lokalnego."""
    if not USE_CLOUD_STORAGE:
        # Wersja lokalna - pliki na dysku
        if not os.path.exists(SETS_FILE):
            return ([], None)
        try:
            with open(SETS_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if isinstance(data, dict) and 'sets' in data and isinstance(data['sets'], list):
                    return (data['sets'], None)
                if isinstance(data, list):
                    return (data, None)
                return ([], None)
        except (OSError, IOError) as e:
            print(f"Błąd I/O podczas wczytywania zestawów (lokalnie): {e}")
            return ([], None)
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            print(f"Błąd dekodowania danych zestawów (lokalnie): {e}")
            return ([], None)
        except Exception as e:
            print(f"Błąd podczas wczytywania zestawów (lokalnie): {e}")
            traceback.print_exc()
            return ([], None)

    # Wersja cloud - Google Cloud Storage
    try:
        client = get_storage_client()
        bucket = client.bucket(BUCKET_NAME)
        blob = bucket.blob(SETS_FILE_NAME)

        if not blob.exists():
            print(f"Plik {SETS_FILE_NAME} nie istnieje w bucket {BUCKET_NAME}")
            return ([], None)

        # Pobierz dane wraz z generacją (dla optymistic locking)
        blob.reload()
        data_str = blob.download_as_text()
        generation = blob.generation

        if not data_str.strip():
            return ([], generation)

        data = json.loads(data_str)
        if isinstance(data, dict) and 'sets' in data and isinstance(data['sets'], list):
            sets_list = data['sets']
            # Walidacja: upewnij się że każdy element to słownik
            valid_sets = []
            for item in sets_list:
                if isinstance(item, dict):
                    valid_sets.append(item)
                else:
                    print(f"OSTRZEŻENIE: Nieprawidłowy format zestawu: {type(item)} - {item}")
            return (valid_sets, generation)
        if isinstance(data, list):
            # Walidacja dla formatu bez wrappera
            valid_sets = []
            for item in data:
                if isinstance(item, dict):
                    valid_sets.append(item)
                else:
                    print(f"OSTRZEŻENIE: Nieprawidłowy format zestawu: {type(item)} - {item}")
            return (valid_sets, generation)
        return ([], generation)
    except Exception as e:
        print(f"Błąd podczas wczytywania zestawów (cloud): {e}")
        traceback.print_exc()
        return ([], None)

def save_sets(sets_data, expected_generation=None, max_retries=3):
    """Zapisz zestawy fiszek - do GCS (produkcja) lub lokalnie (development).

    Args:
        sets_data: dane do zapisania
        expected_generation: oczekiwana generacja dla optymistic locking (tylko GCS)
        max_retries: maksymalna liczba prób w przypadku konfliktu

    Returns:
        True jeśli zapis się powiódł, False w przeciwnym razie
    """
    if not USE_CLOUD_STORAGE:
        # Wersja lokalna - pliki na dysku
        try:
            wrapper = {'sets': sets_data}
            with open(SETS_FILE, 'w', encoding='utf-8') as f:
                json.dump(wrapper, f, indent=2, ensure_ascii=False)
            return True
        except (OSError, IOError) as e:
            print(f"Błąd I/O podczas zapisywania zestawów (lokalnie): {e}")
            return False
        except Exception as e:
            print(f"Błąd podczas zapisywania zestawów (lokalnie): {e}")
            return False

    # Wersja cloud - Google Cloud Storage z retry logic
    for attempt in range(max_retries):
        try:
            wrapper = {'sets': sets_data}
            client = get_storage_client()
            bucket = client.bucket(BUCKET_NAME)
            blob = bucket.blob(SETS_FILE_NAME)

            # Użyj if_generation_match dla optymistic locking
            if expected_generation is not None:
                blob.upload_from_string(
                    json.dumps(wrapper, ensure_ascii=False, indent=2),
                    content_type='application/json',
                    if_generation_match=expected_generation
                )
            else:
                blob.upload_from_string(
                    json.dumps(wrapper, ensure_ascii=False, indent=2),
                    content_type='application/json'
                )

            return True

        except gcp_exceptions.PreconditionFailed:
            # Konflikt - ktoś inny zmodyfikował plik
            print(f"Konflikt przy zapisie zestawów (próba {attempt + 1}/{max_retries})")
            if attempt < max_retries - 1:
                time.sleep(0.1 * (attempt + 1))  # Exponential backoff
                continue
            else:
                print("Nie udało się zapisać zestawów po wszystkich próbach")
                return False

        except Exception as e:
            print(f"Błąd podczas zapisywania zestawów (cloud): {e}")
            return False

    return False


class DataStore:
    def __init__(self):
        self.users, self.users_generation = load_users()
        self.sets, self.sets_generation = load_sets()

    def reload_users(self):
        if USE_CLOUD_STORAGE:
            self.users, self.users_generation = load_users()

    def reload_sets(self):
        if USE_CLOUD_STORAGE:
            self.sets, self.sets_generation = load_sets()

    def save_and_reload_users(self):
        if not save_users(self.users, self.users_generation):
            print('Warning: save_users failed, skipping reload')
            return
        self.users, self.users_generation = load_users()

    def save_and_reload_sets(self):
        if not save_sets(self.sets, self.sets_generation):
            print('Warning: save_sets failed, skipping reload')
            return
        self.sets, self.sets_generation = load_sets()


store = DataStore()
