from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import string

PBKDF2_ITERATIONS = 600_000


def hash_password(password: str) -> str:
    if not 12 <= len(password) <= 128:
        raise ValueError("Şifre 12-128 karakter arasında olmalıdır.")
    salt = secrets.token_bytes(16)
    derived = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS)
    return "pbkdf2_sha256${}${}${}".format(
        PBKDF2_ITERATIONS,
        base64.urlsafe_b64encode(salt).decode("ascii"),
        base64.urlsafe_b64encode(derived).decode("ascii"),
    )


def verify_password(password: str, stored: str) -> bool:
    try:
        if stored.startswith("pbkdf2_sha256$"):
            _, iterations_s, salt_s, expected_s = stored.split("$", 3)
            iterations = int(iterations_s)
            salt = base64.urlsafe_b64decode(salt_s.encode("ascii"))
            expected = base64.urlsafe_b64decode(expected_s.encode("ascii"))
            actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
            return hmac.compare_digest(actual, expected)

        # V3 geriye dönük doğrulama. Başarılı girişte yeni formata yükseltilir.
        salt_s, expected_s = stored.split("$", 1)
        salt = base64.urlsafe_b64decode(salt_s.encode("ascii"))
        expected = base64.urlsafe_b64decode(expected_s.encode("ascii"))
        actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 240_000)
        return hmac.compare_digest(actual, expected)
    except Exception:
        return False


def needs_password_rehash(stored: str) -> bool:
    return not stored.startswith(f"pbkdf2_sha256${PBKDF2_ITERATIONS}$")


def random_token(nbytes: int = 32) -> str:
    return secrets.token_urlsafe(nbytes)


def token_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def generate_strong_password(length: int = 22) -> str:
    alphabet = string.ascii_letters + string.digits + "!@#$%*-_"
    while True:
        value = "".join(secrets.choice(alphabet) for _ in range(length))
        if (
            any(c.islower() for c in value)
            and any(c.isupper() for c in value)
            and any(c.isdigit() for c in value)
            and any(c in "!@#$%*-_" for c in value)
        ):
            return value


def validate_new_password(password: str) -> None:
    if not 12 <= len(password) <= 128:
        raise ValueError("Yeni şifre 12-128 karakter arasında olmalıdır.")
    if not any(c.islower() for c in password):
        raise ValueError("Yeni şifre en az bir küçük harf içermelidir.")
    if not any(c.isupper() for c in password):
        raise ValueError("Yeni şifre en az bir büyük harf içermelidir.")
    if not any(c.isdigit() for c in password):
        raise ValueError("Yeni şifre en az bir rakam içermelidir.")
    if not any(not c.isalnum() for c in password):
        raise ValueError("Yeni şifre en az bir özel karakter içermelidir.")
