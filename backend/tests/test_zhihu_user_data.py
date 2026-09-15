import httpx
import pytest

from verso_framework.config.app import AppSettings
from verso_framework.providers.zhihu.user_data import HttpxUserDataClient, ZhihuUserDataError

_SETTINGS = AppSettings(
    zhihu_client_id="app-id",
    zhihu_client_secret="app-key",
    zhihu_access_secret="platform-secret",
    zhihu_redirect_uri="http://localhost:8000/auth/zhihu/callback",
)


def _client(monkeypatch, handler) -> HttpxUserDataClient:
    client = HttpxUserDataClient(_SETTINGS)
    monkeypatch.setattr(
        client, "_client", lambda: httpx.Client(transport=httpx.MockTransport(handler))
    )
    return client


def test_list_contents_success_empty_items(monkeypatch) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"code": 20000, "Data": {"Items": []}})

    assert _client(monkeypatch, handler).list_contents("tok") == []


def test_list_contents_accepts_documented_code_zero(monkeypatch) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "Code": 0,
                "Message": "success",
                "Data": {
                    "Items": [
                        {
                            "Title": "一篇回答",
                            "Summary": "摘要",
                            "Url": "https://www.zhihu.com/answer/1",
                            "ContentType": "answer",
                            "CreatedAt": 1710000000,
                        }
                    ]
                },
            },
        )

    items = _client(monkeypatch, handler).list_contents("tok")
    assert len(items) == 1
    assert items[0].title == "一篇回答"
    assert items[0].url == "https://www.zhihu.com/answer/1"


def test_list_followees_accepts_code_zero(monkeypatch) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "Code": 0,
                "Data": {
                    "Items": [
                        {
                            "Fullname": "邻人",
                            "Headline": "写代码",
                            "Url": "https://www.zhihu.com/people/lin",
                        }
                    ]
                },
            },
        )

    items = _client(monkeypatch, handler).list_followees("tok")
    assert items[0].fullname == "邻人"


def test_list_contents_http_error_is_not_empty(monkeypatch) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"code": 20000, "Data": {"Items": []}})

    with pytest.raises(ZhihuUserDataError, match="HTTP 500"):
        _client(monkeypatch, handler).list_contents("tok")


def test_list_contents_biz_error_is_not_empty(monkeypatch) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"code": 40001, "message": "fail", "Data": {"Items": []}})

    with pytest.raises(ZhihuUserDataError, match="code=40001"):
        _client(monkeypatch, handler).list_contents("tok")


def test_list_contents_pascal_biz_error_includes_keys(monkeypatch) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"Code": 20001, "Message": "鉴权失败", "Data": {}})

    with pytest.raises(ZhihuUserDataError, match=r"code=20001 keys=Code,Data,Message"):
        _client(monkeypatch, handler).list_contents("tok")


def test_list_contents_network_error_is_not_empty(monkeypatch) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down")

    with pytest.raises(ZhihuUserDataError, match="network error"):
        _client(monkeypatch, handler).list_contents("tok")
