"""LLM 工厂类

使用 LangChain ChatOpenAI 通过 OpenAI 兼容模式调用阿里云 DashScope
这种方式便于后续切换到其他支持 OpenAI API 的模型提供商

支持的模型提供商（只需修改 base_url 和 api_key）：
- 阿里云 DashScope: https://dashscope.aliyuncs.com/compatible-mode/v1
- OpenAI: https://api.openai.com/v1
- Azure OpenAI: https://{resource}.openai.azure.com
- 其他兼容 OpenAI API 的服务
"""

from typing import Any

from langchain_openai import ChatOpenAI
from pydantic import SecretStr

from app.core.config import AppSettings


class LLMFactory:
    """LLM 工厂类 - 使用 OpenAI 兼容模式"""

    DASHSCOPE_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"

    def create_chat_model(
        self,
        model: str | None = None,
        temperature: float = 0.7,
        streaming: bool = True,
        base_url: str | None = None,
        api_key: str | None = None,
        settings: AppSettings | None = None,
    ) -> ChatOpenAI:
        if settings is None:
            settings = AppSettings.from_env()
        model = model or settings.dashscope_model
        base_url = base_url or LLMFactory.DASHSCOPE_BASE_URL
        api_key = api_key or settings.dashscope_api_key

        extra_body: dict[str, Any] = {}
        extra_body["stream"] = streaming

        llm = ChatOpenAI(
            model=model,
            temperature=temperature,
            streaming=streaming,
            base_url=base_url,
            api_key=SecretStr(api_key),
            timeout=settings.llm_request_timeout_seconds,
            max_retries=settings.llm_max_retries,
            model_kwargs={"retry_delay": settings.llm_retry_delay_seconds},
            extra_body=extra_body if extra_body else None,
        )

        return llm


# 全局 LLM 工厂实例
llm_factory = LLMFactory()
