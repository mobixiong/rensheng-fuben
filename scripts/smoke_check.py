from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlsplit, urlunsplit
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]


def quote_url(url: str) -> str:
    parts = urlsplit(url)
    return urlunsplit((
        parts.scheme,
        parts.netloc,
        quote(parts.path, safe="/"),
        quote(parts.query, safe="=&?/:"),
        parts.fragment,
    ))


def read_json(url: str, timeout: int = 10) -> tuple[int, str, object]:
    with urlopen(quote_url(url), timeout=timeout) as res:
        body = res.read().decode("utf-8")
        return res.status, res.headers.get("content-type", ""), json.loads(body)


def read_text(url: str, timeout: int = 10) -> tuple[int, str, str]:
    with urlopen(quote_url(url), timeout=timeout) as res:
        body = res.read().decode("utf-8", errors="replace")
        return res.status, res.headers.get("content-type", ""), body


def post_json(url: str, payload: dict, timeout: int = 30) -> tuple[int, str, object]:
    data = json.dumps(payload).encode("utf-8")
    req = Request(quote_url(url), data=data, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urlopen(req, timeout=timeout) as res:
            body = res.read().decode("utf-8")
            return res.status, res.headers.get("content-type", ""), json.loads(body)
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        try:
            parsed: object = json.loads(body)
        except json.JSONDecodeError:
            parsed = body
        return exc.code, exc.headers.get("content-type", ""), parsed


def head(url: str, timeout: int = 10) -> tuple[int, str]:
    req = Request(quote_url(url), method="HEAD")
    with urlopen(req, timeout=timeout) as res:
        return res.status, res.headers.get("content-type", "")


def check(condition: bool, label: str, detail: str = "") -> None:
    if condition:
        print(f"[OK] {label}{': ' + detail if detail else ''}")
        return
    raise AssertionError(f"{label}{': ' + detail if detail else ''}")


def load_env() -> dict[str, str]:
    env_path = ROOT / ".env"
    values: dict[str, str] = {}
    if not env_path.exists():
        return values
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def browser_candidates() -> list[str]:
    candidates = [
        shutil.which("chrome"),
        shutil.which("msedge"),
        shutil.which("chromium"),
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    ]
    return [item for item in candidates if item and Path(item).exists()]


def check_browser_dom(base_url: str) -> None:
    browsers = browser_candidates()
    if not browsers:
        print("[SKIP] browser DOM: Chrome/Edge not found")
        return
    profile = Path(tempfile.gettempdir()) / f"rensheng-fuben-smoke-browser-{uuid.uuid4().hex}"
    cmd = [
        browsers[0],
        "--headless=new",
        "--disable-gpu",
        "--no-first-run",
        "--no-default-browser-check",
        f"--user-data-dir={profile}",
        "--virtual-time-budget=5000",
        "--dump-dom",
        base_url,
    ]
    completed = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=20)
    if completed.returncode != 0:
        raise AssertionError(f"browser DOM failed: {completed.stderr[:500]}")
    dom = completed.stdout
    check('type="module"' in dom and "/static/app.js" in dom, "browser module script loaded")
    check('id="status">就绪</div>' in dom, "browser boot status", "就绪")
    check('class="shot-card' in dom, "browser shot cards rendered")
    check('status-pill error' not in dom, "browser has no boot error")


def check_external_connections(base_url: str) -> None:
    env = load_env()
    text_payload = {
        "provider": env.get("TEXT_PROVIDER") or "openai",
        "base_url": env.get("LLM_BASE_URL") or env.get("GEMINI_WEB2API_BASE_URL") or "",
        "model": env.get("LLM_MODEL") or env.get("GEMINI_WEB2API_MODEL") or "",
        "api_key": env.get("LLM_API_KEY") or env.get("GEMINI_WEB2API_API_KEY") or "",
        "temperature": 0,
    }
    if all(text_payload.get(key) for key in ("base_url", "model", "api_key")):
        status, _, data = post_json(f"{base_url}/api/settings/test-text", text_payload, timeout=45)
        check(status == 200, "text connection", f"HTTP {status}")
        if isinstance(data, dict):
            print(f"[OK] text model: {data.get('provider')} / {data.get('model')}")
    else:
        print("[SKIP] text connection: missing .env text config")

    image_payload = {
        "provider": env.get("IMAGE_PROVIDER") or "openai",
        "base_url": env.get("IMAGE_BASE_URL") or "",
        "model": env.get("IMAGE_MODEL") or "",
        "api_key": env.get("IMAGE_API_KEY") or "",
        "size": env.get("IMAGE_SIZE") or "9:16",
    }
    if all(image_payload.get(key) for key in ("base_url", "model", "api_key")):
        status, _, data = post_json(f"{base_url}/api/settings/test-image", image_payload, timeout=45)
        check(status == 200, "image connection", f"HTTP {status}")
        if isinstance(data, dict):
            print(f"[OK] image model: {data.get('provider')} / {data.get('model')}")
    else:
        print("[SKIP] image connection: missing .env image config")


def run(base_url: str, include_external: bool) -> None:
    for path in [
        "/api/health",
        "/api/example",
        "/api/projects",
        "/api/project/current",
        "/api/prompt/default",
        "/api/prompt/image",
        "/api/prompt/improve-image",
    ]:
        status, content_type, _ = read_json(f"{base_url}{path}")
        check(status == 200 and "application/json" in content_type, f"GET {path}", content_type)

    status, content_type, index_html = read_text(f"{base_url}/")
    check(status == 200 and "text/html" in content_type, "GET /", content_type)
    check('type="module" src="/static/app.js"' in index_html, "index module entry")

    for path in [
        "/static/app.js",
        "/static/js/api.js",
        "/static/js/ui.js",
        "/static/js/settings.js",
        "/static/js/project-store.js",
        "/static/js/story-view.js",
        "/static/js/workflow.js",
        "/static/style.css",
    ]:
        status, content_type, _ = read_text(f"{base_url}{path}")
        check(status == 200, f"GET {path}", content_type)

    _, _, current = read_json(f"{base_url}/api/project/current")
    if isinstance(current, dict) and current.get("exists") and isinstance(current.get("state"), dict):
        story = current["state"].get("story") or {}
        shots = story.get("shots") or []
        check(isinstance(shots, list), "current project shots readable", str(len(shots)))
        image_urls = [shot.get("image_url") for shot in shots if isinstance(shot, dict) and shot.get("image_url")]
        done = sum(1 for shot in shots if isinstance(shot, dict) and shot.get("_image_status") == "done")
        print(f"[OK] project restored: shots={len(shots)} image_urls={len(image_urls)} done={done}")
        if image_urls:
            status, content_type = head(f"{base_url}{image_urls[0]}")
            check(status == 200 and content_type.startswith("image/"), "first project image", content_type)
    else:
        print("[SKIP] current project: no saved project")

    check_browser_dom(base_url)
    if include_external:
        check_external_connections(base_url)


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke check for 人生副本工作台.")
    parser.add_argument("--base-url", default="http://127.0.0.1:7860")
    parser.add_argument("--external", action="store_true", help="also test configured model connections")
    args = parser.parse_args()

    try:
        run(args.base_url.rstrip("/"), args.external)
        print("[OK] smoke check complete")
        return 0
    except (AssertionError, HTTPError, URLError, TimeoutError, OSError) as exc:
        print(f"[FAIL] {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
