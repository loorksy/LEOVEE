"""Telegram as a conversation transport (ADR 0009).

The security properties are the substance here, not the plumbing: the webhook is
the only unauthenticated route in the application, and its sender id is what
resolves to a workspace.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tenant import TenantContext, resolve_tenant_context
from app.core.tenant_rls import bind_workspace_rls
from app.models.telegram import TelegramLink, TelegramLinkCode
from app.services.telegram.identity import (
    LINK_CODE_ALPHABET,
    LINK_CODE_LENGTH,
    consume_link_code,
    hash_code,
    issue_link_code,
    resolve_sender,
    revoke_link,
)
from app.services.telegram.transport import MAX_MESSAGE_CHARS, _chunks
from app.services.telegram.webhook import MESSAGES, handle_update
from app.tests.conftest import seed_user_org


class _Recorder:
    """Captures what would have been sent, so nothing leaves the test."""

    def __init__(self) -> None:
        self.sent: list[tuple[int, str]] = []

    async def _post(self, chat_id: int, text_: str) -> None:
        self.sent.append((chat_id, text_))


def _update(sender: int, body: str, chat: int | None = None) -> dict[str, Any]:
    return {
        "message": {
            "message_id": 1,
            "from": {"id": sender, "username": "tester"},
            "chat": {"id": chat if chat is not None else sender},
            "text": body,
        }
    }


async def _tenant(session: AsyncSession, *, email: str, slug: str) -> TenantContext:
    user, _org, _member = await seed_user_org(session, email=email, slug=slug)
    ctx = await resolve_tenant_context(session, user.id)
    await bind_workspace_rls(session, ctx)
    return ctx


# --- the link code -----------------------------------------------------------


@pytest.mark.asyncio
async def test_a_code_is_stored_hashed_and_never_in_the_clear(db_session: AsyncSession) -> None:
    """For the minutes it lives it is a bearer credential for a workspace; a
    database read should not be enough to claim someone's account."""
    tenant = await _tenant(db_session, email="tg1@example.com", slug="tg1")
    issued = await issue_link_code(db_session, tenant)

    assert len(issued.code) == LINK_CODE_LENGTH
    assert set(issued.code) <= set(LINK_CODE_ALPHABET)

    row = await db_session.scalar(
        select(TelegramLinkCode).where(TelegramLinkCode.workspace_id == tenant.workspace_id)
    )
    assert row is not None
    assert row.code_hash != issued.code
    assert row.code_hash == hash_code(issued.code)


@pytest.mark.asyncio
async def test_the_alphabet_excludes_characters_that_look_alike(db_session: AsyncSession) -> None:
    """The code is read off one screen and typed into another. A pair that
    cannot be told apart turns a security control into a support ticket."""
    for confusable in "01OIL":
        assert confusable not in LINK_CODE_ALPHABET


@pytest.mark.asyncio
async def test_a_code_links_the_account_and_cannot_be_used_twice(
    db_session: AsyncSession,
) -> None:
    tenant = await _tenant(db_session, email="tg2@example.com", slug="tg2")
    issued = await issue_link_code(db_session, tenant)
    await db_session.commit()

    first = await consume_link_code(
        db_session, code=issued.code, telegram_user_id=555, telegram_chat_id=555
    )
    assert first is not None
    assert first.workspace_id == tenant.workspace_id

    second = await consume_link_code(
        db_session, code=issued.code, telegram_user_id=666, telegram_chat_id=666
    )
    assert second is None


@pytest.mark.asyncio
async def test_a_code_is_normalised_before_matching(db_session: AsyncSession) -> None:
    """The user retypes it. A code that fails on a trailing space is
    indistinguishable from a wrong code to the person holding it."""
    tenant = await _tenant(db_session, email="tg3@example.com", slug="tg3")
    issued = await issue_link_code(db_session, tenant)
    await db_session.commit()

    linked = await consume_link_code(
        db_session,
        code=f"  {issued.code.lower()}  ",
        telegram_user_id=777,
        telegram_chat_id=777,
    )
    assert linked is not None


@pytest.mark.asyncio
async def test_an_expired_code_is_refused(db_session: AsyncSession) -> None:
    tenant = await _tenant(db_session, email="tg4@example.com", slug="tg4")
    issued = await issue_link_code(db_session, tenant)
    await db_session.execute(
        text("UPDATE telegram_link_codes SET expires_at = :past"),
        {"past": datetime.now(UTC) - timedelta(minutes=1)},
    )
    await db_session.commit()

    assert (
        await consume_link_code(
            db_session, code=issued.code, telegram_user_id=888, telegram_chat_id=888
        )
    ) is None


# --- resolution --------------------------------------------------------------


@pytest.mark.asyncio
async def test_an_unknown_sender_resolves_to_nothing(db_session: AsyncSession) -> None:
    assert await resolve_sender(db_session, 999_999) is None


@pytest.mark.asyncio
async def test_resolution_survives_an_unbound_session(db_session: AsyncSession) -> None:
    """The crux of the design.

    A webhook arrives with a Telegram id and nothing else — the workspace is the
    *answer*, so the lookup cannot already be scoped to one. Binding RLS from
    the message would let untrusted text name the workspace it wants.
    """
    tenant = await _tenant(db_session, email="tg5@example.com", slug="tg5")
    issued = await issue_link_code(db_session, tenant)
    await db_session.commit()
    await consume_link_code(
        db_session, code=issued.code, telegram_user_id=1234, telegram_chat_id=1234
    )
    await db_session.commit()

    # Deliberately clear the tenant GUCs: this is the webhook's real state.
    await db_session.execute(text("SELECT set_config('app.workspace_id', '', false)"))
    await db_session.execute(text("SELECT set_config('app.tenant_id', '', false)"))

    resolved = await resolve_sender(db_session, 1234)
    assert resolved is not None
    assert resolved.workspace_id == tenant.workspace_id


