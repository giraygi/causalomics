import io

import numpy as np
import pandas as pd
import pytest

from app.analysis import (
    AnalysisInputError,
    benjamini_hochberg,
    differential_expression,
    load_annotation,
    load_expression,
    resolve_design,
)
from app.simulate import simulate


@pytest.fixture(scope="module")
def sim():
    return simulate(seed=7)


def _annotation_series(sim):
    return sim.annotation.set_index("sample")["group"]


# --------------------------------------------------------------------------- #
# Statistics on simulated data with a known truth
# --------------------------------------------------------------------------- #
def test_detects_planted_genes(sim):
    result, design = differential_expression(sim.expression, _annotation_series(sim))
    assert design.reference == "control" and design.comparison == "treated"

    significant = set(result.loc[result.p_adjusted < 0.05, "gene"])
    planted = set(sim.true_up) | set(sim.true_down)
    # sensitivity: (almost) all planted genes found
    assert len(planted & significant) >= 18
    # specificity: few false discoveries among the 180 null genes
    assert len(significant - planted) <= 3


def test_fold_change_sign_and_size(sim):
    result, _ = differential_expression(sim.expression, _annotation_series(sim))
    lfc = result.set_index("gene")["log2_fold_change"]
    assert (lfc[sim.true_up] > 1.0).all()
    assert (lfc[sim.true_down] < -1.0).all()
    # effect was simulated as +/-2 on the log2 scale
    assert lfc[sim.true_up].mean() == pytest.approx(2.0, abs=0.4)


def test_reference_group_flips_sign(sim):
    ann = _annotation_series(sim)
    a, _ = differential_expression(sim.expression, ann, reference_group="control")
    b, _ = differential_expression(sim.expression, ann, reference_group="treated")
    merged = a.merge(b, on="gene", suffixes=("_a", "_b"))
    np.testing.assert_allclose(merged.log2_fold_change_a, -merged.log2_fold_change_b)
    np.testing.assert_allclose(merged.p_value_a, merged.p_value_b)


def test_matches_scipy_welch_for_one_gene():
    expr = pd.DataFrame(
        [[1.0, 2.0, 3.0, 10.0, 12.0, 14.0]],
        index=["G1"],
        columns=["a1", "a2", "a3", "b1", "b2", "b3"],
    )
    ann = pd.Series(["A", "A", "A", "B", "B", "B"], index=expr.columns)
    result, _ = differential_expression(expr, ann, log_transform=False)
    from scipy import stats

    expected = stats.ttest_ind([10, 12, 14], [1, 2, 3], equal_var=False)
    assert result.loc[0, "p_value"] == pytest.approx(expected.pvalue)
    assert result.loc[0, "log2_fold_change"] == pytest.approx(10.0)


def test_zero_variance_gene_gets_nan_and_is_excluded_from_fdr():
    expr = pd.DataFrame(
        [[5.0] * 6, [1.0, 2.0, 3.0, 10.0, 12.0, 14.0]],
        index=["FLAT", "G2"],
        columns=["a1", "a2", "a3", "b1", "b2", "b3"],
    )
    ann = pd.Series(["A"] * 3 + ["B"] * 3, index=expr.columns)
    result, _ = differential_expression(expr, ann, log_transform=False)
    result = result.set_index("gene")
    assert np.isnan(result.loc["FLAT", "p_value"])
    assert np.isnan(result.loc["FLAT", "p_adjusted"])
    # only one valid test -> adjusted equals raw
    assert result.loc["G2", "p_adjusted"] == pytest.approx(result.loc["G2", "p_value"])


# --------------------------------------------------------------------------- #
# Benjamini-Hochberg
# --------------------------------------------------------------------------- #
def test_bh_known_values():
    p = [0.01, 0.04, 0.03, 0.20]
    # sorted: 0.01*4/1=0.04, 0.03*4/2=0.06, 0.04*4/3=0.0533 -> monotone 0.0533, 0.20*4/4=0.2
    expected = [0.04, 0.053333, 0.053333, 0.20]
    np.testing.assert_allclose(benjamini_hochberg(p), expected, atol=1e-6)


