from __future__ import annotations

from dataclasses import asdict, dataclass
from statistics import NormalDist

from app.core.formatting import tr_number


@dataclass(frozen=True)
class CapitalResult:
    expected_loss: float
    unexpected_loss: float
    credit_var: float
    economic_capital: float
    confidence: float
    method: str
    governance_status: str

    def asdict(self) -> dict:
        return asdict(self)


def analytical_credit_var_capital(
    pd: float,
    lgd: float,
    ead: float,
    confidence: float = 0.99,
    governance_status: str = "pilot",
) -> CapitalResult:
    """
    Şeffaf tek-kredi sermaye adapter'ı.

    Kayıp bileşeni L=I×EAD×LGD kabul edilir. EL ve UL Bernoulli kayıp
    dağılımından gelir. Credit VaR, EL + z×UL analitik yaklaşımıyla hesaplanır
    ve fiziksel azami kayıp EAD×LGD ile sınırlandırılır. Ekonomik sermaye
    Credit VaR - EL'dir.

    Bu yöntem bankanın düzenleyici/ICAAP motoru değildir. Production'da
    politika düzeyinde kurum onayı olmadan karar guardrail'inde kullanılamaz.
    """
    if not 0 <= pd <= 1:
        raise ValueError("PD 0 ile 1 arasında olmalıdır.")
    if not 0 <= lgd <= 1:
        raise ValueError("LGD 0 ile 1 arasında olmalıdır.")
    if ead < 0:
        raise ValueError("EAD negatif olamaz.")
    if not 0.5 < confidence < 1:
        raise ValueError("Sermaye güven düzeyi 0.50 ile 1 arasında olmalıdır.")
    severity = ead * lgd
    el = pd * severity
    ul = severity * (max(pd * (1.0 - pd), 0.0) ** 0.5)
    z = NormalDist().inv_cdf(confidence)
    credit_var = min(severity, max(0.0, el + z * ul))
    ec = max(0.0, credit_var - el)
    return CapitalResult(
        expected_loss=el,
        unexpected_loss=ul,
        credit_var=credit_var,
        economic_capital=ec,
        confidence=confidence,
        method=f"Analitik Credit VaR (%{tr_number(confidence * 100, 1)}) − EL",
        governance_status=governance_status,
    )
