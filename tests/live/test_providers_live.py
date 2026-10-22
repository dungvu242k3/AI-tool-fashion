"""Real-network probes, default skipped. Missing/blocked source is a visible failure."""
import pytest

from src.collectors.performance_settings import SOURCES
from src.verification.live_probe import probe_provider

pytestmark = pytest.mark.live


@pytest.mark.parametrize("source", SOURCES)
def test_real_provider_returns_traced_records(source, request):
    result = probe_provider(source, request.config.getoption("--live-output"))
    assert result["status"] == "observed", (
        f"Real {source} probe failed; no fallback. codes={result['warning_codes']}; diagnostics={result['diagnostics']}"
    )
    assert result["record_count"] > 0 and result["network_attempts"] > 0