@pytest.mark.asyncio
async def test_a_revoked_link_stops_resolving_but_the_row_survives(
    db_session: AsyncSession,
) -> None:
    """When the link was cut matters more than its absence would."""
    tenant = await _tenant(db_session, email="tg6@example.com", slug="tg6")
    issued = await issue_link_code(db_session, tenant)
    await db_session.commit()
    await consume_link_code(
        db_session, code=issued.code, telegram_user_id=4321, telegram_chat_id=4321
    )
    await db_session.commit()

    assert await revoke_link(db_session, tenant, telegram_user_id=4321) is True
    await db_session.commit()

    assert await resolve_sender(db_session, 4321) is None
    await bind_workspace_rls(db_session, tenant)
    row = await db_session.scalar(select(TelegramLink).where(TelegramLink.telegram_user_id == 4321))
    assert row is not None
    assert row.revoked_at is not None


# --- the webhook -------------------------------------------------------------


@pytest.mark.asyncio
async def test_an_unlinked_sender_learns_nothing(db_session: AsyncSession) -> None:
    """Unlinked, wrong code and expired code get the same sentence.

    Distinguishing them would let anyone holding the bot's handle probe for
    linked accounts or valid codes.
    """
    recorder = _Recorder()
    unlinked = await handle_update(db_session, _update(11, "مرحبا"), transport=recorder)  # type: ignore[arg-type]
    wrong_code = await handle_update(db_session, _update(12, "ABCD2345"), transport=recorder)  # type: ignore[arg-type]

    assert unlinked.action == "unlinked"
    assert wrong_code.action == "unlinked"
    assert recorder.sent[0][1] == recorder.sent[1][1] == MESSAGES["unlinked"]


@pytest.mark.asyncio
async def test_a_valid_code_sent_to_the_agent_links_the_account(
    db_session: AsyncSession,
) -> None:
    tenant = await _tenant(db_session, email="tg7@example.com", slug="tg7")
    issued = await issue_link_code(db_session, tenant)
    await db_session.commit()

    recorder = _Recorder()
    outcome = await handle_update(
        db_session,
        _update(2468, f"/start {issued.code}"),
        transport=recorder,  # type: ignore[arg-type]
    )
    assert outcome.action == "linked"
    assert outcome.workspace_id == tenant.workspace_id
    assert recorder.sent[-1][1] == MESSAGES["linked"]
    # And the promise is made at the moment of linking, not buried in a policy.
    assert "لن أرسل لك شيئاً ما لم تسأل" in MESSAGES["linked"]


@pytest.mark.asyncio
async def test_a_non_text_message_is_answered_without_reaching_the_agent(
    db_session: AsyncSession,
) -> None:
    recorder = _Recorder()
    update: dict[str, Any] = {
        "message": {"from": {"id": 31}, "chat": {"id": 31}, "photo": [{"file_id": "x"}]}
    }
    outcome = await handle_update(db_session, update, transport=recorder)  # type: ignore[arg-type]
    assert outcome.action == "non_text"


@pytest.mark.asyncio
async def test_an_update_with_no_sender_is_ignored_silently(db_session: AsyncSession) -> None:
    """A channel post or a join is not a conversation, and answering one would
    be the system speaking to someone who never asked."""
    recorder = _Recorder()
    outcome = await handle_update(db_session, {"channel_post": {}}, transport=recorder)  # type: ignore[arg-type]
    assert outcome.handled is False
    assert recorder.sent == []


@pytest.mark.asyncio
async def test_membership_removal_cuts_telegram_access_on_the_next_message(
    db_session: AsyncSession,
) -> None:
    """The link stores a user id and the context is rebuilt from the database
    every message, so a removed user loses access with nothing to revoke."""
    tenant = await _tenant(db_session, email="tg8@example.com", slug="tg8")
    issued = await issue_link_code(db_session, tenant)
    await db_session.commit()
    await handle_update(db_session, _update(1357, issued.code), transport=_Recorder())  # type: ignore[arg-type]
    await db_session.commit()

    await db_session.execute(
        text("DELETE FROM organization_members WHERE user_id = :u"), {"u": tenant.user_id}
    )
    await db_session.commit()

    recorder = _Recorder()
    outcome = await handle_update(db_session, _update(1357, "حلل الذهب"), transport=recorder)  # type: ignore[arg-type]
    assert outcome.action == "membership_revoked"
    assert recorder.sent[-1][1] == MESSAGES["unlinked"]


# --- the transport itself ----------------------------------------------------


def test_a_long_reply_is_split_not_truncated() -> None:
    """An analysis cut at 4096 characters loses its invalidation level, which is
    the part the reader most needs."""
    text_ = "\n".join(f"سطر رقم {i} من التحليل" for i in range(600))
    parts = _chunks(text_)
    assert len(parts) > 1
    assert all(len(part) <= MAX_MESSAGE_CHARS for part in parts)
    # Nothing is lost, only redistributed.
    assert "".join(parts).replace("\n", "") == text_.replace("\n", "")


def test_a_short_reply_is_one_message() -> None:
    assert _chunks("قصير") == ["قصير"]


def test_there_is_exactly_one_outbound_function() -> None:
    """The shape is the guarantee: without an inbound update there is no chat id
    to send to, so an unsolicited message cannot be expressed."""
    import inspect

    from app.services.telegram import transport as module

    public = [
        name
        for name, obj in vars(module).items()
        if not name.startswith("_") and inspect.iscoroutinefunction(obj)
    ]
    assert public == ["reply_to"]
    assert "update" in inspect.signature(module.reply_to).parameters
