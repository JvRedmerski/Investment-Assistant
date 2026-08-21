"""Turning an endpoint's response into a fact pack.

One builder per `ExplanationTopic`, and each builder reads exactly one
already-computed response object. That is the narrow waist of this wave:
**everything the model will ever see passes through this module**, so
the rule that it may not calculate is enforced in one readable place
rather than trusted to a prompt.

Three properties every builder holds to:

- **Nothing is computed here either.** A builder selects, labels and
  renders; it never adds, divides or compares. The single exception is
  `formatting.percent`'s multiplication by 100, which is unit conversion
  and lives in one function.
- **Absent facts are kept.** A `None` becomes a fact with a dash, not a
  missing line, so the prompt can forbid explaining it (rule 44).
- **Every fact names its endpoint.** `source` is the path a reader can
  call to see the same number, which is what makes the prose auditable
  (rule 112).

Rule 43 also applies in the negative here: no threshold, weight or
business rule is written into a label. When the plan says an asset was
`limited_by` a sector ceiling, the ceiling arrives as its own fact with
its own value — it is never described in prose the model has to trust.
"""

from app.domain.ai import formatting
from app.domain.ai.schemas import ExplanationTopic, Fact, FactPack, FactUnit
from app.domain.benchmarks.schemas import (
    BenchmarkComparisonResponse,
    SeriesPerformanceResponse,
)
from app.domain.recommendations.schemas import (
    AssetScoreResponse,
    ContributionPlanResponse,
)

#: How many plan lines and how many skipped candidates reach the model.
#:
#: A cap rather than the whole list, because a prompt that grows with the
#: portfolio eventually truncates *somewhere* — and a silent truncation
#: inside the vendor's token limit would drop facts without saying so.
#: Cutting here is visible: the count of what was left out is itself a
#: fact (`plan.lines_omitted`).
MAX_PLAN_LINES = 8
MAX_SKIPPED_LINES = 5

_TRUNCATED_KEY = "plan.lines_omitted"


def _fact(
    key: str,
    label: str,
    value: object | None,
    formatted: str,
    unit: FactUnit,
    source: str,
) -> Fact:
    """Assemble one fact, serialising `value` without ever seeing a float."""
    return Fact(
        key=key,
        label=label,
        value=None if value is None else str(value),
        formatted=formatted,
        unit=unit,
        source=source,
    )


def _series_facts(
    prefix: str,
    label_prefix: str,
    series: SeriesPerformanceResponse,
    source: str,
) -> list[Fact]:
    """The four standalone figures one side of a comparison reports."""
    return [
        _fact(
            f"{prefix}.total_return",
            f"{label_prefix} — retorno acumulado no período",
            series.total_return,
            formatting.percent(series.total_return),
            FactUnit.PERCENT,
            source,
        ),
        _fact(
            f"{prefix}.annualised_return",
            f"{label_prefix} — retorno anualizado",
            series.annualised_return,
            formatting.percent(series.annualised_return),
            FactUnit.PERCENT,
            source,
        ),
        _fact(
            f"{prefix}.volatility",
            f"{label_prefix} — volatilidade anualizada",
            series.volatility,
            formatting.percent(series.volatility),
            FactUnit.PERCENT,
            source,
        ),
        _fact(
            f"{prefix}.max_drawdown",
            f"{label_prefix} — maior queda desde um topo (max drawdown)",
            series.max_drawdown,
            formatting.percent(series.max_drawdown),
            FactUnit.PERCENT,
            source,
        ),
    ]


