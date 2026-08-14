"""What production refuses to boot with.

Each guard here was a production-readiness finding: a misconfiguration that
would otherwise ship silently — a global rate-limit bucket, an under-strength
signing key, an armed execution flag, a credentialed wildcard CORS. The point
of the test is that the refusal is in code, not only in a deploy script's
shell, so `uvicorn app.main` outside the wrappers fails the same way.
"""

from __future__ import annotations

import pytest

from app.core.config import Settings
from app.core.errors import ProviderConfigurationError
from app.core.startup import validate_production_startup

pytestmark = pytest.mark.no_db

#: A complete, valid production configuration. Each test breaks exactly one
#: field so the assertion names the single invariant under test.
#:
#: Note what is *absent*: no OANDA token, no LLM key. Those are platform-managed
#: secrets an admin enters after first boot, so a bootable production config must
#: not contain them — see test_platform_managed_secrets_do_not_gate_boot below.
_VALID = {
    "environment": "production",
    "secret_key": "x" * 40,
    "database_url": "postgresql+asyncpg://leovee_app:pw@db:5432/leovee",
    "redis_url": "redis://redis:6379/0",
    "trust_proxy_headers": True,
    "dev_auth_bypass": False,
    "oanda_execution": False,
    "cors_origins": "https://app.leovee.example",
}


def _settings(**overrides: object) -> Settings:
    return Settings(**{**_VALID, **overrides})  # type: ignore[arg-type]


def test_a_complete_production_config_boots() -> None:
    validate_production_startup(_settings())


def test_execution_is_refused_in_every_environment() -> None:
    # Not gated on environment: no environment is the right one to place an order.
    with pytest.raises(ProviderConfigurationError, match="OANDA_EXECUTION"):
        validate_production_startup(_settings(environment="development", oanda_execution=True))


@pytest.mark.parametrize(
    ("override", "needle"),
    [
        ({"trust_proxy_headers": False}, "TRUST_PROXY_HEADERS"),
        ({"dev_auth_bypass": True}, "DEV_AUTH_BYPASS"),
        ({"secret_key": "short"}, "SECRET_KEY"),
        ({"secret_key": "change-me-in-production"}, "SECRET_KEY"),
        ({"database_url": "postgresql+asyncpg://leovee:pw@db:5432/leovee"}, "leovee_app"),
        ({"redis_url": ""}, "REDIS_URL"),
        ({"cors_origins": "*"}, "CORS_ORIGINS"),
        ({"cors_origins": "http://localhost:5173"}, "CORS_ORIGINS"),
    ],
)
def test_each_invariant_refuses_boot(override: dict[str, object], needle: str) -> None:
    with pytest.raises(ProviderConfigurationError, match=needle):
        validate_production_startup(_settings(**override))


@pytest.mark.parametrize(
    "override",
    [
        {"oanda_api_token": ""},
        {"oanda_api_token": None},
        {"anthropic_api_key": None, "openai_api_key": None, "openrouter_api_key": None},
    ],
)
def test_platform_managed_secrets_do_not_gate_boot(override: dict[str, object]) -> None:
    # Regression guard for a deadlock that made production unstartable.
    #
    # These keys live in platform_secrets.MANAGED_SECRET_KEYS: an admin enters
    # them in the panel and they are applied from the encrypted DB row without a
    # redeploy. But this validator runs in the API lifespan *before*
    # load_runtime_overrides reads that table (app/main.py), so a DB value can
    # never satisfy the check — and the panel that would set it sits behind the
    # API that refuses to start. Requiring them here meant a fresh production
    # install could not boot on the first attempt or any attempt after it.
    #
    # A missing provider must degrade the feature (analysis returns NO_TRADE with
    # a named reason), not refuse traffic.
    validate_production_startup(_settings(**override))


def test_a_short_secret_key_is_rejected_by_length_not_only_by_default() -> None:
    # 31 bytes: not the placeholder, still under the HS256 floor.
    with pytest.raises(ProviderConfigurationError, match="SECRET_KEY"):
        validate_production_startup(_settings(secret_key="x" * 31))
    validate_production_startup(_settings(secret_key="x" * 32))


def test_non_production_skips_the_checks_but_not_execution() -> None:
    # A dev env with a weak key boots; a dev env with execution on does not.
    validate_production_startup(_settings(environment="development", secret_key="weak"))
    with pytest.raises(ProviderConfigurationError):
        validate_production_startup(_settings(environment="development", oanda_execution=True))
