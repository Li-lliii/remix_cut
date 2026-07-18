from __future__ import annotations

from pathlib import Path

from platform_app.modules.digital_humans.service import DigitalHumanService


class DigitalHumanCreateService(DigitalHumanService):
    """数字人创建域服务入口。

    当前先复用 DigitalHumanService 的创建编排；后续真实训练回调、模型结果入库等创建域逻辑
    可以逐步迁移到这里，避免主 service.py 继续膨胀。
    """

    def __init__(self, *, db_path: Path, uploads_dir: Path):
        super().__init__(db_path=db_path, uploads_dir=uploads_dir)
