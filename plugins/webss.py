import subprocess
import os
import platform
import shutil
from datetime import datetime
import asyncio
from pathlib import Path
import time
import uuid
import tempfile
from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse, FileResponse
from utils import LOGGER

try:
    import cloudscraper
    CLOUDSCRAPER_AVAILABLE = True
except ImportError:
    CLOUDSCRAPER_AVAILABLE = False
    LOGGER.warning("Cloudscraper not installed - Cloudflare bypass unavailable")

router = APIRouter(prefix="/webss")

SCREENSHOT_DIR = Path("/tmp/screenshots")
STORE = {}
FILE_EXPIRY = 60

QUALITY_SETTINGS = {
    "low": {"width": 1280, "height": 720},
    "hd": {"width": 1920, "height": 1080},
    "fhd": {"width": 1920, "height": 1080},
    "wqhd": {"width": 2560, "height": 1440}
}

SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)

def find_browser():
    system = platform.system()
    
    if system == "Windows":
        paths = [
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
            os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
            r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
        ]
    elif system == "Darwin":
        paths = [
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            "/Applications/Chromium.app/Contents/MacOS/Chromium",
            "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge"
        ]
    else:
        browsers = ["google-chrome", "chromium", "chromium-browser", "microsoft-edge", "google-chrome-stable"]
        for browser in browsers:
            found = shutil.which(browser)
            if found:
                return found
        paths = [
            "/usr/bin/google-chrome",
            "/usr/bin/chromium",
            "/usr/bin/chromium-browser",
            "/snap/bin/chromium",
            "/usr/bin/google-chrome-stable"
        ]
    
    for path in paths:
        if os.path.exists(path):
            return path
    
    return None

async def bypass_cloudflare(url):
    if not CLOUDSCRAPER_AVAILABLE:
        return None
    
    try:
        scraper = cloudscraper.create_scraper(
            browser={
                'browser': 'chrome',
                'platform': 'windows',
                'mobile': False
            }
        )
        
        LOGGER.info(f"Attempting Cloudflare bypass for: {url}")
        
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(None, lambda: scraper.get(url, timeout=15))
        
        if response.status_code == 200:
            temp_file = tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False, dir='/tmp')
            temp_file.write(response.text)
            temp_file.close()
            LOGGER.info(f"Cloudflare bypass successful, saved HTML to: {temp_file.name}")
            return temp_file.name
        
    except Exception as e:
        LOGGER.warning(f"Cloudflare bypass failed: {str(e)}")
    
    return None

def cleanup_expired_files_sync():
    try:
        now = time.time()
        dead_keys = []
        
        for fid, data in list(STORE.items()):
            if now > data["exp"]:
                try:
                    if os.path.exists(data["path"]):
                        os.remove(data["path"])
                        LOGGER.info(f"Deleted expired screenshot: {os.path.basename(data['path'])}")
                except Exception as e:
                    LOGGER.error(f"Error deleting file: {str(e)}")
                dead_keys.append(fid)
        
        for fid in dead_keys:
            STORE.pop(fid, None)
            
    except Exception as e:
        LOGGER.error(f"Cleanup error: {str(e)}")

