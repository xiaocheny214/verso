"""易变的 LLM 管线：提示词、模板、以后的模型步。与 map / room 同层，可被其他 server 模块调用。"""

from verso_app.server.llm_pipeline.template import TemplateMapPipeline

__all__ = ["TemplateMapPipeline"]
