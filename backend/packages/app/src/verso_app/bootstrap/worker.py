"""独立进程入口。以后 Compose 里与 api 拆开扩容，仍只调 server。"""


def main() -> None:
    raise SystemExit("worker consumers are not wired yet")
