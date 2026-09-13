"""LangChain 聊天模型。quality 只拿模型，提示词和打分规则留在 judge。"""

from langchain_core.language_models import BaseChatModel
from langchain_openai import ChatOpenAI

from verso_framework.config.app import AppSettings


def build_chat_model(settings: AppSettings) -> BaseChatModel:
    kwargs: dict[str, object] = {
        "model": settings.llm_model,
        "api_key": settings.llm_api_key,
        "temperature": 0,
    }
    if settings.llm_base_url:
        kwargs["base_url"] = settings.llm_base_url
    return ChatOpenAI(**kwargs)
