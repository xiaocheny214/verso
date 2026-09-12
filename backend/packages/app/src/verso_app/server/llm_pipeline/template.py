"""P0 从摘要截句。P2 在本模块换成 ChatModel，不改 MapService。"""


class TemplateMapPipeline:
    async def opening_topics(self, title: str, excerpt: str) -> list[str]:
        text = (excerpt or title).strip()
        if not text:
            return ["这篇文章的核心结论是什么？", "有哪一点你不同意？", "读完还想追问什么？"]
        snippet = text[:80]
        return [
            f"作者在说：{snippet}",
            "这个结论的前提成立吗？",
            "如果用在你自己的场景里，会卡在哪？",
        ]

    async def pull_back(self, excerpt: str, last_messages: list[str]) -> str:
        return "拉回地图：讨论还围着这篇文章的结论吗？"

    async def summarize(self, excerpt: str, messages: list[str]) -> str:
        return "本局围绕原文交换了看法（模板纪要，待接入模型）。"
