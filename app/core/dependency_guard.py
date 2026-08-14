from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

# requirements.txt tam sürümlere sabitlenmiştir.
MINIMUMS = {
    "fastapi": (0, 141, 1),
    "starlette": (1, 4, 1),
    "reportlab": (4, 4, 9),
}


def _numeric_tuple(raw: str) -> tuple[int, ...]:
    out: list[int] = []
    for part in raw.split("."):
        digits = "".join(ch for ch in part if ch.isdigit())
        if not digits:
            break
        out.append(int(digits))
    return tuple(out)


def verify_runtime_dependencies() -> None:
    problems: list[str] = []
    for package, minimum in MINIMUMS.items():
        try:
            installed = version(package)
        except PackageNotFoundError:
            problems.append(f"{package} kurulu değil")
            continue
        parsed = _numeric_tuple(installed)
        padded = parsed + (0,) * max(0, len(minimum) - len(parsed))
        if padded[: len(minimum)] < minimum:
            required = ".".join(map(str, minimum))
            problems.append(f"{package} {installed} < {required}")
    if problems:
        joined = "; ".join(problems)
        raise RuntimeError(
            "Güvenlik için gereken bağımlılık tabanı sağlanmıyor: " + joined + ". "
            "'pip install -r requirements.txt' komutuyla sabitlenmiş sürümleri kurun."
        )
