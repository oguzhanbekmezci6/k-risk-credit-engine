from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
import socket
import threading
import time
import webbrowser

# PyCharm / yerel demo tek-tık kullanım içindir. Production deployment bu dosyayı kullanmamalıdır.
os.environ.setdefault("KRISK_MODE", "demo")
os.environ.setdefault("KRISK_COOKIE_SECURE", "false")


def ensure_demo_pdf_dependency() -> None:
    """Karar raporu için ReportLab yoksa yalnız demo modunda kurar."""
    if os.environ.get("KRISK_MODE", "demo").lower() != "demo":
        return
    if importlib.util.find_spec("reportlab") is None:
        print("K-Risk rapor bileşeni kuruluyor (reportlab)...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "reportlab==4.4.9"])


ensure_demo_pdf_dependency()

import uvicorn

from app.core.config import HOST, MODE, PORT
from app.infra.db import init_db


def find_available_port(host: str, preferred: int) -> int:
    for port in range(preferred, preferred + 20):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(0.15)
            if sock.connect_ex((host, port)) != 0:
                return port
    raise RuntimeError("8765-8784 aralığında boş yerel port bulunamadı.")


def open_browser(port: int):
    time.sleep(1.1)
    webbrowser.open(f"http://{HOST}:{port}")


if __name__ == "__main__":
    init_db()
    selected_port = find_available_port(HOST, PORT)
    print("\nK-RİSK V14 - Karar Motoru")
    print("============================================================================")
    print(f"Mod: {MODE}")
    if selected_port != PORT:
        print(f"Not: {PORT} portu kullanımda. K-Risk otomatik olarak {selected_port} portuna geçti.")
    print(f"Adres: http://{HOST}:{selected_port}")
    print("İlk kullanımda tarayıcıdan kendi Yönetici hesabınızı oluşturabilirsiniz.\n")
    threading.Thread(target=open_browser, args=(selected_port,), daemon=True).start()
    uvicorn.run("app.main:app", host=HOST, port=selected_port, reload=False)
