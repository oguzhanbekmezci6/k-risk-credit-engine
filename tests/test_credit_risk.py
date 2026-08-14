import math

from app.decision.credit_risk import (
    CreditExposure,
    StressScenario,
    ead_from_commitment,
    monte_carlo_portfolio,
    portfolio_analytic_metrics,
    single_exposure_metrics,
    stress_portfolio,
)


def test_ead_ccf_formula():
    r = ead_from_commitment(300_000, 200_000, 0.5)
    assert r["ead"] == 400_000
    assert r["converted_undrawn"] == 100_000


def test_single_expected_and_unexpected_loss():
    x = CreditExposure("A", 0.08, 0.5, 1_000_000, "bireysel")
    r = single_exposure_metrics(x, 0.99)
    assert r["expected_loss"] == 40_000
    assert math.isclose(r["unexpected_loss"], 500_000 * math.sqrt(.08 * .92))
    assert r["recovery_rate"] == 0.5


def test_portfolio_el_is_sum_and_correlation_increases_ul():
    xs = [
        CreditExposure("A", .05, .5, 100_000, "perakende"),
        CreditExposure("B", .10, .4, 200_000, "otomotiv"),
    ]
    a = portfolio_analytic_metrics(xs, 0.0)
    b = portfolio_analytic_metrics(xs, 0.25)
    assert math.isclose(a["expected_loss"], 10_500)
    assert b["unexpected_loss"] >= a["unexpected_loss"]
    assert len(b["sector_concentration"]) == 2


def test_stress_increases_expected_loss():
    xs = [CreditExposure("A", .05, .45, 1_000_000, "kobi")]
    r = stress_portfolio(xs, [StressScenario("Baz"), StressScenario("Ağır", 2, 1.2, 1.1)], .15)
    assert r["results"][1]["expected_loss"] > r["results"][0]["expected_loss"]
    assert r["worst_scenario"] == "Ağır"


def test_monte_carlo_reproducible():
    xs = [CreditExposure("A", .10, .5, 100_000, "a"), CreditExposure("B", .08, .6, 120_000, "b")]
    a = monte_carlo_portfolio(xs, simulations=1200, asset_correlation=.15, seed=42)
    b = monte_carlo_portfolio(xs, simulations=1200, asset_correlation=.15, seed=42)
    assert a["credit_var_99"] == b["credit_var_99"]
    assert a["analytical_expected_loss"] == b["analytical_expected_loss"]
