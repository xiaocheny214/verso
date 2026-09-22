"""独立进程入口。以后 Compose 里与 api 拆开扩容，仍只调 server。"""

from __future__ import annotations

import logging

from verso_app.worker.handlers import run_portrait_sync_loop


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    logging.getLogger("verso.worker.portrait").info("portrait sync worker started")
    run_portrait_sync_loop()


if __name__ == "__main__":
    main()
