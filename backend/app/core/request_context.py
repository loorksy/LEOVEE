from __future__ import annotations

import uuid
from contextvars import ContextVar

_request_id: ContextVar[str | None] = ContextVar("request_id", default=None)
_user_id: ContextVar[str | None] = ContextVar("user_id", default=None)
_workspace_id: ContextVar[str | None] = ContextVar("workspace_id", default=None)
_agent_run_id: ContextVar[str | None] = ContextVar("agent_run_id", default=None)


def get_request_id() -> str | None:
    return _request_id.get()


def logging_context() -> dict[str, str]:
    fields: dict[str, str] = {}
    if (rid := get_request_id()) is not None:
        fields["request_id"] = rid
    if (uid := _user_id.get()) is not None:
        fields["user_id"] = uid
    if (wid := _workspace_id.get()) is not None:
        fields["workspace_id"] = wid
    if (aid := _agent_run_id.get()) is not None:
        fields["agent_run_id"] = aid
    return fields


def bind_request_id(request_id: str) -> None:
    _request_id.set(request_id)


def bind_user_workspace(
    *,
    user_id: uuid.UUID | None = None,
    workspace_id: uuid.UUID | None = None,
) -> None:
    if user_id is not None:
        _user_id.set(str(user_id))
    if workspace_id is not None:
        _workspace_id.set(str(workspace_id))


def bind_agent_run_id(agent_run_id: uuid.UUID | str) -> None:
    _agent_run_id.set(str(agent_run_id))


def reset_context() -> None:
    _request_id.set(None)
    _user_id.set(None)
    _workspace_id.set(None)
    _agent_run_id.set(None)
