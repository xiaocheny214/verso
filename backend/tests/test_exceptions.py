from verso_common.enums import BizCode, ModelErrorType
from verso_common.exceptions import BizException, ModelException


def test_biz_exception_aligns_with_fail_signature() -> None:
    exc = BizException("未登录", code=BizCode.UNAUTHORIZED)
    assert exc.message == "未登录"
    assert exc.code == 401
    assert exc.data is None


def test_model_exception_is_biz_exception() -> None:
    exc = ModelException(
        "模型超时",
        provider="zhihu",
        model="zhida",
        error_type=ModelErrorType.TIMEOUT,
    )
    assert isinstance(exc, BizException)
    assert exc.code == BizCode.MODEL_UNAVAILABLE
    assert exc.error_type.retryable is True
    assert ModelErrorType.AUTH.retryable is False
