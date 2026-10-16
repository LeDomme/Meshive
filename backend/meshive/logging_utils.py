import logging
import re

_CATALOGUE_SHARE_PATH = re.compile(r"(/api/share/catalogue/)[^/?\s]+(?=(?:/|\?|\s|$))")


class CatalogueShareAccessLogRedactionFilter(logging.Filter):
    """Redact capability tokens before Uvicorn formats access-log records."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.args, tuple) and len(record.args) >= 3:
            args = list(record.args)
            if isinstance(args[2], str):
                args[2] = _CATALOGUE_SHARE_PATH.sub(r"\1<redacted>", args[2])
                record.args = tuple(args)
        return True


def install_catalogue_share_access_log_redaction() -> None:
    logger = logging.getLogger("uvicorn.access")
    if not any(isinstance(item, CatalogueShareAccessLogRedactionFilter) for item in logger.filters):
        logger.addFilter(CatalogueShareAccessLogRedactionFilter())
