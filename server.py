"""
MarkItDown Website - Python Web Server (Webcom Powered)
======================================================
取代原版的 Docker + Nginx + Node.js (Puppeteer) 架構。
由 Webcom 可攜式 Python 3.11 環境直接運行。

主要功能：
1. 靜態檔案託管並自動補齊 COOP/COEP 標頭（Pyodide SharedArrayBuffer 必要條件）
2. GET /api/fetch-url 網址代理與 SSRF 防護（相容原版前端）
3. POST /api/convert 本地原生 Microsoft MarkItDown 極速轉檔
4. GET /health 服務健康檢查
"""

import os
import sys
import re
import io
import json
import socket
import base64
import tempfile
import urllib.request
import urllib.parse
from typing import Optional

# 確保載入 Webcom 的套件路徑
APP_DIR = os.path.dirname(os.path.abspath(__file__))
WEBCOM_DIR = os.path.abspath(os.path.join(APP_DIR, "..", "Webcom"))
WEBCOM_SITE_PACKAGES = os.path.join(WEBCOM_DIR, "python", "Lib", "site-packages")
if os.path.exists(WEBCOM_SITE_PACKAGES) and WEBCOM_SITE_PACKAGES not in sys.path:
    sys.path.insert(0, WEBCOM_SITE_PACKAGES)

from fastapi import FastAPI, Request, Response, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse, Response
from pydantic import BaseModel
import uvicorn

app = FastAPI(title="MarkItDown Website Server", version="1.0.0")

# 允許跨來源請求
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Type", "X-Original-Url"],
)

# ── 安全標頭中介層 (COOP / COEP / CORP) ───────────────────────────────────────
@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response: Response = await call_next(request)
    # Pyodide / SharedArrayBuffer 必要標頭
    response.headers["Cross-Origin-Opener-Policy"] = "same-origin"
    response.headers["Cross-Origin-Embedder-Policy"] = "require-corp"
    response.headers["Cross-Origin-Resource-Policy"] = "cross-origin"
    # 防止 sw.js 與 manifest 快取
    path = request.url.path
    if path in ["/sw.js", "/wheels/manifest.json"]:
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
    return response

import ipaddress

def is_private_ip(ip: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip)
        return addr.is_private or addr.is_loopback or addr.is_link_local or addr.is_reserved or addr.is_multicast
    except Exception:
        return True


# ── 1. URL 抓取代理 (/api/fetch-url) ──────────────────────────────────────────
@app.get("/api/fetch-url")
def fetch_url(url: str):
    """
    抓取外部 URL 內容，回傳原始 binary/html 與標頭。
    相容原版 markitdown-website 前端需求。
    """
    if not url:
        raise HTTPException(status_code=400, detail="缺少 url 參數")
    
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in ["http", "https"]:
        raise HTTPException(status_code=400, detail="只允許 http 與 https 協定")
    
    hostname = parsed.hostname
    if not hostname:
        raise HTTPException(status_code=400, detail="無效的網址")
    
    # 解析 DNS 並執行 SSRF 檢查
    try:
        addrinfo = socket.getaddrinfo(hostname, None)
        ips = [ai[4][0] for ai in addrinfo]
        for ip in ips:
            if is_private_ip(ip):
                raise HTTPException(status_code=403, detail="禁止存取內部或私有網路位址 (SSRF 防護)")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"網址解析失敗: {e}")

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36 MarkItDown-Proxy/1.0",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.8",
    }

    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=30) as resp:
            content_type = resp.headers.get("Content-Type", "application/octet-stream")
            content = resp.read()
            
            # 50MB 限制
            if len(content) > 50 * 1024 * 1024:
                raise HTTPException(status_code=413, detail="檔案超過 50MB 上限")

            return Response(
                content=content,
                media_type=content_type,
                headers={
                    "Content-Type": content_type,
                    "X-Original-Url": url,
                    "Access-Control-Expose-Headers": "Content-Type, X-Original-Url"
                }
            )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"抓取網址失敗: {e}")

