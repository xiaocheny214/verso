import httpx
import pytest

from verso_app.server.fetch.errors import FetchError
from verso_app.server.fetch.http import HttpxZhihuMarkdownFetcher
from verso_app.server.fetch.service import FetchService
from verso_app.server.fetch.urls import parse_archivable_url


def _client(handler) -> HttpxZhihuMarkdownFetcher:
    transport = httpx.MockTransport(handler)
    return HttpxZhihuMarkdownFetcher(client=httpx.Client(transport=transport))


def test_fetch_article_html_to_markdown() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert "/articles/123" in str(request.url)
        return httpx.Response(
            200,
            json={"title": "专栏标题", "content": "<p>正文<strong>加粗</strong></p>"},
        )

    doc = FetchService(_client(handler)).fetch("https://zhuanlan.zhihu.com/p/123")
    assert doc.content_type == "article"
    assert doc.title == "专栏标题"
    assert "正文" in doc.markdown
    assert "**加粗**" in doc.markdown


def test_fetch_answer_uses_question_title() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert "/answers/9" in str(request.url)
        return httpx.Response(
            200,
            json={
                "content": "<p>回答正文</p>",
                "question": {"title": "问题标题"},
            },
        )

    target = parse_archivable_url("https://www.zhihu.com/answer/9")
    assert target is not None
    doc = FetchService(_client(handler)).fetch_target(target)
    assert doc.content_type == "answer"
    assert doc.title == "问题标题"
    assert "回答正文" in doc.markdown


def test_fetch_http_error_is_fetch_error() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, json={"error": {"message": "denied"}})

    with pytest.raises(FetchError):
        FetchService(_client(handler)).fetch("https://zhuanlan.zhihu.com/p/1")


def test_fetch_rejects_question_page() -> None:
    with pytest.raises(FetchError, match="not an article or answer"):
        FetchService(_client(lambda _r: httpx.Response(500))).fetch(
            "https://www.zhihu.com/question/1"
        )
