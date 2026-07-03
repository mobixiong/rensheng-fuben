import argparse
import socket
import sys
import threading
import time
import urllib.request
import webbrowser
from multiprocessing import freeze_support

import uvicorn

from app.main import app
from app.paths import ENV_PATH, WORKSPACE


def _port_in_use(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(1)
        return sock.connect_ex((host, port)) == 0


def _open_when_ready(url: str) -> None:
    for _ in range(60):
        try:
            with urllib.request.urlopen(f"{url}api/health", timeout=1) as response:
                if response.status == 200:
                    webbrowser.open(url)
                    return
        except Exception:
            time.sleep(0.5)


def main() -> int:
    parser = argparse.ArgumentParser(description="人生副本工作台 Windows launcher")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=7860)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()

    WORKSPACE.mkdir(parents=True, exist_ok=True)
    url = f"http://{args.host}:{args.port}/"

    print("人生副本工作台")
    print(f"访问地址: {url}")
    print(f"本地数据目录: {WORKSPACE}")
    print(f"配置文件: {ENV_PATH}")

    if _port_in_use(args.host, args.port):
        print(f"端口 {args.port} 已被占用。如果已有工作台在运行，将直接打开浏览器。")
        if not args.no_browser:
            webbrowser.open(url)
        return 0

    if not args.no_browser:
        threading.Thread(target=_open_when_ready, args=(url,), daemon=True).start()

    uvicorn.run(app, host=args.host, port=args.port, log_level="info")
    return 0


if __name__ == "__main__":
    freeze_support()
    raise SystemExit(main())
