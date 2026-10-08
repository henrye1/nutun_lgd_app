"""RunConfig: every parameter of spec §8, with the PARITY_JUL26 and CORRECTED presets."""
from __future__ import annotations

import csv
from collections.abc import Callable
from datetime import date
from importlib import resources
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

FitMode = Literal["THREE_PARAM", "TWO_PARAM_FIXED_MU", "MANUAL"]
RuleSet = Literal["ROLLING", "VALUATION_CALC"]


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", validate_assignment=True)


class FixedMuRow(_Frozen):
    k: int = Field(ge=0)
    month: date
    vb: int
    mu: float


class RunSection(_Frozen):
    report_month: date = date(2026, 7, 1)
    extract_month: date | None = None  # None = MAX(PaymentMonth) of the snapshot
    book_list_source: Literal["ACM_VB_ALLOC", "INFO", "UNIVERSE"] = "ACM_VB_ALLOC"


class PaymentsSection(_Frozen):
    vb44_rule: Literal["AS_DELIVERED", "REAPPLY_AT_D"] = "AS_DELIVERED"
    exclusion_list: list[int] = [99910293, 99910155]
    exclusion_applied: bool = False  # VALUATION_CALC: Calc!T2 compares text with a number → inert
    # ROLLING: Tranche_Keys!I2 tests Cfg_ApplyExcl=0, but Config!B12 holds the boolean FALSE and Excel's
    # FALSE=0 is FALSE, so the two books ARE excluded from every rolling grid in the July-26 workbooks.
    exclusion_applied_rolling: bool = True


class FliSection(_Frozen):
    missing_hist_month_calc: Literal["ONE", "DROP_AMOUNT"] = "ONE"
    missing_hist_month_rolling: Literal["ONE", "DROP_AMOUNT"] = "DROP_AMOUNT"
    r2_zero: Literal["ZERO", "ONE"] = "ZERO"
    missing_fwd_month: Literal["ZERO", "ONE_AND_WARN"] = "ZERO"


class CurvesSection(_Frozen):
    cohorts: list[int] = [11, 15, 22, 23, 25, 44]
    n_months: int = Field(default=8, ge=1)
    t_grid: int = Field(default=60, ge=1)
    ndata: int = Field(default=61, ge=1)
    max_age: int = 60
    max_age_vb44: int = 61
    min_bal_ratio: float = 0.10
    min_nho: int = 5
    min_fit_points: int = 12
    vb25_young_age_excl: int = 3
    calc_offset: int = 0
    offset_basis: Literal["PER_TRANCHE_LAST_PAYMENT", "GLOBAL_CUTOFF"] = "PER_TRANCHE_LAST_PAYMENT"
    mbound: dict[int, float] = {11: 100, 15: 100, 22: 100, 23: 100, 25: 100, 44: 3.25}
    fit_mode: dict[int, FitMode] = {vb: "TWO_PARAM_FIXED_MU" for vb in (11, 15, 22, 23, 25, 44)}
    fixed_mu: list[FixedMuRow] = []
    alpha: float = 0.10
    ma_window: int = Field(default=6, ge=1)
    valuation_source: Literal["MA_OF_FITS", "SINGLE_FIT", "UPLOADED"] = "MA_OF_FITS"
    ma_fit_mode: FitMode = "TWO_PARAM_FIXED_MU"
    ma_missing: Literal["SKIP_AND_WARN", "FAIL"] = "SKIP_AND_WARN"
    t_max: int = Field(default=500, ge=120)


class FitSection(_Frozen):
    engine: Literal["LM_PORT", "SCIPY_TRF"] = "LM_PORT"
    lifetime_horizon: int = 120  # Lifetime = Σ f(t), t = 1..120 (Cohort!B18)
    # the fixed starting points of modRollingFitLM (the warm start is prepended at run time)
    starts: list[tuple[float, float, float]] = [
        (4.0, 1.7, 0.3),
        (5.0, 1.2, 0.6),
        (3.0, 2.5, 0.15),
        (6.0, 2.0, 1.0),
        (2.0, 1.0, 0.5),
    ]


