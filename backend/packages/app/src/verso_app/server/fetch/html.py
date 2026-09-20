"""知乎 HTML 正文转 Markdown。"""

from markdownify import markdownify


def html_to_markdown(html: str) -> str:
    text = markdownify(html or "", heading_style="ATX", bullets="-")
    return (text or "").strip()
