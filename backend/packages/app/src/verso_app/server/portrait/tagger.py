"""从标题 / 摘要里抽出闭集擅长标签。本期规则抽取，以后可换成模型。"""

from verso_common.enums import StrengthTag

_KEYWORDS: dict[StrengthTag, tuple[str, ...]] = {
    StrengthTag.PROGRAMMING: (
        "编程",
        "代码",
        "python",
        "java",
        "开发",
        "程序员",
        "后端",
        "前端",
        "算法",
        "golang",
        "rust",
    ),
    StrengthTag.INTERNET: ("互联网", "产品经理", "运营", "增长", "互联网产品"),
    StrengthTag.FITNESS: ("健身", "徒手", "增肌", "减脂", "撸铁", "力量训练"),
    StrengthTag.TRAINING: ("运动训练", "跑步", "训练计划", "体能"),
    StrengthTag.CAREER: ("职场", "求职", "面试", "跳槽", "简历"),
    StrengthTag.STUDY: ("学业", "考研", "高考", "留学", "论文"),
    StrengthTag.FINANCE: ("理财", "基金", "股票", "投资"),
    StrengthTag.WRITING: ("写作", "文案", "小说"),
    StrengthTag.DESIGN: ("设计", "ui", "ux", "视觉"),
    StrengthTag.HEALTH: ("医学", "健康", "看病", "临床"),
    StrengthTag.LAW: ("法律", "律师", "合同", "诉讼"),
}


def tags_from_text(*parts: str) -> list[StrengthTag]:
    blob = " ".join(part for part in parts if part).lower()
    if not blob:
        return []
    found: list[StrengthTag] = []
    for tag, words in _KEYWORDS.items():
        if any(word.lower() in blob for word in words):
            found.append(tag)
    return found
