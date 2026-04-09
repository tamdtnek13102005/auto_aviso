"""
=== AUTO AVISO - LOCAL AGENT ===
Chạy trên máy local có kết nối điện thoại qua ADB.
Cung cấp REST API proxy cho các lệnh ADB.

Chạy: python agent.py
Hoặc: uvicorn agent:app --host 0.0.0.0 --port 8000
"""

from fastapi import FastAPI, HTTPException
from fastapi.responses import Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import subprocess
import random
import time
import logging
import os
import sys

# Thêm thư mục cha vào path để import amthanh
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("local-agent")

ADB_BIN = os.getenv("ADB_BIN", "adb")
ADB_HEALTH_TIMEOUT = float(os.getenv("ADB_HEALTH_TIMEOUT", "12"))
ADB_AUTOSTART_SERVER = os.getenv("ADB_AUTOSTART_SERVER", "1").strip().lower() in {
    "1", "true", "yes", "on"
}

app = FastAPI(title="Auto Aviso - Local Agent", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================================
# Pydantic Models
# ============================================

class TapRequest(BaseModel):
    x: int
    y: int
    randomize: bool = True

class SwipeRequest(BaseModel):
    x1: int
    y1: int
    x2: int
    y2: int
    duration_ms: int = 200
    randomize: bool = True

class KeyEventRequest(BaseModel):
    keycode: str = "BACK"

# ============================================
# API Endpoints
# ============================================

@app.get("/api/health")
def health():
    """Kiểm tra agent có hoạt động + ADB có kết nối không"""
    try:
        if ADB_AUTOSTART_SERVER:
            # Khởi tạo adb daemon trước để giảm timeout giả khi lần gọi đầu.
            subprocess.run(
                [ADB_BIN, "start-server"],
                capture_output=True,
                text=True,
                timeout=8,
            )

        result = subprocess.run(
            [ADB_BIN, "devices"],
            capture_output=True,
            text=True,
            timeout=ADB_HEALTH_TIMEOUT,
        )

        lines = result.stdout.strip().split("\n")[1:]
        devices = [l for l in lines if l.strip() and "\tdevice" in l]
        unauthorized = [l for l in lines if l.strip() and "\tunauthorized" in l]
        offline = [l for l in lines if l.strip() and "\toffline" in l]

        return {
            "status": "ok",
            "adb_connected": len(devices) > 0,
            "device_count": len(devices),
            "unauthorized_count": len(unauthorized),
            "offline_count": len(offline),
        }
    except FileNotFoundError:
        return {
            "status": "ok",
            "adb_connected": False,
            "error": f"ADB binary not found: {ADB_BIN}",
        }
    except subprocess.TimeoutExpired:
        return {
            "status": "ok",
            "adb_connected": False,
            "error": f"Command '{ADB_BIN} devices' timed out after {ADB_HEALTH_TIMEOUT:.1f} seconds",
        }
    except Exception as e:
        return {"status": "ok", "adb_connected": False, "error": str(e)}


@app.get("/api/screenshot")
def screenshot():
    """Chụp ảnh màn hình qua ADB → trả về PNG bytes"""
    try:
        p = subprocess.run(
            [ADB_BIN, "exec-out", "screencap", "-p"],
            stdout=subprocess.PIPE,
            timeout=15,
        )
        if p.returncode != 0:
            raise HTTPException(status_code=500, detail="ADB screencap failed")
        return Response(content=p.stdout, media_type="image/png")
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=504, detail="ADB screencap timeout")


@app.post("/api/tap")
def tap(req: TapRequest):
    """Chạm vào tọa độ (x, y) trên màn hình"""
    x, y = req.x, req.y
    if req.randomize:
        x += random.randint(-5, 5)
        y += random.randint(-5, 5)

    time.sleep(random.uniform(0.01, 0.03))
    subprocess.run(
        [ADB_BIN, "shell", "input", "tap", str(int(x)), str(int(y))], timeout=10
    )
    logger.info(f"👆 Tap ({int(x)}, {int(y)})")
    return {"status": "ok", "x": int(x), "y": int(y)}


@app.post("/api/swipe")
def swipe(req: SwipeRequest):
    """Vuốt trên màn hình"""
    x1, y1, x2, y2 = req.x1, req.y1, req.x2, req.y2
    if req.randomize:
        x1 += random.randint(-3, 3)
        y1 += random.randint(-3, 3)
        x2 += random.randint(-3, 3)
        y2 += random.randint(-3, 3)

    subprocess.run(
        [
            ADB_BIN, "shell", "input", "swipe",
            str(int(x1)), str(int(y1)),
            str(int(x2)), str(int(y2)),
            str(int(req.duration_ms)),
        ],
        timeout=10,
    )
    logger.info(f"👉 Swipe ({int(x1)},{int(y1)}) -> ({int(x2)},{int(y2)})")
    return {"status": "ok"}


@app.post("/api/back")
def back():
    """Nhấn nút Back"""
    time.sleep(random.uniform(0.01, 0.03))
    subprocess.run([ADB_BIN, "shell", "input", "keyevent", "BACK"], timeout=10)
    logger.info("⬅️  Back")
    return {"status": "ok"}


@app.post("/api/keyevent")
def keyevent(req: KeyEventRequest):
    """Gửi key event tùy ý"""
    subprocess.run(
        [ADB_BIN, "shell", "input", "keyevent", req.keycode], timeout=10
    )
    logger.info(f"🔘 KeyEvent: {req.keycode}")
    return {"status": "ok"}


@app.get("/api/screen-size")
def screen_size():
    """Lấy kích thước màn hình"""
    try:
        result = subprocess.run(
            [ADB_BIN, "shell", "wm", "size"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode != 0:
            raise HTTPException(status_code=500, detail=result.stderr)

        output = result.stdout.strip()
        size_str = output.split(":")[-1].strip()
        width, height = map(int, size_str.split("x"))
        return {"width": width, "height": height}
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=504, detail="Timeout")


@app.post("/api/alert/start")
def alert_start():
    """Phát âm cảnh báo captcha (trên máy local)"""
    try:
        from amthanh import start_alert
        start_alert()
        return {"status": "ok", "message": "Alert started"}
    except ImportError:
        return {"status": "error", "message": "Module amthanh không khả dụng"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@app.post("/api/alert/stop")
def alert_stop():
    """Dừng phát âm cảnh báo"""
    try:
        from amthanh import stop_alert
        stop_alert()
        return {"status": "ok", "message": "Alert stopped"}
    except ImportError:
        return {"status": "error", "message": "Module amthanh không khả dụng"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


# ============================================
# Entry Point
# ============================================

if __name__ == "__main__":
    import uvicorn

    print("=" * 50)
    print("🚀 AUTO AVISO - LOCAL AGENT")
    print("=" * 50)
    print("📡 Server:  http://0.0.0.0:8000")
    print("📖 API Docs: http://localhost:8000/docs")
    print("=" * 50)
    uvicorn.run(app, host="0.0.0.0", port=8000)
