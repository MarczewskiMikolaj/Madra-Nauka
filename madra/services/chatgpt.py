"""Official local OSS ChatGPT-plan OAuth. Credentials never leave server storage."""

import base64
import hashlib
import hmac
import json
import os
import secrets
import ssl
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen
from uuid import uuid4

import certifi
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from flask import current_app

RESOURCE = "https://api.openai.com/v1"
AUTH = "https://auth.openai.com"
SCOPE = "openid profile email offline_access resource.invoke chatgpt.tokens.use.direct"
LOCK = threading.RLock()


def tls_context():
    context = ssl.create_default_context()
    context.load_verify_locations(cafile=certifi.where())
    return context


def fetch_json(url, payload=None, form=False, token=None):
    headers = {"Accept": "application/json"}
    data = None
    if payload is not None:
        data = urlencode(payload).encode() if form else json.dumps(payload).encode()
        headers["Content-Type"] = (
            "application/x-www-form-urlencoded" if form else "application/json"
        )
    if token:
        headers["Authorization"] = "Bearer " + token
    try:
        with urlopen(
            Request(url, data=data, headers=headers), timeout=20, context=tls_context()
        ) as response:
            return json.loads(response.read(2 * 1024 * 1024))
    except HTTPError as error:
        current_app.logger.warning(
            "OpenAI request failed: endpoint=%s status=%s",
            urlsplit(url).path,
            error.code,
        )
        raise ValueError(
            f"OpenAI odrzuciło połączenie (HTTP {error.code}). Rozpocznij łączenie konta ponownie."
        ) from None
    except (URLError, TimeoutError) as error:
        reason = error.reason if isinstance(error, URLError) else error
        current_app.logger.warning(
            "OpenAI connection failed: endpoint=%s reason=%s",
            urlsplit(url).path,
            type(reason).__name__,
        )
        if isinstance(reason, ssl.SSLCertVerificationError):
            raise ValueError(
                "Serwer aplikacji nie może zweryfikować certyfikatu HTTPS OpenAI. Sprawdź konfigurację certyfikatów serwera."
            ) from None
        raise ValueError(
            "Nie udało się połączyć z OpenAI. Sprawdź połączenie z internetem i spróbuj ponownie."
        ) from None
    except ValueError:
        current_app.logger.warning(
            "OpenAI response invalid: endpoint=%s", urlsplit(url).path
        )
        raise ValueError(
            "OpenAI zwróciło nieprawidłową odpowiedź. Spróbuj ponownie."
        ) from None


def directory():
    path = Path(current_app.config["DATABASE"]).parent / "chatgpt"
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    return path


def cipher():
    secret = current_app.secret_key
    if isinstance(secret, str):
        secret = secret.encode()
    return Fernet(base64.urlsafe_b64encode(hashlib.sha256(secret).digest()))


def load(uid):
    path = directory() / (uid + ".enc")
    if not path.exists():
        return {}
    try:
        return json.loads(cipher().decrypt(path.read_bytes()))
    except Exception:
        raise ValueError(
            "Nie można odczytać połączenia ChatGPT. Połącz konto ponownie."
        ) from None


def save(uid, record):
    path = directory() / (uid + ".enc")
    temporary = path.with_name(path.name + "." + secrets.token_hex(8))
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as output:
        output.write(cipher().encrypt(json.dumps(record).encode()))
    os.replace(temporary, path)


