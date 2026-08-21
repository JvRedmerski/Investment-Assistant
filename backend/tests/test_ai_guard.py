"""Tests for `app.domain.ai.guard`.

The guard is the only thing in this wave that *verifies* rule 44 rather
than asking for it, so its two failure modes both matter: missing an
invented figure makes it useless, and flagging a legitimate one makes it
noise that gets ignored. Both directions are pinned below.
"""

from app.domain.ai.guard import allowed_figures, unverified_figures
from app.domain.ai.schemas import Fact, FactUnit

SOURCE = "GET /api/v1/portfolios/1/benchmarks/CDI"


def _fact(key: str, label: str, value: str | None, formatted: str) -> Fact:
    return Fact(
        key=key,
        label=label,
        value=value,
        formatted=formatted,
        unit=FactUnit.PERCENT,
        source=SOURCE,
    )


FACTS = (
    _fact("portfolio.total_return", "Carteira — retorno acumulado", "0.1238", "12,4%"),
    _fact("benchmark.total_return", "CDI — retorno acumulado", "0.0527", "5,3%"),
    _fact("comparison.excess_return", "Excesso sobre o CDI", "0.0711", "+7,1 p.p."),
    _fact("comparison.beta", "Beta da carteira", None, "—"),
)


def test_prose_that_only_quotes_the_facts_is_clean():
    text = (
        "Sua carteira rendeu 12,4% na janela medida, contra 5,3% do CDI, "
        "um excesso de +7,1 p.p. O beta está indisponível."
    )
    assert unverified_figures(text, FACTS) == ()


def test_a_figure_that_appears_in_no_fact_is_flagged():
    """The failure this whole module exists for: a plausible invention."""
    text = "Sua carteira rendeu 12,4%, bem acima da inflação de 4,8% no período."
    assert unverified_figures(text, FACTS) == ("4,8",)


def test_a_number_the_model_derived_itself_is_flagged():
    """12,4 − 5,3 is arithmetic, and arithmetic is not the model's job."""
    text = "A diferença entre 12,4% e 5,3% é de 7,1 pontos, ou 2,35 vezes o CDI."
    assert unverified_figures(text, FACTS) == ("2,35",)


def test_trailing_zeros_do_not_count_as_a_different_number():
    """`12,40%` and `12,4%` are the same quantity, not a hallucination."""
    assert unverified_figures("A carteira rendeu 12,40%.", FACTS) == ()


def test_a_number_written_in_a_label_may_be_quoted():
    """Labels are backend-authored too, so their figures are legitimate."""
    facts = (_fact("score.final", "Score final do ativo (0 a 100)", "76.72", "76,72"),)
    text = "O score é 76,72 numa escala de 0 a 100."
    assert unverified_figures(text, facts) == ()


def test_the_components_of_a_rendered_date_may_be_quoted():
    facts = (
        Fact(
            key="window.start",
            label="Início da janela",
            value="2021-11-08",
            formatted="08/11/2021",
            unit=FactUnit.DATE,
            source=SOURCE,
        ),
    )
    assert unverified_figures("A janela começa em 08/11/2021.", facts) == ()


def test_a_grouped_thousand_matches_its_formatted_fact():
    facts = (
        Fact(
            key="plan.contribution",
            label="Aporte",
            value="1000.00",
            formatted="R$ 1.000,00",
            unit=FactUnit.CURRENCY_BRL,
            source=SOURCE,
        ),
    )
    assert unverified_figures("O aporte de R$ 1.000,00 foi distribuído.", facts) == ()


def test_an_invented_figure_repeated_is_reported_once():
    text = "A inflação de 4,8% pesou; com 4,8% ao ano o efeito se acumula."
    assert unverified_figures(text, FACTS) == ("4,8",)


def test_flags_come_back_in_order_of_appearance():
    text = "Primeiro 9,9%, depois 3,3%, e por fim 12,4% que é real."
    assert unverified_figures(text, FACTS) == ("9,9", "3,3")


def test_an_unavailable_fact_contributes_no_allowed_figure():
    """A dash is not a licence to write a number for that fact."""
    allowed = allowed_figures((FACTS[3],))
    assert allowed == frozenset()


def test_prose_with_no_numbers_at_all_is_clean():
    text = "Os dados de risco estão indisponíveis para esta janela."
    assert unverified_figures(text, FACTS) == ()
