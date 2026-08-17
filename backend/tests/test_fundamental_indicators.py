"""Unit tests for compute_indicators, with known input and known expected
output (AGENTS.md rule 68)."""

from datetime import date
from decimal import Decimal

from app.domain.fundamentals.indicators import IndicatorInputs, compute_indicators


def _inputs(year: int = 2024, **overrides) -> IndicatorInputs:
    values = {
        "reference_date": date(year, 12, 31),
        "revenue": Decimal(1000),
        "net_income": Decimal(150),
        "equity": Decimal(600),
        "debt": Decimal(400),
        "cash": Decimal(100),
    }
    values.update(overrides)
    return IndicatorInputs(**values)


# -- indicators computable from what is ingested today ----------------


def test_roe_is_net_income_over_equity():
    result = compute_indicators(_inputs(net_income=Decimal(150), equity=Decimal(600)))

    assert result.roe == 0.25


def test_net_margin_is_net_income_over_revenue():
    result = compute_indicators(_inputs(net_income=Decimal(150), revenue=Decimal(1000)))

    assert result.net_margin == 0.15


def test_roe_is_reported_when_negative():
    # A loss is a real result, not missing data.
    result = compute_indicators(_inputs(net_income=Decimal(-60), equity=Decimal(600)))

    assert result.roe == -0.1


def test_roe_is_reported_when_equity_is_negative():
    result = compute_indicators(_inputs(net_income=Decimal(60), equity=Decimal(-600)))

    assert result.roe == -0.1


def test_revenue_growth_compares_against_the_previous_period():
    previous = _inputs(2023, revenue=Decimal(800))
    current = _inputs(2024, revenue=Decimal(1000))

    result = compute_indicators(current, previous)

    assert result.revenue_growth == 0.25


def test_profit_growth_compares_against_the_previous_period():
    previous = _inputs(2023, net_income=Decimal(100))
    current = _inputs(2024, net_income=Decimal(150))

    result = compute_indicators(current, previous)

    assert result.profit_growth == 0.5


def test_negative_growth_is_reported():
    previous = _inputs(2023, revenue=Decimal(1000))
    current = _inputs(2024, revenue=Decimal(750))

    result = compute_indicators(current, previous)

    assert result.revenue_growth == -0.25


# -- growth edge cases -------------------------------------------------


def test_growth_is_none_without_a_previous_period():
    result = compute_indicators(_inputs())

    assert result.revenue_growth is None
    assert result.profit_growth is None


def test_growth_is_none_when_the_previous_value_is_missing():
    previous = _inputs(2023, revenue=None)
    current = _inputs(2024, revenue=Decimal(1000))

    result = compute_indicators(current, previous)

    assert result.revenue_growth is None


def test_growth_is_none_when_the_previous_value_is_zero():
    previous = _inputs(2023, revenue=Decimal(0))
    current = _inputs(2024, revenue=Decimal(1000))

    result = compute_indicators(current, previous)

    assert result.revenue_growth is None


def test_growth_is_none_from_a_negative_base():
    # -100 -> -50 halves the loss, but calling that "+50% growth" would
    # read as good news about a company that is still losing money.
    previous = _inputs(2023, net_income=Decimal(-100))
    current = _inputs(2024, net_income=Decimal(-50))

    result = compute_indicators(current, previous)

    assert result.profit_growth is None


# -- indicators blocked by inputs not ingested yet ---------------------


def test_pe_and_pb_are_none_without_shares_outstanding():
    result = compute_indicators(_inputs(price=Decimal(30)))

    assert result.pe is None
    assert result.pb is None


def test_pe_and_pb_are_computed_once_shares_outstanding_is_supplied():
    # Proves the formulas are correct and ready for W06-003.
    result = compute_indicators(
        _inputs(
            price=Decimal(30),
            shares_outstanding=Decimal(100),
            net_income=Decimal(150),
            equity=Decimal(600),
        )
    )

    assert result.pe == 20.0  # EPS = 1.5 -> 30 / 1.5
    assert result.pb == 5.0  # BVPS = 6.0 -> 30 / 6.0


def test_dy_is_none_without_dividend_data():
    result = compute_indicators(_inputs(price=Decimal(30)))

    assert result.dy is None


def test_dy_is_computed_once_dividends_are_supplied():
    result = compute_indicators(
        _inputs(price=Decimal(30), dividends_per_share=Decimal("1.8"))
    )

    assert result.dy == 0.06


def test_ebitda_indicators_are_none_because_ebitda_is_never_ingested():
    # ADR-013: the provider only exposes EBITDA as a TTM snapshot.
    result = compute_indicators(_inputs())

    assert result.debt_ebitda is None
    assert result.ebitda_margin is None


def test_ebitda_indicators_are_computed_once_ebitda_is_supplied():
    result = compute_indicators(
        _inputs(ebitda=Decimal(250), debt=Decimal(500), revenue=Decimal(1000))
    )

    assert result.debt_ebitda == 2.0
    assert result.ebitda_margin == 0.25


def test_roic_is_none_without_ebit_and_tax_rate():
    result = compute_indicators(_inputs())

    assert result.roic is None


def test_roic_is_none_when_only_ebit_is_supplied():
    # No tax rate is assumed: NOPAT without one would be a guess.
    result = compute_indicators(_inputs(ebit=Decimal(300)))

    assert result.roic is None


def test_roic_is_computed_once_ebit_and_tax_rate_are_supplied():
    result = compute_indicators(
        _inputs(
            ebit=Decimal(300),
            effective_tax_rate=Decimal("0.34"),
            debt=Decimal(400),
            equity=Decimal(600),
            cash=Decimal(100),
        )
    )

    # NOPAT = 300 * 0.66 = 198; invested capital = 400 + 600 - 100 = 900
    assert result.roic == 0.22


def test_roic_is_none_when_any_invested_capital_component_is_missing():
    result = compute_indicators(
        _inputs(ebit=Decimal(300), effective_tax_rate=Decimal("0.34"), cash=None)
    )

    assert result.roic is None


# -- missing data and division by zero ---------------------------------


def test_everything_is_none_for_an_input_with_no_figures():
    result = compute_indicators(IndicatorInputs(reference_date=date(2024, 12, 31)))

    assert result == type(result)()  # all fields at their None default


def test_zero_denominator_yields_none_not_an_exception():
    result = compute_indicators(
        _inputs(revenue=Decimal(0), equity=Decimal(0), net_income=Decimal(150))
    )

    assert result.net_margin is None
    assert result.roe is None


def test_zero_numerator_is_a_real_zero_not_none():
    # Breaking even is a measured outcome, unlike missing data.
    result = compute_indicators(_inputs(net_income=Decimal(0)))

    assert result.roe == 0.0
    assert result.net_margin == 0.0


def test_missing_price_yields_none_even_with_shares_outstanding():
    result = compute_indicators(_inputs(price=None, shares_outstanding=Decimal(100)))

    assert result.pe is None
    assert result.pb is None


def test_calculation_is_deterministic():
    inputs = _inputs(price=Decimal(30), shares_outstanding=Decimal(100))
    previous = _inputs(2023, revenue=Decimal(800))

    assert compute_indicators(inputs, previous) == compute_indicators(inputs, previous)
