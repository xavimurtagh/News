"""Tests for tier computation and result partitioning."""

from __future__ import annotations

from news_lens.models import ConsensusTier, CoverageStatus, OutletCoverage
from news_lens.pipeline import _compute_tier, _partition_results


def cov(status: CoverageStatus) -> OutletCoverage:
    return OutletCoverage(outlet_domain="x.com", article_id="a", status=status)


def test_universal_when_every_outlet_asserts():
    coverage = [cov(CoverageStatus.ASSERTED) for _ in range(3)]
    assert _compute_tier(coverage, 3) is ConsensusTier.UNIVERSAL


def test_disputed_takes_precedence_over_universal():
    coverage = [
        cov(CoverageStatus.ASSERTED),
        cov(CoverageStatus.ASSERTED),
        cov(CoverageStatus.CONTRADICTED),
    ]
    assert _compute_tier(coverage, 3) is ConsensusTier.DISPUTED


def test_attributed_only_when_no_outlet_asserts():
    coverage = [
        cov(CoverageStatus.ATTRIBUTED),
        cov(CoverageStatus.ATTRIBUTED),
        cov(CoverageStatus.OMITTED),
    ]
    assert _compute_tier(coverage, 3) is ConsensusTier.ATTRIBUTED_ONLY


def test_single_sourced_when_one_covers_rest_omit():
    coverage = [
        cov(CoverageStatus.ASSERTED),
        cov(CoverageStatus.OMITTED),
        cov(CoverageStatus.OMITTED),
    ]
    assert _compute_tier(coverage, 3) is ConsensusTier.SINGLE_SOURCED


def test_single_sourced_for_one_attribution_rest_omit():
    coverage = [
        cov(CoverageStatus.ATTRIBUTED),
        cov(CoverageStatus.OMITTED),
        cov(CoverageStatus.OMITTED),
    ]
    assert _compute_tier(coverage, 3) is ConsensusTier.SINGLE_SOURCED


def test_majority_when_some_omit():
    coverage = [
        cov(CoverageStatus.ASSERTED),
        cov(CoverageStatus.ASSERTED),
        cov(CoverageStatus.OMITTED),
    ]
    assert _compute_tier(coverage, 3) is ConsensusTier.MAJORITY


def test_disputed_overrides_attributed_only():
    coverage = [
        cov(CoverageStatus.ATTRIBUTED),
        cov(CoverageStatus.CONTRADICTED),
    ]
    assert _compute_tier(coverage, 2) is ConsensusTier.DISPUTED


def test_partition_results_filters_exceptions():
    items = ["a", "b", "c", "d"]
    results = ["A", ValueError("boom"), "C", KeyError("nope")]
    keep_items, keep_results = _partition_results(items, results)
    assert keep_items == ["a", "c"]
    assert keep_results == ["A", "C"]


def test_partition_results_all_success():
    keep_items, keep_results = _partition_results(["x"], ["X"])
    assert keep_items == ["x"]
    assert keep_results == ["X"]


def test_partition_results_all_failed():
    keep_items, keep_results = _partition_results(
        ["x", "y"], [ValueError("a"), KeyError("b")]
    )
    assert keep_items == []
    assert keep_results == []


def test_partition_results_preserves_alignment():
    """Surviving items and results stay paired by index."""
    items = [10, 20, 30]
    results = [{"v": 1}, ValueError("skip"), {"v": 3}]
    keep_items, keep_results = _partition_results(items, results)
    assert list(zip(keep_items, keep_results)) == [(10, {"v": 1}), (30, {"v": 3})]
