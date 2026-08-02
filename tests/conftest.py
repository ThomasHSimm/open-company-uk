import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from ukcompany.cache import CachedResponse

FIXTURES = Path(__file__).parent / "fixtures"

# Fixed observation date so age-based tests are deterministic.
OBSERVED_AT = datetime(2026, 8, 1, 12, 0, 0, tzinfo=UTC)


def load_profile(name: str) -> CachedResponse:
    data = json.loads((FIXTURES / name).read_text())
    return CachedResponse(
        company_number=data.get("company_number", "00000000"),
        endpoint="profile",
        status_code=200,
        fetched_at=OBSERVED_AT,
        url="fixture://" + name,
        data=data,
    )


def load_insolvency(name: str, company_number: str) -> CachedResponse:
    data = json.loads((FIXTURES / name).read_text())
    return CachedResponse(
        company_number=company_number,
        endpoint="insolvency",
        status_code=200,
        fetched_at=OBSERVED_AT,
        url="fixture://" + name,
        data=data,
    )


@pytest.fixture
def profile_clean() -> CachedResponse:
    return load_profile("profile_active_clean.json")


@pytest.fixture
def profile_liquidation() -> CachedResponse:
    return load_profile("profile_liquidation.json")


@pytest.fixture
def profile_strikeoff() -> CachedResponse:
    return load_profile("profile_strikeoff.json")


@pytest.fixture
def profile_dissolved() -> CachedResponse:
    return load_profile("profile_dissolved.json")


@pytest.fixture
def profile_minimal() -> CachedResponse:
    return load_profile("profile_minimal_old.json")


@pytest.fixture
def insolvency_case() -> CachedResponse:
    return load_insolvency("insolvency_07654321.json", "07654321")
