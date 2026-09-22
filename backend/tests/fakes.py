from verso_framework.providers.zhihu import (
    ZhihuCollection,
    ZhihuContent,
    ZhihuFollowee,
    ZhihuProfile,
    ZhihuToken,
)


class FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.lists: dict[str, list[str]] = {}

    def set(
        self,
        name: str,
        value: str,
        ex: int | None = None,
        nx: bool = False,
    ) -> bool | None:
        if nx and name in self.values:
            return None
        self.values[name] = value
        return True

    def get(self, name: str) -> str | None:
        return self.values.get(name)

    def getdel(self, name: str) -> str | None:
        return self.values.pop(name, None)

    def delete(self, *names: str) -> None:
        for name in names:
            self.values.pop(name, None)

    def rpush(self, name: str, *values: str) -> int:
        bucket = self.lists.setdefault(name, [])
        bucket.extend(values)
        return len(bucket)

    def blpop(self, keys: list[str] | str, timeout: int = 0) -> tuple[str, str] | None:
        names = [keys] if isinstance(keys, str) else list(keys)
        for name in names:
            bucket = self.lists.get(name) or []
            if bucket:
                return name, bucket.pop(0)
        return None


class FakeOAuth:
    def __init__(self, profile: ZhihuProfile) -> None:
        self.profile = profile
        self.codes: list[str] = []

    def authorization_url(self, state: str) -> str:
        return f"https://openapi.zhihu.com/authorize?state={state}"

    def exchange_code(self, code: str) -> ZhihuToken:
        self.codes.append(code)
        return ZhihuToken(access_token="tok", expires_in=3600)

    def fetch_profile(self, access_token: str) -> ZhihuProfile:
        return self.profile


class FakeZhihu:
    def __init__(
        self,
        contents: list[ZhihuContent] | None = None,
        followees: list[ZhihuFollowee] | None = None,
        collections: list[ZhihuCollection] | None = None,
    ) -> None:
        self.contents = contents or []
        self.followees = followees or []
        self.collections = collections or []

    def list_contents(self, access_token: str, *, limit: int = 50) -> list[ZhihuContent]:
        return self.contents

    def list_followees(self, access_token: str, *, limit: int = 20) -> list[ZhihuFollowee]:
        return self.followees

    def list_favorites(self, access_token: str, *, limit: int = 50) -> list[ZhihuCollection]:
        return self.collections


class FakeEmbedder:
    """测试用：按关键词轴计数，让健身/实习类文本能分开。"""

    TOKENS = (
        "徒手",
        "健身",
        "训练",
        "实习",
        "跳槽",
        "管理",
        "理财",
        "定投",
        "写作",
        "可读",
        "间隔",
    )

    def embed_documents(self, texts):
        return [self.embed_query(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        vec = [float(text.count(token)) for token in self.TOKENS]
        norm = sum(value * value for value in vec) ** 0.5
        if norm <= 0:
            return vec
        return [value / norm for value in vec]
