"""Differential expression analysis for two-group designs.

The module is deliberately free of web/database dependencies so it can be
used and tested on its own:

    expr = load_expression("expression.csv")
    groups = load_annotation("annotation.csv")
    result = differential_expression(expr, groups, reference_group="control")

Statistics
----------
* Values are log2(x + pseudocount) transformed (optional, for linear-scale input).
* log2 fold change = mean(comparison group) - mean(reference group) on the log2 scale.
* p-values: Welch's two-sample t-test (unequal variances).
* Multiple-testing correction: Benjamini-Hochberg false discovery rate.
"""

from __future__ import annotations

import io
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import IO

import numpy as np
import pandas as pd
from scipy import stats

CsvSource = str | Path | IO[str] | IO[bytes] | bytes

MIN_SAMPLES_PER_GROUP = 2

RESULT_COLUMNS = [
    "gene",
    "mean_reference",
    "mean_comparison",
    "log2_fold_change",
    "t_statistic",
    "p_value",
    "p_adjusted",
]


class AnalysisInputError(ValueError):
    """Raised when the input files cannot be analysed. The message is user-facing."""


@dataclass(frozen=True)
class GroupDesign:
    reference: str
    comparison: str
    reference_samples: list[str]
    comparison_samples: list[str]


# --------------------------------------------------------------------------- #
# Input parsing and validation
# --------------------------------------------------------------------------- #
def _as_text(source: CsvSource) -> str:
    if isinstance(source, (str, Path)) and Path(str(source)).exists():
        return Path(source).read_text(encoding="utf-8-sig")
    if isinstance(source, bytes):
        return source.decode("utf-8-sig")
    if hasattr(source, "read"):
        data = source.read()
        return data.decode("utf-8-sig") if isinstance(data, bytes) else data
    raise AnalysisInputError(f"Unsupported input source: {source!r}")


def _detect_delimiter(header_line: str) -> str:
    """Comma, tab or semicolon, whichever occurs most in the header line."""
    counts = {d: header_line.count(d) for d in (",", "\t", ";")}
    best = max(counts, key=counts.get)
    return best if counts[best] > 0 else ","


def _read_csv(source: CsvSource, **kwargs) -> pd.DataFrame:
    try:
        text = _as_text(source)
    except UnicodeDecodeError as exc:
        raise AnalysisInputError("File is not UTF-8 encoded text.") from exc
    if not text.strip():
        raise AnalysisInputError("File is empty.")
    sep = _detect_delimiter(text.splitlines()[0])
    try:
        return pd.read_csv(io.StringIO(text), sep=sep, **kwargs)
    except Exception as exc:  # pandas raises many different exception types
        raise AnalysisInputError(f"Could not parse CSV file: {exc}") from exc


def load_expression(source: CsvSource) -> pd.DataFrame:
    """Read an expression table: first column = gene IDs, other columns = samples."""
    df = _read_csv(source)
    if df.shape[1] < 2:
        raise AnalysisInputError(
            "Expression table needs a gene ID column followed by at least one sample column."
        )
    df = df.set_index(df.columns[0])
    df.index = df.index.astype(str).str.strip()
    df.index.name = "gene"
    df.columns = [str(c).strip() for c in df.columns]

    if df.index.duplicated().any():
        dupes = sorted(set(df.index[df.index.duplicated()]))[:5]
        raise AnalysisInputError(f"Duplicate gene IDs in expression table: {', '.join(dupes)}")
    if pd.Index(df.columns).duplicated().any():
        raise AnalysisInputError("Duplicate sample names in expression table header.")

    numeric = df.apply(pd.to_numeric, errors="coerce")
    bad = numeric.isna() & df.notna()
    if bad.any().any():
        gene, sample = bad.stack()[bad.stack()].index[0]
        raise AnalysisInputError(
            f"Non-numeric value in expression table (gene '{gene}', sample '{sample}')."
        )
    if numeric.isna().any().any():
        n_missing = int(numeric.isna().sum().sum())
        raise AnalysisInputError(
            f"Expression table contains {n_missing} missing value(s); please impute or remove them."
        )
    if numeric.empty:
        raise AnalysisInputError("Expression table contains no genes.")
    return numeric.astype(float)


def load_annotation(source: CsvSource) -> pd.Series:
    """Read a sample annotation file with columns `sample` and `group`.

    Header names are matched case-insensitively. Without such headers the first
    two columns are used as sample and group.
    """
    df = _read_csv(source, dtype=str)
    cols = {c.strip().lower(): c for c in df.columns}
    if "sample" in cols and "group" in cols:
        df = df[[cols["sample"], cols["group"]]]
    elif df.shape[1] >= 2:
        df = df.iloc[:, :2]
    else:
        raise AnalysisInputError("Annotation file needs two columns: sample and group.")
    df.columns = ["sample", "group"]
    df = df.dropna(how="all")
    df["sample"] = df["sample"].str.strip()
    df["group"] = df["group"].str.strip()
    if df["sample"].isna().any() or df["group"].isna().any() or (df["group"] == "").any():
        raise AnalysisInputError("Annotation file has rows with a missing sample or group.")
    if df["sample"].duplicated().any():
        raise AnalysisInputError("A sample appears more than once in the annotation file.")
    return df.set_index("sample")["group"]


