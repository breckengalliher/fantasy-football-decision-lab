"""Controlled local Streamlit/browser performance benchmark.

Runs only against a temporary local server and a disposable Chrome profile.
Outputs JSON with server startup, browser navigation/paint, layout shift, JS heap,
and Streamlit process resource measurements.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import shutil
import subprocess
import tempfile
import time
import urllib.request
from pathlib import Path

import websockets


ROOT = Path(__file__).resolve().parents[1]
CHROME = Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe")


async def cdp(ws_url: str, url: str, repeats: int, ready_selector: str, width: int, height: int) -> list[dict]:
    results: list[dict] = []
    async with websockets.connect(ws_url, origin=None, max_size=8_000_000) as socket:
        sequence = 0

        async def command(method: str, params: dict | None = None) -> dict:
            nonlocal sequence
            sequence += 1
            await socket.send(json.dumps({"id": sequence, "method": method, "params": params or {}}))
            while True:
                message = json.loads(await socket.recv())
                if message.get("id") == sequence:
                    if "error" in message:
                        raise RuntimeError(f"CDP {method}: {message['error']}")
                    return message.get("result", {})

        await command("Page.enable")
        await command("Runtime.enable")
        await command("Performance.enable")
        await command("Emulation.setDeviceMetricsOverride", {"width": width, "height": height, "deviceScaleFactor": 1, "mobile": width < 768})
        await command("Page.addScriptToEvaluateOnNewDocument", {"source": """
          window.__qa = {cls: 0, lcp: 0};
          new PerformanceObserver(list => { for (const e of list.getEntries()) if (!e.hadRecentInput) window.__qa.cls += e.value; }).observe({type:'layout-shift', buffered:true});
          new PerformanceObserver(list => { const a=list.getEntries(); if(a.length) window.__qa.lcp=a[a.length-1].startTime; }).observe({type:'largest-contentful-paint', buffered:true});
        """})
        for index in range(repeats):
            started = time.perf_counter()
            await command("Page.navigate", {"url": url})
            deadline = time.perf_counter() + 8
            ready = False
            while time.perf_counter() < deadline:
                await asyncio.sleep(0.05)
                state = await command("Runtime.evaluate", {"expression": f"document.readyState === 'complete' && !!document.querySelector({json.dumps(ready_selector)})", "returnByValue": True})
                ready = bool(state.get("result", {}).get("value"))
                if ready:
                    # Streamlit's static shell loads before its WebSocket-driven UI.
                    visible = await command("Runtime.evaluate", {"expression": "document.body.innerText.trim().length > 20", "returnByValue": True})
                    if visible.get("result", {}).get("value"):
                        break
            await asyncio.sleep(0.25)
            metrics = await command("Runtime.evaluate", {"expression": """
              (() => { const n=performance.getEntriesByType('navigation')[0]||{}; const p=Object.fromEntries(performance.getEntriesByType('paint').map(x=>[x.name,x.startTime])); return {
                domContentLoaded:n.domContentLoadedEventEnd||0, load:n.loadEventEnd||0, responseStart:n.responseStart||0,
                fcp:p['first-contentful-paint']||0, cls:window.__qa?.cls||0, lcp:window.__qa?.lcp||0,
                bodyChars:document.body.innerText.length, scrollWidth:document.documentElement.scrollWidth,
                clientWidth:document.documentElement.clientWidth, heap:performance.memory?.usedJSHeapSize||0,
                visibleButtons:[...document.querySelectorAll('button')].filter(x=>{const r=x.getBoundingClientRect();return r.width&&r.height}).length,
                undersizedButtons:[...document.querySelectorAll('button')].filter(x=>{const r=x.getBoundingClientRect();return r.width&&r.height&&(r.width<44||r.height<44)}).length,
                clippedText:[...document.querySelectorAll('h1,h2,h3,p,span,button,label')].filter(x=>x.scrollWidth>x.clientWidth+1).length
              }; })()
            """, "returnByValue": True})
            value = metrics.get("result", {}).get("value", {})
            value.update({"run": index + 1, "wall_ms": round((time.perf_counter() - started) * 1000, 2), "ready": ready})
            results.append(value)
    return results


def wait_json(url: str, timeout: float = 20) -> object:
    deadline = time.perf_counter() + timeout
    while time.perf_counter() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1) as response:
                return json.load(response)
        except Exception:
            time.sleep(0.1)
    raise TimeoutError(url)


def process_metrics(pid: int) -> dict:
    command = ["powershell", "-NoProfile", "-Command", f"$p=Get-Process -Id {pid}; [pscustomobject]@{{WorkingSet=$p.WorkingSet64;PrivateMemory=$p.PrivateMemorySize64;CPU=$p.CPU}} | ConvertTo-Json -Compress"]
    return json.loads(subprocess.check_output(command, text=True))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    parser.add_argument("--port", type=int, default=8530)
    parser.add_argument("--repeats", type=int, default=7)
    parser.add_argument("--width", type=int, default=390)
    parser.add_argument("--height", type=int, default=844)
    args = parser.parse_args()
    profile = Path(tempfile.mkdtemp(prefix="sdl-benchmark-"))
    stdout = tempfile.TemporaryFile()
    stderr = tempfile.TemporaryFile()
    server = chrome = None
    try:
        started = time.perf_counter()
        server = subprocess.Popen([os.sys.executable, "-m", "streamlit", "run", "dashboard/app.py", "--server.headless", "true", "--browser.gatherUsageStats", "false", "--server.port", str(args.port)], cwd=ROOT, stdout=stdout, stderr=stderr)
        health = f"http://127.0.0.1:{args.port}/_stcore/health"
        deadline = time.perf_counter() + 30
        while time.perf_counter() < deadline:
            try:
                with urllib.request.urlopen(health, timeout=1) as response:
                    if response.status == 200:
                        break
            except Exception:
                time.sleep(0.05)
        startup_ms = round((time.perf_counter() - started) * 1000, 2)
        baseline_resource = process_metrics(server.pid)
        debug_port = args.port + 1000
        chrome = subprocess.Popen([str(CHROME), "--headless=new", "--disable-gpu", "--hide-scrollbars", "--remote-allow-origins=*", f"--remote-debugging-port={debug_port}", f"--user-data-dir={profile}", f"--window-size={args.width},{args.height}", "about:blank"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        targets = wait_json(f"http://127.0.0.1:{debug_port}/json")
        page_target = next(target for target in targets if target.get("type") == "page")
        ws_url = page_target["webSocketDebuggerUrl"]
        base = f"http://127.0.0.1:{args.port}"
        paths = {
            "home_mobile": (f"{base}/?view=home", ".landing-hero"),
            "comparison_mobile": (f"{base}/?view=decision-room&position=WR&players=Puka%20Nacua%7CJaxon%20Smith-Njigba", ".decision-edge"),
            "trends_mobile": (f"{base}/?view=player-trends", ".trend-player-card"),
            "command_center_login_mobile": (f"{base}/?view=command-center", ".cc-auth-intro"),
        }
        browser = {name: asyncio.run(cdp(ws_url, url, args.repeats, selector, args.width, args.height)) for name, (url, selector) in paths.items()}
        final_resource = process_metrics(server.pid)
        result = {
            "environment": {"viewport": f"{args.width}x{args.height}", "network": "local loopback", "runs": args.repeats, "python": os.sys.version},
            "server_startup_ms": startup_ms,
            "server_resource_before": baseline_resource,
            "server_resource_after": final_resource,
            "browser": browser,
        }
        Path(args.output).write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(json.dumps(result, indent=2))
    finally:
        if chrome:
            chrome.terminate()
            try: chrome.wait(5)
            except subprocess.TimeoutExpired: chrome.kill()
        if server:
            server.terminate()
            try: server.wait(5)
            except subprocess.TimeoutExpired: server.kill()
        stdout.close(); stderr.close()
        shutil.rmtree(profile, ignore_errors=True)


if __name__ == "__main__":
    main()
