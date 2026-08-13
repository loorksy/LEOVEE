"""The out-of-scope list, enforced by the build rather than by memory.

Owner decisions D3, D4, D5 and D7 (docs/AICHART_MIGRATION_PLAN.md §2) put whole
subsystems permanently out of scope: broker connectivity, trade execution,
external notifications, and backtesting. The migration ports ~200k lines from a
codebase where all four exist and are deeply wired in, over many phases, by
people reading that codebase all day.

A written rule does not survive that. A failing test does.

The forbidden term list is deliberately blunt: if a term genuinely needs to
appear (a docstring explaining why a thing is absent, a status enum inherited
from OANDA), add it to ALLOWED_OCCURRENCES with a reason. Widening the rule is
a decision someone makes on purpose, in a diff, with a justification.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.no_db

# .../backend/app/tests/conformance/<this file>
BACKEND_ROOT = Path(__file__).resolve().parents[3]
REPO_ROOT = BACKEND_ROOT.parent
FRONTEND_SRC = REPO_ROOT / "frontend" / "src"

# term -> which owner decision forbids it
FORBIDDEN_TERMS: dict[str, str] = {
    "metaapi": "D3 — MetaAPI is out of scope",
    "metatrader": "D3 — MT5 is out of scope",
    "mt5": "D3 — MT5 is out of scope",
    "broker_login": "D3 — broker account linking is out of scope",
    "place_order": "D4 — trade execution is out of scope",
    "send_order": "D4 — trade execution is out of scope",
    "submit_order": "D4 — trade execution is out of scope",
    "close_position": "D4 — trade execution is out of scope",
    "modify_sl_tp": "D4 — trade execution is out of scope",
    # Telegram is a conversation transport (ADR 0009), so the term itself is no
    # longer forbidden — the *proactive send* is, and that is enforced by
    # `test_no_outbound_telegram_send` below rather than by a substring.
    "webpush": "D5 — external notifications are out of scope",
    "pywebpush": "D5 — external notifications are out of scope",
    "web-push": "D5 — external notifications are out of scope",
    "backtest": "D7 — backtesting and statistical validation are out of scope",
    "walk_forward": "D7 — statistical validation is out of scope",
    "monte_carlo": "D7 — statistical validation is out of scope",
}

# Paths that may mention a forbidden term, with the reason. Keep these few.
ALLOWED_OCCURRENCES: dict[str, str] = {
    # This file names the terms in order to forbid them.
    "backend/app/tests/conformance/test_no_execution_surface.py": "the guard itself",
    # The gate that proves execution stays impossible has to name it.
    "backend/app/tests/test_trade_execution_gate.py": "asserts execution is refused",
}

#: Where Telegram may be mentioned at all. A transport, nothing more (ADR 0009).
TELEGRAM_ALLOWED_PREFIXES = (
    "backend/app/services/telegram/",
    "backend/app/api/routes/telegram.py",
    "backend/app/models/telegram.py",
    "backend/app/schemas/telegram.py",
    "backend/app/tests/",
    "backend/alembic/versions/",
    "frontend/src/features/telegram/",
    "frontend/src/api/telegram.ts",
    # The settings page mounts the panel; mounting is not sending.
    "frontend/src/features/settings/",
    "frontend/src/i18n/",
    # Registration points. Each mentions the transport in order to wire it up,
    # and none of them can send anything.
    "backend/app/main.py",
    "backend/app/core/config.py",
    "backend/app/models/__init__.py",
    "backend/app/services/platform_secrets.py",
)

#: Verbs that name an outbound action. Matched at a word boundary rather than as
#: a substring: `resolve_sender` contains "send" and sends nothing, and a guard
#: that cannot tell the difference gets weakened by the first false positive it
#: produces.
OUTBOUND_VERBS = ("send", "notify", "broadcast", "push", "announce", "alert")

#: The single function permitted to send to Telegram, and it can only reply.
TELEGRAM_REPLY_FUNCTION = "reply_to"

SCANNED_SUFFIXES = {".py", ".ts", ".tsx", ".js", ".jsx"}
SKIPPED_DIRECTORIES = {
    "node_modules",
    "__pycache__",
    ".git",
    ".venv",
    "dist",
    "build",
    "vendor",
    ".mypy_cache",
    ".pytest_cache",
}


def _scanned_files() -> list[Path]:
    roots = [BACKEND_ROOT / "app", FRONTEND_SRC]
    files: list[Path] = []
    for root in roots:
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if path.suffix not in SCANNED_SUFFIXES or not path.is_file():
                continue
            if SKIPPED_DIRECTORIES & set(path.parts):
                continue
            files.append(path)
    return sorted(files)


def _relative(path: Path) -> str:
    return path.relative_to(REPO_ROOT).as_posix()


@pytest.mark.parametrize("term", sorted(FORBIDDEN_TERMS), ids=lambda term: str(term))
def test_out_of_scope_subsystem_is_absent(term: str) -> None:
    pattern = re.compile(re.escape(term), re.IGNORECASE)
    hits: list[str] = []

    for path in _scanned_files():
        relative = _relative(path)
        if relative in ALLOWED_OCCURRENCES:
            continue
        try:
            content = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for number, line in enumerate(content.splitlines(), start=1):
            if pattern.search(line):
                hits.append(f"{relative}:{number}: {line.strip()[:110]}")

    assert not hits, (
        f"'{term}' is out of scope ({FORBIDDEN_TERMS[term]}) but appears in "
        f"{len(hits)} place(s):\n  " + "\n  ".join(hits[:20])
    )


def test_allowlist_has_no_stale_entries() -> None:
    """An allowlist entry for a file that no longer exists hides a real gap later."""
    stale = [relative for relative in ALLOWED_OCCURRENCES if not (REPO_ROOT / relative).exists()]
    assert not stale, f"ALLOWED_OCCURRENCES names files that do not exist: {stale}"


def test_no_broker_execution_dependency_is_installed() -> None:
    """Catch the subsystem arriving as a dependency before any code imports it."""
    forbidden_packages = ("metaapi", "MetaTrader5", "pywebpush", "python-telegram-bot")
    pyproject = (BACKEND_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    found = [name for name in forbidden_packages if name.lower() in pyproject.lower()]
    assert not found, f"out-of-scope packages declared in backend/pyproject.toml: {found}"

    package_json = REPO_ROOT / "frontend" / "package.json"
    if package_json.exists():
        content = package_json.read_text(encoding="utf-8").lower()
        found_js = [
            name
            for name in ("metaapi.cloud-sdk", "web-push", "node-telegram-bot-api")
            if name in content
        ]
        assert not found_js, f"out-of-scope packages in frontend/package.json: {found_js}"


# --- Telegram: a transport, and only a transport (ADR 0009) ------------------


def _telegram_files() -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for path in _scanned_files():
        relative = _relative(path)
        try:
            content = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        if "telegram" in content.lower():
            out.append((relative, content))
    return out


def test_telegram_stays_inside_the_transport() -> None:
    """The term is allowed now, but not everywhere.

    D5's reason for excluding Telegram was that a *proactive* channel creates an
    operational commitment — a send time, a retry policy, a queue, a question
    about what happens when delivery fails. A reply carries none of that. So the
    transport is confined to its own modules, and a mention anywhere else means
    the notification channel is growing back somewhere it will not be noticed.
    """
    strays = [
        relative
        for relative, _ in _telegram_files()
        if not relative.startswith(TELEGRAM_ALLOWED_PREFIXES)
    ]
    assert not strays, (
        "Telegram is a conversation transport (ADR 0009) and belongs in "
        f"{TELEGRAM_ALLOWED_PREFIXES}; found mentions in: {strays}"
    )


def test_the_only_way_to_send_to_telegram_is_to_reply() -> None:
    """The shape forbids notification, not a comment saying not to.

    Every outbound call goes through one function that takes its chat id from
    the inbound message it is answering. There is no way to *start* a
    conversation, so a proactive notification cannot be written by accident — it
    would have to be a new function, and this test is what notices.
    """
    senders: list[str] = []
    for relative, content in _telegram_files():
        if not relative.startswith("backend/app/services/telegram/"):
            continue
        for number, line in enumerate(content.splitlines(), start=1):
            stripped = line.strip()
            if not stripped.startswith(("def ", "async def ")):
                continue
            name = stripped.split("(")[0].removeprefix("async def ").removeprefix("def ").strip()
            # A private helper cannot be reached from outside the module, so it
            # cannot become an entry point for an unsolicited send.
            if name.startswith("_") or name == TELEGRAM_REPLY_FUNCTION:
                continue
            words = name.lower().split("_")
            if any(verb in words for verb in OUTBOUND_VERBS):
                senders.append(f"{relative}:{number}: {name}")
    assert not senders, (
        "these look like outbound senders that do not require an inbound message "
        f"(D5 stands: nothing is ever sent unprompted): {senders}"
    )
