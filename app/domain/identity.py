from __future__ import annotations

import unicodedata


def normalize_username(value: str) -> str:
    """Yerel/demo kullanıcı adını güvenli ve tutarlı biçimde normalize eder.

    Türkçe harfler dahil Unicode harf/rakamlar ile . _ - karakterlerine izin verir.
    Production ortamında kullanıcı kimliği bankanın IAM/SSO katmanından gelmelidir.
    """
    username = unicodedata.normalize("NFKC", (value or "").strip()).casefold().replace("i\u0307", "i")
    if not 3 <= len(username) <= 64:
        raise ValueError("Kullanıcı adı 3-64 karakter arasında olmalıdır.")
    if any(ch.isspace() for ch in username):
        raise ValueError("Kullanıcı adında boşluk kullanılamaz.")
    if not all(ch.isalnum() or ch in "._-" for ch in username):
        raise ValueError("Kullanıcı adı yalnızca harf, rakam, nokta, alt çizgi veya tire içerebilir.")
    return username
