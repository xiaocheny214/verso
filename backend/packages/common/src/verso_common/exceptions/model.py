"""大模型调用异常。

供 quality 裁决等路径在调用模型失败时 raise。继承 :class:`BizException`，
会被 web 全局处理器按 MRO 捕获，转成 ``Response.fail``。

额度紧或模型失败时，质量路径应记 ``unclear``、不扣分；不要轮询打穿日额度。
"""

from verso_common.enums.biz_code import BizCode
from verso_common.enums.model import ModelErrorType
from verso_common.exceptions.biz import BizException


class ModelException(BizException):
    """大模型调用异常。

    ``provider`` / ``model`` / ``error_type`` 供内部日志与重试决策，
    不直接出现在前端响应里。
    """

    def __init__(
        self,
        message: str = "模型调用失败",
        *,
        code: int = BizCode.MODEL_UNAVAILABLE,
        data: object = None,
        provider: str | None = None,
        model: str | None = None,
        error_type: ModelErrorType = ModelErrorType.UNKNOWN,
    ) -> None:
        super().__init__(message, code=code, data=data)
        self.provider = provider
        self.model = model
        self.error_type = error_type
