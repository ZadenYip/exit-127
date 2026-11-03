import logging

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from v1.auth.error.errors import SessionIdCollisionError


logger = logging.getLogger(__name__)


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(SessionIdCollisionError)
    async def handle_session_id_collision(
        request: Request, exc: SessionIdCollisionError
    ) -> JSONResponse:
        logger.error(
            "Could not create a unique login session ID after retries; path=%s",
            request.url.path,
            exc_info=(type(exc), exc, exc.__traceback__),
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "detail": {
                    "code": "SESSION_ID_COLLISION",
                    "message": "无法创建登录会话",
                }
            },
        )
