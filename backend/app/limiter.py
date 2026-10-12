"""Per-IP rate limits. The proxy header is trusted only when TRUST_PROXY is set."""

from slowapi import Limiter
from slowapi.util import get_remote_address
from starlette.requests import Request

from app.config import get_settings


def client_ip(request: Request) -> str:
    settings = get_settings()
    if settings.trust_proxy:
        forwarded = request.headers.get("x-forwarded-for", "")
        hop = forwarded.split(",")[0].strip()
        if hop:
            return hop[:64]
    return get_remote_address(request)


# Header injection requires a Starlette Response argument on every route.
# Keep the limit, and leave the response body untouched.
limiter = Limiter(key_func=client_ip, headers_enabled=False)
