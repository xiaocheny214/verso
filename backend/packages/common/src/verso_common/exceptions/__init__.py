class VersoError(Exception):
    """Base error. web 层翻成统一返回，server 只抛这个家族。"""


class AuthRequired(VersoError):
    pass


class InviteNotAllowed(VersoError):
    pass


class RoomClosed(VersoError):
    pass