@contextmanager
def locked(uid):
    import fcntl

    with LOCK:
        fd = os.open(directory() / (uid + ".lock"), os.O_CREAT | os.O_RDWR, 0o600)
        with os.fdopen(fd, "w") as file:
            fcntl.flock(file, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(file, fcntl.LOCK_UN)


def begin(uid, callback):
    with locked(uid):
        record = load(uid)
        with locked("_host"):
            host_record = load("_host")
            host = host_record.get("host_id") or "urn:uuid:" + str(uuid4())
            save("_host", {"host_id": host})
        verifier, state, nonce = (
            secrets.token_urlsafe(48),
            secrets.token_urlsafe(32),
            secrets.token_urlsafe(32),
        )
        client_id = record.get("client_id") or "dynamic_agent_client"
        record.update(
            host_id=host,
            pending={
                "verifier": verifier,
                "state": state,
                "nonce": nonce,
                "callback": callback,
                "client_id": client_id,
                "started": time.time(),
            },
        )
        save(uid, record)
        params = {
            "client_id": client_id,
            "ext_agent_host_id": host,
            "response_type": "code",
            "redirect_uri": callback,
            "scope": SCOPE,
            "resource": RESOURCE,
            "state": state,
            "nonce": nonce,
            "code_challenge_method": "S256",
            "code_challenge": base64.urlsafe_b64encode(
                hashlib.sha256(verifier.encode()).digest()
            )
            .decode()
            .rstrip("="),
        }
        if client_id == "dynamic_agent_client":
            params["agent_name_hint"] = "Madra Nauka"
        return AUTH + "/api/accounts/authorize?" + urlencode(params)


def decode_part(part):
    return base64.urlsafe_b64decode(part + "=" * (-len(part) % 4))


def verify_identity(token, client_id, nonce):
    try:
        header, body, signature = token.split(".")
        details = json.loads(decode_part(header))
        if details["alg"] != "RS256":
            raise ValueError()
        discovery = fetch_json(AUTH + "/.well-known/openid-configuration")
        jwks_url = discovery["jwks_uri"]
        if not jwks_url.startswith(AUTH + "/"):
            raise ValueError()
        keys = fetch_json(jwks_url)["keys"]
        key = next(
            k
            for k in keys
            if k.get("kid") == details.get("kid") and k.get("kty") == "RSA"
        )
        public = rsa.RSAPublicNumbers(
            int.from_bytes(decode_part(key["e"]), "big"),
            int.from_bytes(decode_part(key["n"]), "big"),
        ).public_key()
        public.verify(
            decode_part(signature),
            (header + "." + body).encode(),
            padding.PKCS1v15(),
            hashes.SHA256(),
        )
        claims = json.loads(decode_part(body))
        audiences = (
            claims["aud"] if isinstance(claims["aud"], list) else [claims["aud"]]
        )
        if (
            claims["iss"] != AUTH
            or client_id not in audiences
            or claims["exp"] <= time.time()
            or not claims.get("sub")
            or not hmac.compare_digest(claims.get("nonce", ""), nonce)
        ):
            raise ValueError()
        return claims
    except Exception:
        raise ValueError(
            "Nie udało się potwierdzić tożsamości konta ChatGPT. Połącz konto ponownie."
        ) from None


def finish(uid, args):
    with locked(uid):
        record = load(uid)
        pending = record.get("pending", {})
        if (
            not pending
            or time.time() - pending["started"] > 600
            or not hmac.compare_digest(args.get("state", ""), pending["state"])
        ):
            raise ValueError(
                "Logowanie wygasło lub ma nieprawidłowy stan. Rozpocznij ponownie."
            )
        record.pop("pending", None)
        save(uid, record)  # one-use attempt, also on denial or exchange failure
        if args.get("error"):
            raise ValueError("Nie udzielono zgody na połączenie ChatGPT.")
        cid = args.get("client_id") or pending["client_id"]
        if (
            cid == "dynamic_agent_client"
            or (
                pending["client_id"] != "dynamic_agent_client"
                and cid != pending["client_id"]
            )
            or not args.get("code")
        ):
            raise ValueError("Nieprawidłowy wynik rejestracji ChatGPT.")
        record["client_id"] = cid
        save(uid, record)
        tokens = fetch_json(
            AUTH + "/api/accounts/oauth/token",
            {
                "grant_type": "authorization_code",
                "client_id": cid,
                "code": args["code"],
                "code_verifier": pending["verifier"],
                "redirect_uri": pending["callback"],
                "resource": RESOURCE,
            },
            form=True,
        )
        identity = verify_identity(tokens.get("id_token", ""), cid, pending["nonce"])
        if record.get("subject") and record["subject"] != identity["sub"]:
            raise ValueError(
                "Wybrano inne konto niż wcześniej połączone. Najpierw odłącz poprzednie konto."
            )
        record.update(
            tokens=tokens,
            client_id=cid,
            subject=identity["sub"],
            email=identity.get("email", ""),
            expires_at=time.time() + int(tokens.get("expires_in", 3600)),
        )
        save(uid, record)
        return record


def permitted(record):
    return (
        bool(record.get("tokens", {}).get("access_token"))
        and "chatgpt.tokens.use.direct"
        in record.get("tokens", {}).get("scope", "").split()
    )


def usage_consent(record):
    return record.get("allow_plan_and_credits") is True


def set_usage_consent(uid, allowed):
    with locked(uid):
        record = load(uid)
        record["allow_plan_and_credits"] = bool(allowed)
        record["usage_consent_updated_at"] = time.time()
        save(uid, record)


def access_token(uid):
    with locked(uid):
        record = load(uid)
        if not permitted(record):
            raise ValueError(
                "Połącz ChatGPT i udziel zgody na używanie planu do generowania materiałów."
            )
        if record["expires_at"] <= time.time() + 90:
            old = record["tokens"]
            if not old.get("refresh_token"):
                raise ValueError("Połączenie wygasło. Zaloguj się do ChatGPT ponownie.")
            new = fetch_json(
                AUTH + "/api/accounts/oauth/token",
                {
                    "grant_type": "refresh_token",
                    "client_id": record["client_id"],
                    "refresh_token": old["refresh_token"],
                    "resource": RESOURCE,
                },
                form=True,
            )
            record["tokens"] = {**old, **new}
            record["expires_at"] = time.time() + int(new.get("expires_in", 3600))
            save(uid, record)
        if not permitted(record):
            raise ValueError(
                "Brak zgody na użycie abonamentu. Połącz ChatGPT ponownie."
            )
        return record["tokens"]["access_token"]


def models(uid):
    result = fetch_json(RESOURCE + "/models", token=access_token(uid))
    return [
        {"id": m["slug"], "name": m.get("display_name", m["slug"])}
        for m in result.get("models", [])
        if m.get("visibility") == "list"
    ]


def disconnect(uid):
    with locked(uid):
        record = load(uid)
        tokens = record.get("tokens", {})
        confirmed = not tokens.get("refresh_token")
        if tokens.get("refresh_token"):
            try:
                discovery = fetch_json(AUTH + "/.well-known/openid-configuration")
                endpoint = discovery["revocation_endpoint"]
                if not endpoint.startswith(AUTH + "/"):
                    raise ValueError()
                payload = urlencode(
                    {
                        "token": tokens["refresh_token"],
                        "token_type_hint": "refresh_token",
                        "client_id": record["client_id"],
                    }
                ).encode()
                with urlopen(
                    Request(
                        endpoint,
                        data=payload,
                        headers={"Content-Type": "application/x-www-form-urlencoded"},
                    ),
                    timeout=20,
                ):
                    confirmed = True
            except Exception:
                pass
        record.pop("tokens", None)
        record.pop("pending", None)
        save(uid, record)
        return confirmed
