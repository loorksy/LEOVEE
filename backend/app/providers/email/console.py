import structlog

from app.providers.email.base import EmailMessage

logger = structlog.get_logger(__name__)

# Captured messages in test/development for assertions.
_outbox: list[EmailMessage] = []


def get_console_outbox() -> list[EmailMessage]:
    return _outbox


def clear_console_outbox() -> None:
    _outbox.clear()


class ConsoleEmailProvider:
    async def send(self, message: EmailMessage) -> None:
        _outbox.append(message)
        logger.info(
            "email_sent_console",
            to=message.to,
            subject=message.subject,
        )
