"""Small-instance durable SQLite snapshots on GCS, with conditional atomic writes.

The SQLite file is never mounted from GCS. Each context gets an independent
in-memory database; successful transactions publish a complete snapshot. A
stale writer is rejected instead of overwriting another instance's changes.
"""

import threading
import json
import time
from contextlib import contextmanager
from flask import current_app
from werkzeug.exceptions import Conflict, ServiceUnavailable


class StateConflict(Conflict):
    description = "Dane zmieniły się w międzyczasie. Odśwież stronę i ponów zapis."


class StateUnavailable(ServiceUnavailable):
    description = "Nie udało się połączyć z magazynem danych. Spróbuj ponownie."


class CloudState:
    def __init__(self, bucket, prefix, client=None):
        if client is None:
            from google.cloud import storage

            client = storage.Client()
        self.bucket = client.bucket(bucket)
        self.prefix = prefix.strip("/")
        self.lock = threading.RLock()

    def read(self, name):
        from google.api_core.exceptions import NotFound, PreconditionFailed

        for _ in range(3):
            blob = self.bucket.blob(self.prefix + "/" + name)
            try:
                blob.reload(timeout=30)
            except NotFound:
                return None, 0
            except Exception:
                current_app.logger.warning("Cloud state read failed")
                raise StateUnavailable() from None
            try:
                generation = int(blob.generation)
                return (
                    blob.download_as_bytes(if_generation_match=generation, timeout=30),
                    generation,
                )
            except (NotFound, PreconditionFailed):
                # Replacement deletes the old generation when versioning is off.
                # A download of that generation can return 404, even though the
                # object still exists. Reload its current generation and retry.
                continue
            except Exception:
                current_app.logger.warning("Cloud state read failed")
                raise StateUnavailable() from None
        raise StateConflict()

    def write(self, name, content, generation):
        from google.api_core.exceptions import PreconditionFailed
        from google.cloud.storage.retry import DEFAULT_RETRY_IF_GENERATION_SPECIFIED

        blob = self.bucket.blob(self.prefix + "/" + name)
        try:
            blob.upload_from_string(
                content,
                content_type="application/octet-stream",
                if_generation_match=generation,
                timeout=30,
                retry=DEFAULT_RETRY_IF_GENERATION_SPECIFIED,
            )
            return int(blob.generation)
        except PreconditionFailed:
            raise StateConflict() from None
        except Exception:
            # A lost response might follow a committed write. Never claim success;
            # idempotent application flows determine the result on the next request.
            current_app.logger.warning("Cloud state write failed")
            raise StateUnavailable() from None

    @contextmanager
    def lease(self, name):
        """Serialize credential rotation across overlapping Cloud Run revisions."""
        from google.api_core.exceptions import NotFound, PreconditionFailed

        lock_name = "locks/" + name
        deadline = time.monotonic() + 10
        while True:
            data, generation = self.read(lock_name)
            if data is None or json.loads(data)["expires"] < time.time():
                try:
                    acquired = self.write(
                        lock_name,
                        json.dumps({"expires": time.time() + 300}).encode(),
                        generation,
                    )
                    break
                except StateConflict:
                    pass
            if time.monotonic() >= deadline:
                raise StateConflict()
            time.sleep(0.25)
        try:
            yield
        finally:
            try:
                self.bucket.blob(self.prefix + "/" + lock_name).delete(
                    if_generation_match=acquired, timeout=30
                )
            except (NotFound, PreconditionFailed):
                pass
            except Exception:
                current_app.logger.warning("Credential lock release failed")


def cloud_state():
    return current_app.extensions.get("cloud_state")
