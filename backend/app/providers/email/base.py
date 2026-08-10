from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class EmailMessage:
    to: str
    subject: str
    html_body: str
    text_body: str | None = None


class EmailProvider(Protocol):
    async def send(self, message: EmailMessage) -> None: ...
