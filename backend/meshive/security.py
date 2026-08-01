from urllib.parse import urlsplit

from starlette.requests import Request

_STATE_CHANGING_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


def is_cross_site_api_request(request: Request) -> bool:
    if (
        request.method.upper() not in _STATE_CHANGING_METHODS
        or not request.url.path.startswith("/api/")
    ):
        return False

    origin = request.headers.get("origin")
    if origin is not None:
        if origin == "null":
            return True
        parsed = urlsplit(origin)
        request_host = request.headers.get("host", "")
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            return True
        return parsed.netloc.casefold() != request_host.casefold()

    return request.headers.get("sec-fetch-site", "").casefold() == "cross-site"
