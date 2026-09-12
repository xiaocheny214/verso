from pydantic import BaseModel


class Ok[T](BaseModel):
    ok: bool = True
    data: T


class Err(BaseModel):
    ok: bool = False
    code: str
    message: str
