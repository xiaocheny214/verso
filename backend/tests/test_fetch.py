from verso_app.server.fetch.html import html_to_markdown
from verso_app.server.fetch.urls import archivable_from_content, parse_archivable_url


def test_parse_article_and_answer_urls() -> None:
    article = parse_archivable_url("https://zhuanlan.zhihu.com/p/357892158")
    assert article is not None
    assert article.kind == "article"
    assert article.content_id == "357892158"
    answer = parse_archivable_url("https://www.zhihu.com/question/1/answer/2")
    assert answer is not None
    assert answer.kind == "answer"
    assert answer.content_id == "2"
    short = parse_archivable_url("https://www.zhihu.com/answer/99")
    assert short is not None
    assert short.content_id == "99"


def test_skip_question_column_and_unrelated_hosts() -> None:
    assert parse_archivable_url("https://www.zhihu.com/question/123") is None
    assert parse_archivable_url("https://www.zhihu.com/column/abc") is None
    assert parse_archivable_url("https://example.com/p/1") is None


def test_list_type_filters_pins() -> None:
    url = "https://zhuanlan.zhihu.com/p/1"
    assert archivable_from_content(url=url, content_type="pin") is None
    assert archivable_from_content(url=url, content_type="article") is not None
    assert (
        archivable_from_content(url="https://www.zhihu.com/pin/1", content_type="article") is None
    )


def test_html_to_markdown_keeps_headings_and_links() -> None:
    md = html_to_markdown(
        '<h2>小节</h2><p>先看 <a href="https://zhihu.com">链接</a>。</p><ul><li>一项</li></ul>'
    )
    assert "## 小节" in md
    assert "[链接](https://zhihu.com)" in md
    assert "- 一项" in md
