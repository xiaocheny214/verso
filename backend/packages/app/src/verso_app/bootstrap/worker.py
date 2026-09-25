"""独立进程入口。以后 Compose 里与 api 拆开扩容，仍只调 server。"""

from __future__ import annotations

import logging
import threading

from verso_app.worker.handlers import run_portrait_sync_loop
from verso_app.worker.jobs import run_job_loop


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    threading.Thread(target=run_job_loop, name="verso-job-consumer", daemon=True).start()
    logging.getLogger("verso.worker.portrait").info("portrait sync worker started")
    run_portrait_sync_loop()


if __name__ == "__main__":
    main()
