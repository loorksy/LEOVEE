"""No function in the recommendation layer may name its own scope.

This is the single rule that stops the isolation bug class from being ported.
AiChart threads `userId` through six hundred lines of hand-written WHERE
clauses — one per query — and the isolation of the whole product rests on nobody
ever forgetting one. The signature *is* the bug: it makes a cross-tenant query
expressible, and once it is expressible it is one refactor away from happening.

Here scope comes from the Postgres session, so the database filters every
statement whether the caller remembered to or not. This test asserts the
absence, because that property holds only while nobody adds a convenient
`workspace_id=` parameter to make some report easier.
"""

from __future__ import annotations

import inspect
from pathlib import Path
from types import ModuleType

import pytest

pytestmark = pytest.mark.no_db

RECOMMENDATIONS = Path(__file__).resolve().parents[2] / "services" / "recommendations"

#: Parameter names that would let a caller choose which tenant's rows to read.
SCOPE_PARAMETERS = frozenset({"user_id", "workspace_id", "tenant_id", "owner_id", "account_id"})

#: `TenantContext` is fine and is the opposite thing: it is *proof of* a scope,
#: resolved from verified membership, not a filter the caller picks.
ALLOWED_CONTEXT_PARAMETER = "tenant"


def _modules() -> list[ModuleType]:
    import importlib

    return [
        importlib.import_module(f"app.services.recommendations.{path.stem}")
        for path in sorted(RECOMMENDATIONS.glob("*.py"))
        if path.stem != "__init__"
    ]


def test_the_package_exists_and_is_being_scanned() -> None:
    """A guard that silently scans nothing passes forever."""
    assert len(_modules()) >= 3


@pytest.mark.parametrize("module", _modules(), ids=lambda m: m.__name__.rsplit(".", 1)[-1])
def test_no_function_accepts_a_scope_parameter(module: ModuleType) -> None:
    offenders: list[str] = []
    for name, obj in vars(module).items():
        if name.startswith("_") or not callable(obj):
            continue
        if getattr(obj, "__module__", None) != module.__name__:
            continue
        try:
            signature = inspect.signature(obj)
        except (TypeError, ValueError):  # pragma: no cover — builtins
            continue
        for parameter in signature.parameters:
            if parameter in SCOPE_PARAMETERS:
                offenders.append(f"{module.__name__}.{name}({parameter}=…)")

    assert not offenders, (
        "these accept a scope as an argument, which makes a cross-tenant query "
        f"expressible: {offenders}. Take a TenantContext and let RLS filter."
    )


def test_the_repository_takes_a_tenant_context_instead() -> None:
    """The positive half: scope is proved, not chosen."""
    from app.services.recommendations import repository

    for name in ("list_open", "list_recent", "get", "list_by_status", "list_stale"):
        parameters = inspect.signature(getattr(repository, name)).parameters
        assert ALLOWED_CONTEXT_PARAMETER in parameters, f"{name} does not bind a tenant"


#: Models whose rows are the recommendation data itself. A hand-written tenant
#: predicate on one of these is the misleading pattern; the same syntax against
#: `WorkspaceMember` is how the worker discovers which workspaces exist at all,
#: which is a different question and has no RLS answer.
SCOPED_MODELS = ("Recommendation", "RecommendationRevision")


def test_no_recommendation_query_filters_on_a_tenant_column() -> None:
    """A hand-written tenant predicate on recommendation data is not wrong — it
    is *misleading*. It implies the filtering happens in Python, and a reader
    who believes that will helpfully add the parameter this package exists
    without.

    Deliberately narrow. The first version matched any `.workspace_id ==` and
    flagged the worker's `WorkspaceMember.workspace_id == workspace.id`, which
    resolves *who can speak for a workspace* rather than filtering anyone's
    rows. A guard that cannot tell those apart gets loosened the first time it
    cries wolf, and then it stops catching the real thing.
    """
    strays: list[str] = []
    for path in RECOMMENDATIONS.glob("*.py"):
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            stripped = line.strip()
            if stripped.startswith("#") or stripped.startswith("*"):
                continue
            for model in SCOPED_MODELS:
                if f"{model}.tenant_id ==" in line or f"{model}.workspace_id ==" in line:
                    strays.append(f"{path.name}:{number}: {stripped[:80]}")
    assert not strays, f"tenant predicates written by hand: {strays}"