def portfolio_performance_facts(
    portfolio_name: str,
    portfolio_id: int,
    comparison: BenchmarkComparisonResponse,
) -> FactPack:
    """Facts for "estou batendo o benchmark?".

    The window is stated once, up front, because both sides of a
    comparison are already cut to the span they share (W11-004): the
    dates below describe the portfolio *and* the benchmark, and a reader
    who assumes otherwise is reading the bug that wave fixed.
    """
    code = comparison.benchmark_code
    source = f"GET /api/v1/portfolios/{portfolio_id}/benchmarks/{code}"
    window = comparison.subject

    facts: list[Fact] = [
        _fact(
            "benchmark.name",
            "Benchmark comparado",
            comparison.benchmark_name,
            comparison.benchmark_name,
            FactUnit.TEXT,
            source,
        ),
        _fact(
            "window.start",
            "Início da janela medida (comum aos dois lados)",
            window.start_date,
            formatting.short_date(window.start_date),
            FactUnit.DATE,
            source,
        ),
        _fact(
            "window.end",
            "Fim da janela medida (comum aos dois lados)",
            window.end_date,
            formatting.short_date(window.end_date),
            FactUnit.DATE,
            source,
        ),
        _fact(
            "window.observations",
            "Observações na janela",
            window.observations,
            formatting.count(window.observations),
            FactUnit.COUNT,
            source,
        ),
    ]

    facts += _series_facts("portfolio", "Carteira", comparison.subject, source)
    facts += _series_facts(
        "benchmark", comparison.benchmark_name, comparison.benchmark, source
    )

    facts += [
        _fact(
            "comparison.excess_return",
            f"Excesso da carteira sobre o {comparison.benchmark_name}",
            comparison.excess_return,
            formatting.points(comparison.excess_return),
            FactUnit.POINTS,
            source,
        ),
        # A multiple in the database (1.15) and "115% do CDI" to a
        # Brazilian investor, which is why it is rendered as a percent
        # and not as a ratio. Null unless both returns were positive —
        # outside that case the idiom states the opposite of the truth.
        _fact(
            "comparison.return_ratio",
            f"Retorno da carteira como percentual do {comparison.benchmark_name}",
            comparison.return_ratio,
            formatting.percent(comparison.return_ratio),
            FactUnit.PERCENT,
            source,
        ),
        _fact(
            "comparison.beta",
            "Beta da carteira contra o benchmark",
            comparison.beta,
            formatting.decimal_value(comparison.beta),
            FactUnit.DECIMAL,
            source,
        ),
        _fact(
            "comparison.sharpe",
            "Índice de Sharpe da carteira",
            comparison.sharpe,
            formatting.decimal_value(comparison.sharpe),
            FactUnit.DECIMAL,
            source,
        ),
        _fact(
            "comparison.sortino",
            "Índice de Sortino da carteira",
            comparison.sortino,
            formatting.decimal_value(comparison.sortino),
            FactUnit.DECIMAL,
            source,
        ),
        _fact(
            "comparison.risk_free_rate",
            "Taxa livre de risco usada no Sharpe e no Sortino",
            comparison.risk_free_rate,
            formatting.percent(comparison.risk_free_rate),
            FactUnit.PERCENT,
            source,
        ),
    ]

    return FactPack(
        topic=ExplanationTopic.PORTFOLIO_PERFORMANCE,
        subject=portfolio_name,
        facts=tuple(facts),
    )


def contribution_plan_facts(
    portfolio_name: str,
    plan: ContributionPlanResponse,
) -> FactPack:
    """Facts for "onde colocar o próximo aporte, e por quê?".

    Both the money and the reasons travel: every funded line carries the
    rule that sized it (`limited_by`), and every skipped candidate
    carries the rule that stopped it. The model is therefore never in
    the position of having to guess *why* — which is the position in
    which it would invent one.
    """
    source = f"GET /api/v1/portfolios/{plan.portfolio_id}/contribution-plan"

    facts: list[Fact] = [
        _fact(
            "plan.contribution",
            "Valor do aporte a distribuir",
            plan.contribution,
            formatting.money(plan.contribution),
            FactUnit.CURRENCY_BRL,
            source,
        ),
        _fact(
            "plan.allocated",
            "Valor efetivamente alocado pelo plano",
            plan.allocated,
            formatting.money(plan.allocated),
            FactUnit.CURRENCY_BRL,
            source,
        ),
        _fact(
            "plan.unallocated",
            "Valor que os limites deixaram sem destino",
            plan.unallocated,
            formatting.money(plan.unallocated),
            FactUnit.CURRENCY_BRL,
            source,
        ),
        _fact(
            "plan.base_value",
            "Base de cálculo dos pesos (carteira já com o aporte dentro)",
            plan.base_value,
            formatting.money(plan.base_value),
            FactUnit.CURRENCY_BRL,
            source,
        ),
        _fact(
            "policy.max_asset_weight",
            "Teto de peso por ativo",
            plan.policy.max_asset_weight,
            formatting.percent(plan.policy.max_asset_weight),
            FactUnit.PERCENT,
            source,
        ),
        _fact(
            "policy.max_sector_weight",
            "Teto de peso por setor",
            plan.policy.max_sector_weight,
            formatting.percent(plan.policy.max_sector_weight),
            FactUnit.PERCENT,
            source,
        ),
        _fact(
            "policy.min_ticket",
            "Ticket mínimo por ativo",
            plan.policy.min_ticket,
            formatting.money(plan.policy.min_ticket),
            FactUnit.CURRENCY_BRL,
            source,
        ),
        _fact(
            "plan.rules_version",
            "Versão das regras de alocação",
            plan.rules_version,
            plan.rules_version,
            FactUnit.TEXT,
            source,
        ),
        _fact(
            "plan.formula_version",
            "Versão da fórmula de score consumida",
            plan.formula_version,
            plan.formula_version,
            FactUnit.TEXT,
            source,
        ),
    ]

    for allocation in plan.allocations[:MAX_PLAN_LINES]:
        prefix = f"allocation.{allocation.ticker}"
        rank = allocation.rank
        facts += [
            _fact(
                f"{prefix}.amount",
                f"{allocation.ticker} — valor alocado (posição {rank} do plano)",
                allocation.amount,
                formatting.money(allocation.amount),
                FactUnit.CURRENCY_BRL,
                source,
            ),
            _fact(
                f"{prefix}.final_score",
                f"{allocation.ticker} — score final (0 a 100)",
                allocation.final_score,
                formatting.decimal_value(allocation.final_score),
                FactUnit.SCORE,
                source,
            ),
            _fact(
                f"{prefix}.coverage",
                f"{allocation.ticker} — cobertura da fórmula que o score usou",
                allocation.coverage,
                formatting.percent(allocation.coverage),
                FactUnit.PERCENT,
                source,
            ),
            _fact(
                f"{prefix}.weight_before",
                f"{allocation.ticker} — peso na carteira antes do aporte",
                allocation.weight_before,
                formatting.percent(allocation.weight_before),
                FactUnit.PERCENT,
                source,
            ),
            _fact(
                f"{prefix}.weight_after",
                f"{allocation.ticker} — peso na carteira depois do aporte",
                allocation.weight_after,
                formatting.percent(allocation.weight_after),
                FactUnit.PERCENT,
                source,
            ),
            _fact(
                f"{prefix}.limited_by",
                f"{allocation.ticker} — regra que limitou o valor",
                allocation.limited_by,
                allocation.limited_by,
                FactUnit.TEXT,
                source,
            ),
        ]

    for skipped in plan.skipped[:MAX_SKIPPED_LINES]:
        detail = f"{skipped.reason}: {skipped.detail}"
        facts.append(
            _fact(
                f"skipped.{skipped.ticker}.reason",
                f"{skipped.ticker} — motivo de não receber nada",
                detail,
                detail,
                FactUnit.TEXT,
                source,
            )
        )

    omitted = max(len(plan.allocations) - MAX_PLAN_LINES, 0) + max(
        len(plan.skipped) - MAX_SKIPPED_LINES, 0
    )
    facts.append(
        _fact(
            _TRUNCATED_KEY,
            "Linhas do plano não enviadas ao modelo (corte por tamanho)",
            omitted,
            formatting.count(omitted),
            FactUnit.COUNT,
            source,
        )
    )

    return FactPack(
        topic=ExplanationTopic.CONTRIBUTION_PLAN,
        subject=portfolio_name,
        facts=tuple(facts),
    )


