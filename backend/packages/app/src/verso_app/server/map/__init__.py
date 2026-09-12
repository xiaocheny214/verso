"""局内地图业务：时机、房间、战绩。生成管线经 MapPipeline 注入。"""

from verso_app.server.map.ports import MapPipeline
from verso_app.server.map.service import MapService

__all__ = ["MapPipeline", "MapService"]
