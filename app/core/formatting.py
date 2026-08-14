from __future__ import annotations


def tr_number(value: float | int, decimals: int = 0) -> str:
    """Format a number using Turkish separators: 1.234.567,89."""
    rendered = f"{float(value):,.{decimals}f}"
    return rendered.replace(",", "\u0000").replace(".", ",").replace("\u0000", ".")


def tr_money(value: float | int, decimals: int = 0) -> str:
    return f"{tr_number(value, decimals)} TL"


def tr_percent_ratio(value: float | int, decimals: int = 1) -> str:
    return f"%{tr_number(float(value) * 100, decimals)}"