def asset_score_facts(score: AssetScoreResponse, portfolio_id: int) -> FactPack:
    """Facts for "por que este ativo pontua assim?".

    `coverage` is sent for the whole score *and* as each pillar's list of
    absences, because coverage is required reading rather than a
    footnote: two scores built on different fractions of the formula are
    not comparable, and an explanation that omits that is worse than no
    explanation.
    """
    source = f"GET /api/v1/portfolios/{portfolio_id}/scores"

    facts: list[Fact] = [
        _fact(
            "asset.ticker",
            "Ativo",
            score.ticker,
            score.ticker,
            FactUnit.TEXT,
            source,
        ),
        _fact(
            "asset.sector",
            "Setor",
            score.sector,
            score.sector or formatting.ABSENT,
            FactUnit.TEXT,
            source,
        ),
        _fact(
            "score.final",
            "Score final do ativo (0 a 100)",
            score.final_score,
            formatting.decimal_value(score.final_score),
            FactUnit.SCORE,
            source,
        ),
        _fact(
            "score.coverage",
            "Fração da fórmula que o score de fato cobre",
            score.coverage,
            formatting.percent(score.coverage),
            FactUnit.PERCENT,
            source,
        ),
        _fact(
            "score.formula_version",
            "Versão da fórmula de score",
            score.formula_version,
            score.formula_version,
            FactUnit.TEXT,
            source,
        ),
    ]

    for sub in score.sub_scores:
        prefix = f"pillar.{sub.name}"
        facts += [
            _fact(
                f"{prefix}.value",
                f"Pilar {sub.name} — nota (0 a 100)",
                sub.value,
                formatting.decimal_value(sub.value),
                FactUnit.SCORE,
                source,
            ),
            _fact(
                f"{prefix}.weight",
                f"Pilar {sub.name} — peso na fórmula",
                sub.weight,
                formatting.percent(sub.weight),
                FactUnit.PERCENT,
                source,
            ),
        ]
        if sub.missing:
            missing = ", ".join(sub.missing)
            facts.append(
                _fact(
                    f"{prefix}.missing",
                    f"Pilar {sub.name} — insumos ausentes",
                    missing,
                    missing,
                    FactUnit.TEXT,
                    source,
                )
            )

    return FactPack(
        topic=ExplanationTopic.ASSET_SCORE,
        subject=score.ticker,
        facts=tuple(facts),
    )
