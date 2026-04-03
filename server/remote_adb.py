"""
Remote ADB Client - gọi Local Agent qua HTTP

Thay thế các lệnh subprocess ADB bằng HTTP requests
đến Local Agent server.
"""

import requests
import logging
import io
import time
import numpy as np
import cv2
from PIL import Image

logger = logging.getLogger("remote-adb")


class RemoteADB:
    """
    Client gọi Local Agent qua HTTP để thực thi lệnh ADB.

    Thay thế hoàn toàn các subprocess.run(["adb", ...]) calls
    bằng HTTP requests đến agent server.
    """

    def __init__(self, agent_url: str = "http://localhost:8000"):
        self.agent_url = agent_url.rstrip("/")
        self.session = requests.Session()
        self.session.timeout = 15
        self._screen_size_cache = None

    # ---- Kết nối ----

    def health_check(self) -> dict:
        """Kiểm tra agent có sống và ADB có kết nối không"""
        try:
            r = self.session.get(f"{self.agent_url}/api/health", timeout=5)
            return r.json()
        except requests.RequestException as e:
            return {"status": "error", "adb_connected": False, "error": str(e)}

    def is_connected(self) -> bool:
        """Kiểm tra nhanh agent có sống không"""
        try:
            r = self.session.get(f"{self.agent_url}/api/health", timeout=5)
            return r.status_code == 200
        except:
            return False

    # ---- Screenshot ----

    def screencap_bytes(self) -> bytes:
        """Chụp ảnh màn hình, trả về PNG bytes"""
        r = self.session.get(f"{self.agent_url}/api/screenshot", timeout=15)
        if r.status_code != 200:
            raise RuntimeError(f"Screenshot failed: {r.status_code} - {r.text}")
        return r.content

    def screencap_bgr(self) -> np.ndarray:
        """Chụp ảnh màn hình, trả về numpy array (BGR format cho OpenCV)"""
        data = self.screencap_bytes()
        img = Image.open(io.BytesIO(data))
        return cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)

    # ---- Hành động ----

    def tap(self, x: int, y: int, randomize: bool = True):
        """Chạm vào tọa độ (x, y)"""
        r = self.session.post(
            f"{self.agent_url}/api/tap",
            json={"x": int(x), "y": int(y), "randomize": randomize},
            timeout=10,
        )
        if r.status_code != 200:
            raise RuntimeError(f"Tap failed: {r.text}")
        logger.info(f"👆 Remote tap ({x}, {y})")

    def swipe(self, x1, y1, x2, y2, duration_ms=200, randomize=True):
        """Vuốt từ (x1,y1) đến (x2,y2)"""
        r = self.session.post(
            f"{self.agent_url}/api/swipe",
            json={
                "x1": int(x1), "y1": int(y1),
                "x2": int(x2), "y2": int(y2),
                "duration_ms": int(duration_ms),
                "randomize": randomize,
            },
            timeout=10,
        )
        if r.status_code != 200:
            raise RuntimeError(f"Swipe failed: {r.text}")
        logger.info(f"👉 Remote swipe ({x1},{y1}) -> ({x2},{y2})")

    def back(self):
        """Nhấn nút Back"""
        r = self.session.post(f"{self.agent_url}/api/back", timeout=10)
        if r.status_code != 200:
            raise RuntimeError(f"Back failed: {r.text}")
        logger.info("⬅️  Remote back")

    # ---- Thông tin ----

    def get_screen_size(self) -> tuple:
        """Lấy kích thước màn hình (có cache)"""
        if self._screen_size_cache is not None:
            return self._screen_size_cache

        r = self.session.get(f"{self.agent_url}/api/screen-size", timeout=5)
        data = r.json()
        if "error" in data:
            raise RuntimeError(f"Screen size failed: {data['error']}")

        self._screen_size_cache = (data["width"], data["height"])
        logger.info(f"📐 Screen size: {self._screen_size_cache}")
        return self._screen_size_cache

    def clear_screen_size_cache(self):
        """Xóa cache (khi đổi thiết bị hoặc xoay màn hình)"""
        self._screen_size_cache = None

    # ---- Âm thanh (chạy trên local) ----

    def start_alert(self):
        """Phát cảnh báo captcha trên máy local"""
        try:
            r = self.session.post(f"{self.agent_url}/api/alert/start", timeout=5)
            return r.json()
        except Exception as e:
            logger.warning(f"Alert start failed: {e}")

    def stop_alert(self):
        """Dừng cảnh báo trên máy local"""
        try:
            r = self.session.post(f"{self.agent_url}/api/alert/stop", timeout=5)
            return r.json()
        except Exception as e:
            logger.warning(f"Alert stop failed: {e}")
