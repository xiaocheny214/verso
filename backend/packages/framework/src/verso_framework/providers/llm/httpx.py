"""OpenAI 兼容的同步补全。quality 在模型失败时记 unclear。"""

from __future__ import annotations

import httpx
from verso_common.enums import ModelErrorType
from verso_common.exceptions import ModelException

from verso_framework.config.app import AppSettings


class HttpxChatModel:
    def __init__(self, settings: AppSettings, *, timeout: float = 20.0) -> None:
        self._settings = settings
        self._timeout = timeout

    def complete(self, prompt: str) -> str:
        if not (
            self._settings.llm_api_key
            and self._settings.llm_base_url
            and self._settings.llm_model
        ):
            raise ModelException(
                "未配置评估模型",
                error_type=ModelErrorType.AUTH,
            )
        url = self._settings.llm_base_url.rstrip("/") + "/chat/completions"
        try:
            with httpx.Client(timeout=self._timeout) as client:
                response = client.post(
                    url,
                    headers={"Authorization": f"Bearer {self._settings.llm_api_key}"},
                    json={
                        "model": self._settings.llm_model,
                        "messages": [{"role": "user", "content": prompt}],
                        "temperature": 0,
                    },
                )
            response.raise_for_status()
            payload = response.json()
        except httpx.TimeoutException as exc:
            raise ModelException("模型超时", error_type=ModelErrorType.TIMEOUT) from exc
        except httpx.HTTPStatusError as exc:
            error_type = (
                ModelErrorType.RATE_LIMIT
                if exc.response.status_code == 429
                else ModelErrorType.NETWORK
            )
            raise ModelException("模型调用失败", error_type=error_type) from exc
        except httpx.HTTPError as exc:
            raise ModelException("模型调用失败", error_type=ModelErrorType.NETWORK) from exc
        except ValueError as exc:
            raise ModelException(
                "模型响应无效", error_type=ModelErrorType.INVALID_RESPONSE
            ) from exc
        try:
            content = payload["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ModelException(
                "模型响应无效", error_type=ModelErrorType.INVALID_RESPONSE
            ) from exc
        if not isinstance(content, str):
            raise ModelException("模型响应无效", error_type=ModelErrorType.INVALID_RESPONSE)
        return content