class BoundsSection(_Frozen):
    data_rule_set: RuleSet = "VALUATION_CALC"
    data_k: int = 0
    params_fit_mode: FitMode = "THREE_PARAM"
    params_k: int = 1
    # Where the bound-curve parameters come from (finding 2026-10-08, supersedes §9 Q9 for 5 of 6 VBs):
    #   VALUATION_CALC_FIT = fit the VALUATION_CALC grid itself (the valuation Cohort sheets own Solver fits);
    #   ROLLING_FIT = the rolling fit at (params_fit_mode, params_k); MANUAL = manual_params per VB.
    # params_vb_override sends single VBs elsewhere: the VB11 valuation params are the rolling k=1 3P fit.
    params_source: Literal["VALUATION_CALC_FIT", "ROLLING_FIT", "MANUAL"] = "VALUATION_CALC_FIT"
    params_vb_override: dict[int, tuple[Literal["ROLLING", "VALUATION_CALC"], int]] = {11: ("ROLLING", 1)}
    manual_params: dict[int, tuple[float, float, float]] | None = None
    points: Literal["KEPT", "CONTIGUOUS_PREFIX"] = "CONTIGUOUS_PREFIX"
    p_rule: Literal["M_AT_BOUND_ONLY", "FIXED_MU_IS_2"] = "M_AT_BOUND_ONLY"  # Q14
    q12_vb15_blank_from_vb11: bool = True  # Q12: Curves!I5:I503 tests Cohort_11 for the VB15 upper bound
    # Q22: the valuation Cohort_xx sheets sum X'WX / P (AF5:AF10, AF20:AF22) and the ±1% sensitivity (J4:J9)
    # over hard-coded row ranges per sheet; they end before the last used point for VB15, VB22 and VB44.
    matrix_t_max: dict[int, int] | None = {11: 61, 15: 53, 22: 55, 23: 48, 25: 48, 44: 48}
    sensitivity_t_max: dict[int, int] | None = {11: 61, 15: 53, 22: 55, 23: 43, 25: 26, 44: 48}
    sse_t_max: dict[int, int] | None = {11: 61, 15: 55, 22: 57, 23: 48, 25: 48, 44: 48}  # Cohort!B12 ranges


class ValuationSection(_Frozen):
    horizon: int = Field(default=120, ge=1)
    disc_time: float = 0.43
    age_capping: int = 12
    bound_age: int | None = 12  # None = age_capping
    delta_window: int = Field(default=36, ge=1)
    delta_floor: float = 0.10
    delta_window_alignment: Literal["PAYMENT_MONTH_BACKSTOP", "AGE_INDEX"] = "PAYMENT_MONTH_BACKSTOP"
    age_basis: Literal["EXAMPLE_MIN", "AGE_CO", "MAX_COUNT", "INFO_ROLLED"] = "EXAMPLE_MIN"
    month_offset: int = -2
    gross_basis: Literal["PP", "FACE", "CONTRACTUAL"] = "PP"
    vb44_own_yield_sub: bool = False


class CappingSection(_Frozen):
    age_test: Literal["COUNT_T1", "AGE", "N_OBS"] = "COUNT_T1"
    ac_capped_display: Literal["AS_WORKBOOK", "ONLY_WHEN_APPLIES"] = "AS_WORKBOOK"


class CostsSection(_Frozen):
    vb_map: dict[int, str] = {22: "22", 44: "44"}
    default_curve: str = "Rest"


class BookSection(_Frozen):
    vb_source: Literal["ALLOC", "CLIENT"] = "ALLOC"


class ForecastSection(_Frozen):
    cohort_costs: bool = False


class ResultsSection(_Frozen):
    backtest_n_source: Literal["CLIENT_DELTA_ROWS", "OWN_WINDOW"] = "CLIENT_DELTA_ROWS"