def test_bh_matches_statsmodels():
    statsmodels = pytest.importorskip("statsmodels.stats.multitest")
    rng = np.random.default_rng(0)
    p = rng.uniform(size=500) ** 2
    ours = benjamini_hochberg(p)
    theirs = statsmodels.multipletests(p, method="fdr_bh")[1]
    np.testing.assert_allclose(ours, theirs)


def test_bh_handles_nan_and_bounds():
    adj = benjamini_hochberg([0.5, np.nan, 0.9, 1.0])
    assert np.isnan(adj[1])
    assert np.nanmax(adj) <= 1.0


# --------------------------------------------------------------------------- #
# Input validation
# --------------------------------------------------------------------------- #
EXPR_CSV = "gene,s1,s2,s3,s4\nG1,1,2,3,4\nG2,5,6,7,8\n"
ANN_CSV = "sample,group\ns1,A\ns2,A\ns3,B\ns4,B\n"


def test_parsers_accept_valid_files():
    expr = load_expression(io.StringIO(EXPR_CSV))
    ann = load_annotation(io.StringIO(ANN_CSV))
    assert expr.shape == (2, 4)
    assert ann["s3"] == "B"


def test_parsers_accept_tab_separated_bytes():
    expr = load_expression(EXPR_CSV.replace(",", "\t").encode())
    assert list(expr.columns) == ["s1", "s2", "s3", "s4"]


@pytest.mark.parametrize(
    "csv, message",
    [
        ("gene,s1,s2\nG1,1,x\n", "Non-numeric"),
        ("gene,s1,s2\nG1,1,\n", "missing value"),
        ("gene,s1,s2\nG1,1,2\nG1,3,4\n", "Duplicate gene"),
        ("gene\nG1\n", "at least one sample"),
    ],
)
def test_expression_validation(csv, message):
    with pytest.raises(AnalysisInputError, match=message):
        load_expression(io.StringIO(csv))


def test_sample_without_group_is_rejected():
    expr = load_expression(io.StringIO(EXPR_CSV))
    ann = load_annotation(io.StringIO("sample,group\ns1,A\ns2,A\ns3,B\n"))
    with pytest.raises(AnalysisInputError, match="without a group"):
        resolve_design(expr, ann)


def test_three_groups_rejected():
    expr = load_expression(io.StringIO(EXPR_CSV))
    ann = load_annotation(io.StringIO("sample,group\ns1,A\ns2,B\ns3,C\ns4,C\n"))
    with pytest.raises(AnalysisInputError, match="Exactly two groups"):
        resolve_design(expr, ann)


def test_group_with_single_sample_rejected():
    expr = load_expression(io.StringIO(EXPR_CSV))
    ann = load_annotation(io.StringIO("sample,group\ns1,A\ns2,B\ns3,B\ns4,B\n"))
    with pytest.raises(AnalysisInputError, match="at least 2"):
        resolve_design(expr, ann)


def test_negative_values_with_log_transform_rejected():
    expr = load_expression(io.StringIO("gene,s1,s2,s3,s4\nG1,-1,2,3,4\n"))
    ann = load_annotation(io.StringIO(ANN_CSV))
    with pytest.raises(AnalysisInputError, match="Negative values"):
        differential_expression(expr, ann)
    # works when the data are declared as already log-transformed
    result, _ = differential_expression(expr, ann, log_transform=False)
    assert len(result) == 1


def test_unknown_reference_group_rejected():
    expr = load_expression(io.StringIO(EXPR_CSV))
    ann = load_annotation(io.StringIO(ANN_CSV))
    with pytest.raises(AnalysisInputError, match="not found"):
        resolve_design(expr, ann, reference_group="Z")
