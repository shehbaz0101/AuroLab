from starlette.middleware.base import BaseHTTPMiddleware
from shared.logger import get_logger

logger = get_logger()

class LoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        logger.info(f"request: {request.method} {request.url}")
        response = await call_next(request)
        logger.info(f"response status: {response.status_code}")
        
        return response