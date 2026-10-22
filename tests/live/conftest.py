"""Explicit live selection only. Ordinary unit tests keep their outbound HTTP block."""
import pytest

from src.collectors.performance_settings import SOURCES


def pytest_addoption(parser):
    parser.addoption("--live-provider", action="append", default=[], choices=list(SOURCES),
                     help="Opt in to one real provider; repeat to select more (never implied by marker).")
    parser.addoption("--live-output", default="reports/verification_phase12/live",
                     help="Directory for real probe diagnostics; never latest_data.json.")


@pytest.fixture(autouse=True)
def block_accidental_external_http(request):
    """Override the root block ONLY in this directory and after explicit opt-in."""
    selected = request.config.getoption("--live-provider")
    source = request.node.callspec.params.get("source") if hasattr(request.node, "callspec") else None
    if source not in selected:
        pytest.skip("Real provider not selected via --live-provider; no cached/mock substitution")
