"""Validation of email addresses used for registration and login."""

import re


def normalize_email(value):
    value = value.strip().casefold()
    if len(value) > 254 or not re.fullmatch(
        r"[a-z0-9.!#$%&'*+/=?^_`{|}~-]+@[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?\.[a-z]{2,63}",
        value,
    ):
        raise ValueError("Wpisz poprawny adres e-mail.")
    local, domain = value.rsplit("@", 1)
    if (
        len(local) > 64
        or local.startswith(".")
        or local.endswith(".")
        or ".." in value
        or any(
            not label or label.startswith("-") or label.endswith("-") or len(label) > 63
            for label in domain.split(".")
        )
    ):
        raise ValueError("Wpisz poprawny adres e-mail.")
    return value
