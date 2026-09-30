import logging
import time

logger = logging.getLogger("apps.core")


class RequestLoggingMiddleware:
    """Lightweight request/response timing logger — cheap observability
    without pulling in a full APM stack for a portfolio project."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        start = time.monotonic()
        response = self.get_response(request)
        duration_ms = (time.monotonic() - start) * 1000
        logger.info(
            "%s %s -> %s (%.1fms)",
            request.method,
            request.path,
            response.status_code,
            duration_ms,
        )
        return response