def resolve_design(
    expression: pd.DataFrame,
    annotation: pd.Series,
    reference_group: str | None = None,
) -> GroupDesign:
    """Check that samples match and exactly two groups with enough replicates exist."""
    expr_samples = set(expression.columns)
    ann_samples = set(annotation.index)
    missing = sorted(expr_samples - ann_samples)
    if missing:
        raise AnalysisInputError(
            f"Samples without a group in the annotation file: {', '.join(missing[:10])}"
        )
    # Annotation rows for samples absent from the table are ignored on purpose,
    # so one annotation file can serve several expression tables.
    ann = annotation[annotation.index.isin(expr_samples)]

    groups = sorted(ann.unique())
    if len(groups) != 2:
        raise AnalysisInputError(
            f"Exactly two groups are required, found {len(groups)}: {', '.join(groups)}"
        )
    if reference_group is None:
        reference_group = groups[0]
    if reference_group not in groups:
        raise AnalysisInputError(
            f"Reference group '{reference_group}' not found; available groups: {', '.join(groups)}"
        )
    comparison_group = groups[1] if reference_group == groups[0] else groups[0]

    ref_samples = [s for s in expression.columns if ann.get(s) == reference_group]
    cmp_samples = [s for s in expression.columns if ann.get(s) == comparison_group]
    for name, samples in ((reference_group, ref_samples), (comparison_group, cmp_samples)):
        if len(samples) < MIN_SAMPLES_PER_GROUP:
            raise AnalysisInputError(
                f"Group '{name}' has {len(samples)} sample(s); "
                f"at least {MIN_SAMPLES_PER_GROUP} are needed for a t-test."
            )
    return GroupDesign(reference_group, comparison_group, ref_samples, cmp_samples)


# --------------------------------------------------------------------------- #
# Statistics
# --------------------------------------------------------------------------- #
def benjamini_hochberg(p_values) -> np.ndarray:
    """Benjamini-Hochberg adjusted p-values (FDR). NaNs are kept and ignored."""
    p = np.asarray(p_values, dtype=float)
    adjusted = np.full(p.shape, np.nan)
    mask = ~np.isnan(p)
    pv = p[mask]
    n = pv.size
    if n == 0:
        return adjusted
    order = np.argsort(pv)
    ranked = pv[order] * n / np.arange(1, n + 1)
    # enforce monotonicity from the largest p-value downwards
    ranked = np.minimum.accumulate(ranked[::-1])[::-1]
    out = np.empty(n)
    out[order] = np.clip(ranked, 0.0, 1.0)
    adjusted[mask] = out
    return adjusted


def differential_expression(
    expression: pd.DataFrame,
    annotation: pd.Series,
    reference_group: str | None = None,
    log_transform: bool = True,
    pseudocount: float = 1.0,
) -> tuple[pd.DataFrame, GroupDesign]:
    """Per-gene log2 fold change, Welch t-test p-value and BH-adjusted p-value.

    Returns the result table (sorted by p-value, NaNs last) and the resolved design.
    Genes with zero variance in both groups get NaN statistics and are excluded
    from the multiple-testing correction.
    """
    design = resolve_design(expression, annotation, reference_group)

    values = expression
    if log_transform:
        if (values < 0).any().any():
            raise AnalysisInputError(
                "Negative values found. If the data are already log-transformed, "
                "disable the log2 transformation."
            )
        values = np.log2(values + pseudocount)

    ref = values[design.reference_samples].to_numpy()
    cmp_ = values[design.comparison_samples].to_numpy()

    mean_ref = ref.mean(axis=1)
    mean_cmp = cmp_.mean(axis=1)
    with np.errstate(divide="ignore", invalid="ignore"), warnings.catch_warnings():
        # constant genes trigger precision warnings; they are set to NaN below
        warnings.simplefilter("ignore", RuntimeWarning)
        t_stat, p_val = stats.ttest_ind(cmp_, ref, axis=1, equal_var=False)
    t_stat = np.asarray(t_stat, dtype=float)
    p_val = np.asarray(p_val, dtype=float)

    # Zero variance in both groups: the test is undefined -> report NaN, not 0 or 1.
    no_variance = (ref.var(axis=1, ddof=1) == 0) & (cmp_.var(axis=1, ddof=1) == 0)
    t_stat[no_variance] = np.nan
    p_val[no_variance] = np.nan

    result = pd.DataFrame(
        {
            "gene": values.index.astype(str),
            "mean_reference": mean_ref,
            "mean_comparison": mean_cmp,
            "log2_fold_change": mean_cmp - mean_ref,
            "t_statistic": t_stat,
            "p_value": p_val,
            "p_adjusted": benjamini_hochberg(p_val),
        }
    )
    result = result.sort_values("p_value", na_position="last", kind="mergesort")
    return result.reset_index(drop=True)[RESULT_COLUMNS], design
