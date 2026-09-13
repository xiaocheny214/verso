"""实时频道。匹配成功通知走 user；对话事件走 exchange。禁止全站广播。"""

from enum import StrEnum


class RealtimeChannel(StrEnum):
    USER = "user"
    EXCHANGE = "exchange"