class RunConfig(_Frozen):
    preset: str
    run: RunSection = RunSection()
    payments: PaymentsSection = PaymentsSection()
    fli: FliSection = FliSection()
    curves: CurvesSection = CurvesSection()
    fit: FitSection = FitSection()
    bounds: BoundsSection = BoundsSection()
    valuation: ValuationSection = ValuationSection()
    capping: CappingSection = CappingSection()
    costs: CostsSection = CostsSection()
    book: BookSection = BookSection()
    forecast: ForecastSection = ForecastSection()
    results: ResultsSection = ResultsSection()

    def fixed_mu_lookup(self) -> dict[tuple[int, int], float]:
        return {(r.k, r.vb): r.mu for r in self.curves.fixed_mu}

    def quirk_flags(self) -> dict[str, str]:
        """The §9 switches that a run records (Q-id → value)."""
        return {
            "Q1.month_offset": str(self.valuation.month_offset),
            "Q2.missing_fwd_month": self.fli.missing_fwd_month,
            "Q3.bound_age": "age_capping" if self.valuation.bound_age is None else str(self.valuation.bound_age),
            "Q4.exclusion_applied": f"calc={self.payments.exclusion_applied},rolling={self.payments.exclusion_applied_rolling}",
            "Q6.ac_capped_display": self.capping.ac_capped_display,
            "Q8.forecast_cohort_costs": str(self.forecast.cohort_costs),
            "Q9.bounds": f"data={self.bounds.data_rule_set}@k{self.bounds.data_k},"
            f"params={self.bounds.params_source}:{self.bounds.params_fit_mode}@k{self.bounds.params_k},"
            f"override={self.bounds.params_vb_override}",
            "Q13.vb_source": self.book.vb_source,
            "Q14.bounds_points": self.bounds.points,
            "Q14.p_rule": self.bounds.p_rule,
            "Q12.vb15_ub_from_vb11": str(self.bounds.q12_vb15_blank_from_vb11),
            "Q22.valuation_matrix_t_max": "none" if self.bounds.matrix_t_max is None else str(self.bounds.matrix_t_max),
            "Q22.valuation_sse_t_max": "none" if self.bounds.sse_t_max is None else str(self.bounds.sse_t_max),
            "Q22.valuation_sensitivity_t_max": "none" if self.bounds.sensitivity_t_max is None
            else str(self.bounds.sensitivity_t_max),
            "Q16.offset_basis": self.curves.offset_basis,
            "Q17.r2_zero": self.fli.r2_zero,
            "Q18.age_basis": self.valuation.age_basis,
            "Q19.missing_hist_month_rolling": self.fli.missing_hist_month_rolling,
            "Q21.vb44_own_yield_sub": str(self.valuation.vb44_own_yield_sub),
        }


def load_fixed_mu_seed() -> list[FixedMuRow]:
    text = resources.files("nutun_engine").joinpath("data/fixed_mu_jul26.csv").read_text(encoding="utf-8")
    return [
        FixedMuRow(k=int(r["k"]), month=date.fromisoformat(r["month"]), vb=int(r["vb"]), mu=float(r["mu"]))
        for r in csv.DictReader(text.splitlines())
    ]


def parity_jul26() -> RunConfig:
    return RunConfig(preset="PARITY_JUL26", curves=CurvesSection(fixed_mu=load_fixed_mu_seed()))


def corrected() -> RunConfig:
    base = parity_jul26()
    return base.model_copy(
        update={
            "preset": "CORRECTED",
            "payments": base.payments.model_copy(update={"exclusion_applied_rolling": False}),
            "fli": base.fli.model_copy(
                update={"missing_hist_month_rolling": "ONE", "missing_fwd_month": "ONE_AND_WARN"}
            ),
            "curves": base.curves.model_copy(update={"t_max": 600}),
            "bounds": BoundsSection(
                data_rule_set="ROLLING", data_k=0, params_fit_mode="THREE_PARAM", params_k=0, points="KEPT",
                params_source="ROLLING_FIT", params_vb_override={},
                p_rule="FIXED_MU_IS_2", q12_vb15_blank_from_vb11=False, matrix_t_max=None, sensitivity_t_max=None, sse_t_max=None,
            ),
            "valuation": base.valuation.model_copy(update={"month_offset": 0, "bound_age": None}),
            "capping": CappingSection(ac_capped_display="ONLY_WHEN_APPLIES"),
            "forecast": ForecastSection(cohort_costs=True),
        }
    )


PRESETS: dict[str, Callable[[], RunConfig]] = {"PARITY_JUL26": parity_jul26, "CORRECTED": corrected}
