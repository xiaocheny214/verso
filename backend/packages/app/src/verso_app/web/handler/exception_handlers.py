"""全局异常处理器：把异常统一转成 ``Response`` 返回前端。

挂载入口 :func:`register_exception_handlers`，在 ``create_app`` 中调用。

约定：所有异常均返回 **HTTP 200**，业务码放 body；
未预期异常用 ``logger.error(..., exc_info=exc)`` 记录完整堆栈。
"""

import logging

from fastapi import FastAPI, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from verso_common.enums.biz_code import BizCode
from verso_common.exceptions import BizException
from verso_common.result import Response

logger = logging.getLogger("verso.handler")

_VALUE_ERROR_PREFIX = "Value error, "


def _jsonify(resp: Response) -> JSONResponse:
    return JSONResponse(status_code=200, content=resp.model_dump(mode="json"))


def handle_biz_exception(_request: Request, exc: BizException) -> JSONResponse:
    return _jsonify(Response.fail(exc.message, code=exc.code, data=exc.data))


def _first_validation_message(errors: object) -> str:
    if isinstance(errors, list):
        for item in errors:
            msg = item.get("msg") if isinstance(item, dict) else None
            if isinstance(msg, str) and msg:
                return msg.removeprefix(_VALUE_ERROR_PREFIX)
    return "请求参数校验失败"


def handle_request_validation_error(_request: Request, exc: RequestValidationError) -> JSONResponse:
    detail = jsonable_encoder(exc.errors())
    return _jsonify(
        Response.fail(
            _first_validation_message(detail),
            code=BizCode.BAD_REQUEST,
            data=detail,
        )
    )


def handle_http_exception(_request: Request, exc: HTTPException) -> JSONResponse:
    return _jsonify(Response.fail(str(exc.detail), code=exc.status_code))


def handle_unhandled_exception(request: Request, exc: Exception) -> JSONResponse:
    logger.error(
        "未预期异常 %s %s",
        request.method,
        request.url.path,
        exc_info=exc,
    )
    return _jsonify(Response.fail("服务器内部错误", code=BizCode.INTERNAL_ERROR))


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(BizException, handle_biz_exception)
    app.add_exception_handler(RequestValidationError, handle_request_validation_error)
    app.add_exception_handler(HTTPException, handle_http_exception)
    app.add_exception_handler(Exception, handle_unhandled_exception)
