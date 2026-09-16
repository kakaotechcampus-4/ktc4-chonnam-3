import logging
import re
from urllib.parse import urlsplit


class AuthRedactionFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if record.name == "uvicorn.access" and isinstance(record.args, tuple):
            if len(record.args) == 5 and isinstance(record.args[2], str):
                # Keep Uvicorn's positional args intact for its access-log formatter.
                target = urlsplit(record.args[2])
                if target.query:
                    record.args = (
                        *record.args[:2],
                        target._replace(query="[REDACTED]").geturl(),
                        *record.args[3:],
                    )
            record.msg = self.redact(str(record.msg))
            record.args = tuple(
                self.redact(arg) if isinstance(arg, str) else arg for arg in record.args
            )
        else:
            record.msg, record.args = self.redact(record.getMessage()), ()
        return True

    @staticmethod
    def redact(message: str) -> str:
        message = re.sub(
            r"([?&](?:code|state|access_token|refresh_token|client_secret)=)[^&\s\"']*",
            r"\1[REDACTED]",
            message,
            flags=re.IGNORECASE,
        )
        message = re.sub(
            r"((?:accessToken|refreshToken|oauthState)=)[^;\s]+",
            r"\1[REDACTED]",
            message,
            flags=re.IGNORECASE,
        )
        message = re.sub(r"(Bearer\s+)[^\s\"']+", r"\1[REDACTED]", message, flags=re.IGNORECASE)
        return message


def configure_auth_logging() -> None:
    for name in ("uvicorn.access", "httpx", "httpcore"):
        logger = logging.getLogger(name)
        if not any(isinstance(item, AuthRedactionFilter) for item in logger.filters):
            logger.addFilter(AuthRedactionFilter())
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