# ── 2. 本地原生 MarkItDown 極速轉檔 (/api/convert) ────────────────────────────
class ConvertRequest(BaseModel):
    filename: str
    data_base64: str

@app.post("/api/convert")
def convert_document(req: ConvertRequest):
    """
    使用 Webcom 本地原生 Microsoft MarkItDown 進行高速轉檔。
    無須等待 400MB Pyodide WASM 載入，1 秒內完成轉換。
    """
    md_engine = None
    try:
        from markitdown import MarkItDown
        md_engine = MarkItDown()
    except Exception as imp_err:
        # 1. 嘗試向 8001 Webcom Daemon 代理請求
        try:
            proxy_url = "http://127.0.0.1:8001/tools/parse_document"
            req_data = json.dumps({"filename": req.filename, "data_base64": req.data_base64}).encode("utf-8")
            preq = urllib.request.Request(proxy_url, data=req_data, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(preq, timeout=30) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                if data.get("status") == "success":
                    md_text = data.get("markdown") or data.get("text") or ""
                    title = os.path.splitext(req.filename)[0]
                    return {
                        "status": "success",
                        "filename": req.filename,
                        "title": title,
                        "markdown": md_text,
                        "charCount": len(md_text),
                        "lineCount": len(md_text.splitlines())
                    }
        except Exception:
            pass

        # 2. 純文字 / 代碼直讀 fallback
        ext = os.path.splitext(req.filename)[1].lower()
        if ext in (".txt", ".md", ".json", ".csv", ".tsv", ".py", ".js", ".html", ".htm", ".xml", ".yaml", ".yml"):
            try:
                raw_b64 = req.data_base64
                if "base64," in raw_b64:
                    raw_b64 = raw_b64.split("base64,", 1)[1]
                file_bytes = base64.b64decode(raw_b64)
                raw_text = file_bytes.decode("utf-8", errors="replace")
                title = os.path.splitext(req.filename)[0]
                return {
                    "status": "success",
                    "filename": req.filename,
                    "title": title,
                    "markdown": raw_text,
                    "charCount": len(raw_text),
                    "lineCount": len(raw_text.splitlines())
                }
            except Exception:
                pass

        raise HTTPException(
            status_code=500, 
            detail=f"本地未安裝 markitdown 套件 ({imp_err})。請執行: pip install markitdown[all] 或啟動 Webcom 常駐程式 (Port 8001)"
        )

    raw_b64 = req.data_base64
    if "base64," in raw_b64:
        raw_b64 = raw_b64.split("base64,", 1)[1]
    
    try:
        file_bytes = base64.b64decode(raw_b64)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Base64 解碼失敗: {e}")

    ext = os.path.splitext(req.filename)[1] or ".txt"
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as f:
            f.write(file_bytes)
            temp_path = f.name
        
        md_engine = MarkItDown()
        result = md_engine.convert(temp_path)
        markdown_text = result.text_content or ""
        title = getattr(result, "title", None) or os.path.splitext(req.filename)[0]

        return {
            "status": "success",
            "filename": req.filename,
            "title": title,
            "markdown": markdown_text,
            "charCount": len(markdown_text),
            "lineCount": len(markdown_text.splitlines())
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"MarkItDown 轉換失敗: {e}")
    finally:
        if temp_path and os.path.exists(temp_path):
            try: os.remove(temp_path)
            except Exception: pass

# ── 3. 健康檢查 ───────────────────────────────────────────────────────────────
@app.get("/health")
def health():
    return {
        "status": "online",
        "service": "MarkItDown Website (Webcom Powered)",
        "port": 8002
    }

# ── 4. 靜態資源託管 ───────────────────────────────────────────────────────────
import mimetypes
mimetypes.add_type("application/wasm", ".wasm")
mimetypes.add_type("application/octet-stream", ".whl")

app.mount("/", StaticFiles(directory=APP_DIR, html=True), name="static")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8002))
    print(f"==================================================")
    print(f"  MarkItDown Website (Webcom Powered)")
    print(f"  服務網址: http://127.0.0.1:{port}")
    print(f"==================================================")
    uvicorn.run(app, host="127.0.0.1", port=port)
