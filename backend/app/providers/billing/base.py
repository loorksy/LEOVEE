from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class BillingProvider(ABC):
    @abstractmethod
    async def create_checkout_session(
        self,
        *,
        tenant_id: str,
        plan_code: str,
        success_url: str,
        cancel_url: str,
    ) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    async def handle_webhook(
        self,
        session: Any,
        payload: bytes,
        signature: str | None,
    ) -> dict[str, Any]:
        raise NotImplementedError
