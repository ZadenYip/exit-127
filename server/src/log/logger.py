import contextvars
import logging
import time
import uuid

from fastapi import FastAPI, Request, Response
from starlette.middleware.base import RequestResponseEndpoint


TRACE_ID_HEADER = "X-Trace-ID"
trace_id_context: contextvars.ContextVar[str] = contextvars.ContextVar(
    "trace_id",
    default="-",
)


_original_record_factory = logging.getLogRecordFactory()


def _record_factory(*args, **kwargs):
    record = _original_record_factory(*args, **kwargs)
    record.traceid = trace_id_context.get()
    return record


logging.setLogRecordFactory(_record_factory)

access_logger = logging.getLogger("http.access")

def _get_or_create_trace_id(request: Request) -> str:
    """优先沿用上游 traceid，否则为当前请求生成一个新的 traceid。"""
    incoming_trace_id = request.headers.get(TRACE_ID_HEADER)
    if incoming_trace_id:
        return incoming_trace_id
    return uuid.uuid4().hex


def register_logger(app: FastAPI) -> None:
    logging.basicConfig(
        level=logging.INFO,
        format=(
            "%(asctime)s %(levelname)s %(name)s "
            "[traceid=%(traceid)s] %(message)s"
        ),
    )

    @app.middleware("http")
    async def log_requests(
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        trace_id = _get_or_create_trace_id(request)
        token = trace_id_context.set(trace_id)
        request.state.trace_id = trace_id
        start_time = time.perf_counter()

        try:
            access_logger.info(
                "Incoming Request: %s %s",
                request.method,
                request.url.path,
            )
            response = await call_next(request)
            process_time_ms = (time.perf_counter() - start_time) * 1000
            response.headers[TRACE_ID_HEADER] = trace_id
            access_logger.info(
                "Request Completed: %s %s - Status Code: %d - Process Time: %.2f ms",
                request.method,
                request.url.path,
                response.status_code,
                process_time_ms,
            )
            return response
        except Exception:
            process_time_ms = (time.perf_counter() - start_time) * 1000
            access_logger.exception(
                "Request Failed: %s %s - Process Time: %.2f ms",
                request.method,
                request.url.path,
                process_time_ms,
            )
            raise
        finally:
            trace_id_context.reset(token)
