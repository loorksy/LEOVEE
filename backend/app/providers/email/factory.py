from functools import lru_cache

from app.core.config import get_settings
from app.providers.email.base import EmailProvider
from app.providers.email.console import ConsoleEmailProvider
from app.providers.email.resend import ResendEmailProvider


@lru_cache
def get_email_provider() -> EmailProvider:
    settings = get_settings()
    if settings.resend_api_key:
        return ResendEmailProvider(settings.resend_api_key, settings.email_from)
    return ConsoleEmailProvider()
