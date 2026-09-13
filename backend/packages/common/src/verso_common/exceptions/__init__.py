"""异常：业务异常基类与大模型调用异常。"""

from verso_common.exceptions.biz import BizException
from verso_common.exceptions.model import ModelException

__all__ = ["BizException", "ModelException"]
