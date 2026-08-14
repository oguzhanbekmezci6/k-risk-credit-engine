from __future__ import annotations

import getpass
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.infra.db import create_user, ensure_schema
from app.infra.security import validate_new_password


def main() -> None:
    ensure_schema()
    print("K-Risk güvenli kullanıcı oluşturma")
    username = input("Kullanıcı adı: ").strip().lower()
    role = input("Rol [admin/risk_manager/analyst]: ").strip()
    password = getpass.getpass("Şifre: ")
    confirm = getpass.getpass("Şifre tekrar: ")
    if password != confirm:
        raise SystemExit("Şifreler aynı değil.")
    validate_new_password(password)
    created = create_user(username, password, role, must_change_password=True)
    print(f"Kullanıcı oluşturuldu: {created['username']} ({created['role']}). İlk girişte şifre değişikliği zorunlu.")


if __name__ == "__main__":
    main()
