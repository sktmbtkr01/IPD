from pathlib import Path

import pytest

from benchmark.analysis.agreement import fleiss_kappa
from benchmark.foundation import build_foundation_manifest, verify_foundation_manifest
from benchmark.execution.run_store import RunStore


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_frozen_foundation_manifest_matches_code_and_configuration():
    manifest = build_foundation_manifest(PROJECT_ROOT)

    verify_foundation_manifest(PROJECT_ROOT)
    assert len(manifest["foundation_hash"]) == 64
    assert len(manifest["prompt_hashes"]) == 12
    assert manifest["prompt_bundle_hash"]


def test_run_store_rejects_path_traversal(tmp_path: Path):
    store = RunStore(tmp_path)

    with pytest.raises(ValueError, match="unsafe run-store identifier"):
        store.load_result("../outside", "REFERENCE", "run")


def test_fleiss_kappa_known_extremes_and_invalid_shape():
    assert fleiss_kappa([("BUY", "BUY", "BUY"), ("SELL", "SELL", "SELL")]) == 1.0
    assert fleiss_kappa([]) is None
    with pytest.raises(ValueError, match="equal rows"):
        fleiss_kappa([("BUY", "HOLD"), ("SELL",)])