@router.get("/shot")
async def screenshot_endpoint(url: str, quality: str = "hd", bypass: bool = False):
    try:
        if not url:
            raise HTTPException(status_code=400, detail="URL parameter is required")
        
        quality = quality.lower()
        if quality not in QUALITY_SETTINGS:
            return JSONResponse(
                status_code=400,
                content={
                    "error": f"Invalid quality. Choose from: {', '.join(QUALITY_SETTINGS.keys())}",
                    "api_owner": "@ISmartCoder",
                    "api_updates": "t.me/abirxdhackz"
                }
            )
        
        if not url.startswith(('http://', 'https://')):
            url = 'https://' + url
        
        browser = find_browser()
        if not browser:
            return JSONResponse(
                status_code=500,
                content={
                    "error": "No browser found on system. Install Chrome, Chromium, or Edge",
                    "api_owner": "@ISmartCoder",
                    "api_updates": "t.me/abirxdhackz"
                }
            )
        
        target_url = url
        temp_html_file = None
        
        if bypass and CLOUDSCRAPER_AVAILABLE:
            temp_html_file = await bypass_cloudflare(url)
            if temp_html_file:
                target_url = f"file://{temp_html_file}"
        elif bypass and not CLOUDSCRAPER_AVAILABLE:
            LOGGER.warning("Cloudflare bypass requested but cloudscraper not installed")
        
        dimensions = QUALITY_SETTINGS[quality]
        width = dimensions["width"]
        height = dimensions["height"]
        
        fid = uuid.uuid4().hex
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        domain = url.split('//')[-1].split('/')[0].replace('www.', '').replace('.', '_')
        filename = f"{fid}_{domain}_{quality}_{timestamp}.png"
        output_path = SCREENSHOT_DIR / filename
        
        cmd = [
            browser,
            "--headless",
            "--disable-gpu",
            f"--screenshot={str(output_path)}",
            f"--window-size={width},{height}",
            "--hide-scrollbars",
            "--disable-dev-shm-usage",
            "--no-sandbox",
            "--disable-software-rasterizer",
            "--disable-extensions",
            "--disable-background-networking",
            "--disable-sync",
            "--metrics-recording-only",
            "--mute-audio",
            target_url
        ]
        
        LOGGER.info(f"Capturing {quality.upper()} screenshot ({width}x{height}) for: {url}")
        
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        try:
            await asyncio.wait_for(process.wait(), timeout=30)
        except asyncio.TimeoutError:
            process.kill()
            if temp_html_file and os.path.exists(temp_html_file):
                os.remove(temp_html_file)
            return JSONResponse(
                status_code=504,
                content={
                    "error": "Screenshot timeout (30 seconds)",
                    "api_owner": "@ISmartCoder",
                    "api_updates": "t.me/abirxdhackz"
                }
            )
        
        if temp_html_file and os.path.exists(temp_html_file):
            os.remove(temp_html_file)
        
        if not output_path.exists():
            return JSONResponse(
                status_code=500,
                content={
                    "error": "Failed to generate screenshot",
                    "api_owner": "@ISmartCoder",
                    "api_updates": "t.me/abirxdhackz"
                }
            )
        
        file_size = output_path.stat().st_size
        expiry = time.time() + FILE_EXPIRY
        
        STORE[fid] = {
            "path": str(output_path),
            "exp": expiry,
            "filename": filename
        }
        
        from main import get_actual_ip
        server_ip = get_actual_ip()
        port = int(os.getenv("PORT", 4434))
        file_url = f"http://{server_ip}:{port}/webss/file/{fid}"
        
        LOGGER.info(f"Screenshot created: {filename} ({file_size} bytes) - expires in {FILE_EXPIRY}s")
        
        return JSONResponse({
            "success": True,
            "url": url,
            "quality": quality.upper(),
            "resolution": f"{width}x{height}",
            "screenshot": file_url,
            "file_id": fid,
            "filename": filename,
            "size_bytes": file_size,
            "size_kb": round(file_size / 1024, 2),
            "cloudflare_bypass": bypass and CLOUDSCRAPER_AVAILABLE,
            "expires_in": f"{FILE_EXPIRY} seconds",
            "timestamp": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC"),
            "api_owner": "@ISmartCoder",
            "api_updates": "t.me/abirxdhackz"
        })
        
    except HTTPException:
        raise
    except Exception as e:
        LOGGER.error(f"Screenshot error: {str(e)}")
        return JSONResponse(
            status_code=500,
            content={
                "error": str(e),
                "api_owner": "@ISmartCoder",
                "api_updates": "t.me/abirxdhackz"
            }
        )

@router.get("/file/{fid}")
async def get_file(fid: str):
    cleanup_expired_files_sync()
    
    if fid not in STORE:
        raise HTTPException(status_code=404, detail="File not found")
    
    data = STORE[fid]
    
    if time.time() > data["exp"]:
        try:
            if os.path.exists(data["path"]):
                os.remove(data["path"])
                LOGGER.info(f"Deleted expired file on access: {os.path.basename(data['path'])}")
        except Exception:
            pass
        STORE.pop(fid, None)
        raise HTTPException(status_code=404, detail="File expired")
    
    if not os.path.exists(data["path"]):
        STORE.pop(fid, None)
        raise HTTPException(status_code=404, detail="File not found on disk")
    
    return FileResponse(
        data["path"],
        media_type="image/png",
        filename=data["filename"]
    )
