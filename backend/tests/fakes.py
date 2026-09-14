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

    def set(self, name: str, value: str, ex: int | None = None) -> None:
        self.values[name] = value

    def get(self, name: str) -> str | None:
        return self.values.get(name)

    def getdel(self, name: str) -> str | None:
        return self.values.pop(name, None)

    def delete(self, *names: str) -> None:
        for name in names:
            self.values.pop(name, None)


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
