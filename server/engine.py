"""
Bot Engine - Template matching + các hàm bot

Tương đương models.py nhưng dùng RemoteADB thay vì subprocess trực tiếp.
Tất cả template matching chạy trên server, ADB commands gửi qua HTTP.
"""

import cv2
import numpy as np
import os
import time
import random
import threading
import logging

try:
    from .remote_adb import RemoteADB
    from .config import DEFAULT_SCALES, TEMPLATE_SCALES, SCREENSHOT_BUFFER_TTL
except ImportError:
    # Hỗ trợ import khi chạy trực tiếp file main.py
    from remote_adb import RemoteADB
    from config import DEFAULT_SCALES, TEMPLATE_SCALES, SCREENSHOT_BUFFER_TTL

logger = logging.getLogger("engine")

# ============================================
# TEMPLATE CACHE
# ============================================

class TemplateCache:
    """Cache template đã resize sẵn theo nhiều tỉ lệ"""

    def __init__(self):
        self._cache = {}
        self._lock = threading.Lock()

    def get(self, path, scales=None):
        if scales is None:
            scales = DEFAULT_SCALES

        cache_key = (path, tuple(scales))

        with self._lock:
            if cache_key in self._cache:
                return self._cache[cache_key]

            template = cv2.imread(path)
            if template is None:
                logger.error(f"❌ Không đọc được template: {path}")
                return None

            scaled_templates = []
            temp_h, temp_w = template.shape[:2]

            for scale in scales:
                if scale == 1.0:
                    scaled_templates.append((template, scale, temp_w, temp_h))
                else:
                    new_w = int(temp_w * scale)
                    new_h = int(temp_h * scale)
                    resized = cv2.resize(template, (new_w, new_h), interpolation=cv2.INTER_LINEAR)
                    scaled_templates.append((resized, scale, new_w, new_h))

            self._cache[cache_key] = scaled_templates
            logger.info(f"✅ Cached template: {os.path.basename(path)} ({len(scales)} scales)")
            return scaled_templates

    def clear(self):
        with self._lock:
            self._cache.clear()

# ============================================
# SCREENSHOT BUFFER
# ============================================

class ScreenshotBuffer:
    """Buffer screenshot với TTL — tránh chụp lại quá nhiều qua mạng"""

    def __init__(self, adb: RemoteADB, ttl=0.5):
        self.adb = adb
        self._buffer = None
        self._timestamp = 0
        self._ttl = ttl
        self._lock = threading.Lock()

    def get(self, force_refresh=False):
        with self._lock:
            now = time.time()

            if not force_refresh and self._buffer is not None:
                if (now - self._timestamp) < self._ttl:
                    return self._buffer

            self._buffer = self.adb.screencap_bgr()
            self._timestamp = now
            return self._buffer

    def invalidate(self):
        with self._lock:
            self._timestamp = 0


# ============================================
# BOT ENGINE
# ============================================

class BotEngine:
    """
    Engine chính: template matching + điều khiển phone qua RemoteADB.
    Thay thế toàn bộ models.py.
    """

    def __init__(self, adb: RemoteADB, templates_dir: str = "./templates"):
        self.adb = adb
        self.templates_dir = templates_dir
        self._cache = TemplateCache()
        self._screen = ScreenshotBuffer(adb, ttl=SCREENSHOT_BUFFER_TTL)
        self._missing_template_groups = set()

    # ---- Đường dẫn template ----

    def _tpl(self, filename: str) -> str:
        return os.path.join(self.templates_dir, filename)

    # ---- Screenshot ----

    def load_screenshot(self, force_refresh=False, use_cache=True) -> np.ndarray:
        if not use_cache:
            return self.adb.screencap_bgr()
        return self._screen.get(force_refresh=force_refresh)

    def invalidate_screenshot(self):
        self._screen.invalidate()

    # ---- Template Matching đa tỉ lệ ----

    def match_template_multiscale(
        self,
        screen_bgr,
        template_path,
        threshold=0.6,
        scales=None,
        early_exit_conf=0.9,
        debug=False,
    ) -> dict:
        result = {
            "found": False,
            "confidence": 0.0,
            "location": None,
            "bbox": None,
            "scale": 1.0,
        }

        screen_h, screen_w = screen_bgr.shape[:2]

        scaled_templates = self._cache.get(template_path, scales=scales)
        if scaled_templates is None:
            return result

        best_val = 0
        best_match = None
        best_scale = 1.0

        for template, scale, temp_w, temp_h in scaled_templates:
            if temp_w > screen_w or temp_h > screen_h:
                continue

            match_result = cv2.matchTemplate(screen_bgr, template, cv2.TM_CCOEFF_NORMED)
            _, max_val, _, max_loc = cv2.minMaxLoc(match_result)

            if max_val > best_val:
                best_val = max_val
                best_match = (max_loc, temp_w, temp_h)
                best_scale = scale

                if max_val >= early_exit_conf:
                    break

        if best_val >= threshold and best_match:
            top_left, w, h = best_match
            center_x = top_left[0] + w // 2
            center_y = top_left[1] + h // 2

            result = {
                "found": True,
                "confidence": best_val,
                "location": (center_x, center_y),
                "bbox": (top_left[0], top_left[1], w, h),
                "scale": best_scale,
            }
            logger.info(
                f"✅ Tìm thấy: scale={best_scale:.2f}, conf={best_val:.4f}, center=({center_x},{center_y})"
            )

            if debug:
                debug_img = screen_bgr.copy()
                cv2.rectangle(debug_img, top_left, (top_left[0] + w, top_left[1] + h), (0, 255, 0), 3)
                debug_filename = f"debug_{os.path.basename(template_path).split('.')[0]}.png"
                cv2.imwrite(debug_filename, debug_img)
        else:
            if best_match:
                top_left, w, h = best_match
                center_x = top_left[0] + w // 2
                center_y = top_left[1] + h // 2
                result["confidence"] = best_val
                result["location"] = (center_x, center_y)
                result["bbox"] = (top_left[0], top_left[1], w, h)
                result["scale"] = best_scale
            logger.debug(f"❌ Không tìm thấy (best_conf={best_val:.4f} < threshold={threshold})")

        return result

    def _match_first_available_template(
        self,
        screen_bgr,
        filenames,
        threshold=0.6,
        scales=None,
        early_exit_conf=0.9,
        group_name=None,
    ) -> dict:
        """Thử match theo danh sách template, trả về kết quả đầu tiên tìm thấy."""
        existing_files = []
        best_candidate = None

        for filename in filenames:
            path = self._tpl(filename)
            if not os.path.exists(path):
                continue

            existing_files.append(filename)

            result = self.match_template_multiscale(
                screen_bgr=screen_bgr,
                template_path=path,
                threshold=threshold,
                scales=scales,
                early_exit_conf=early_exit_conf,
            )
            result["template_name"] = filename

            if result["found"]:
                return result

            if best_candidate is None or result["confidence"] > best_candidate["confidence"]:
                best_candidate = result

        # Chỉ cảnh báo thiếu template khi thực sự không có file nào trong danh sách.
        if not existing_files and group_name and group_name not in self._missing_template_groups:
            logger.warning(
                f"⚠️  Chưa có template cho nhóm '{group_name}'. "
                f"Thêm một trong: {', '.join(filenames)}"
            )
            self._missing_template_groups.add(group_name)

        if best_candidate is not None:
            return best_candidate

        return {
            "found": False,
            "confidence": 0.0,
            "location": None,
            "bbox": None,
            "scale": 1.0,
            "template_name": None,
        }

    # ---- CHECK functions (chỉ kiểm tra, không click) ----

    def check_nv(self, screen_bgr=None, threshold=0.7) -> bool:
        if screen_bgr is None:
            screen_bgr = self.load_screenshot(use_cache=True)

        scales = TEMPLATE_SCALES.get("item_nv", DEFAULT_SCALES)
        result = self.match_template_multiscale(
            screen_bgr, self._tpl("item_nv.jpg"),
            threshold=threshold, scales=scales,
        )
        if result["found"]:
            logger.info(f"Nhiệm vụ đã tìm thấy! (conf={result['confidence']:.3f})")
        return result["found"]

    def detect_btn_xn(self, screen_bgr=None, threshold=0.7) -> dict:
        """Phát hiện nút xác nhận, trả về thông tin bbox/confidence."""
        if screen_bgr is None:
            screen_bgr = self.load_screenshot(use_cache=True)

        scales = TEMPLATE_SCALES.get("btn_xacnhan", DEFAULT_SCALES)
        result = self.match_template_multiscale(
            screen_bgr, self._tpl("btn_xacnhan.jpg"),
            threshold=threshold, scales=scales,
        )
        result["template_name"] = "btn_xacnhan.jpg"
        return result

    def check_btn_xn(self, screen_bgr=None, threshold=0.7) -> bool:
        result = self.detect_btn_xn(screen_bgr=screen_bgr, threshold=threshold)
        if result["found"]:
            logger.info(f"✅ Nút xác nhận tìm thấy! (conf={result['confidence']:.3f})")
        return result["found"]

    def check_btn_start_video(self, screen_bgr=None, threshold=0.7) -> bool:
        if screen_bgr is None:
            screen_bgr = self.load_screenshot(use_cache=True)

        scales = TEMPLATE_SCALES.get("btn_xacnhan", DEFAULT_SCALES)
        result = self.match_template_multiscale(
            screen_bgr, self._tpl("start_video.png"),
            threshold=threshold, scales=scales,
        )
        if result["found"]:
            logger.info(f"✅ Nút start video tìm thấy! (conf={result['confidence']:.3f})")
        return result["found"]

    def detect_time_cho(self, screen_bgr=None, threshold=0.6) -> dict:
        """Phát hiện trạng thái thời gian chờ, trả về thông tin bbox/confidence."""
        if screen_bgr is None:
            screen_bgr = self.load_screenshot(use_cache=True)

        return self._match_first_available_template(
            screen_bgr=screen_bgr,
            filenames=["time_cho.jpg", "time_cho.png"],
            threshold=threshold,
            scales=TEMPLATE_SCALES.get("item_nv", DEFAULT_SCALES),
            early_exit_conf=0.9,
            group_name="time_cho",
        )

    def check_time_cho(self, screen_bgr=None, threshold=0.6) -> bool:
        result = self.detect_time_cho(screen_bgr=screen_bgr, threshold=threshold)
        if result["found"]:
            logger.info(f"✅ Xác nhận đang chạy nhiệm vụ! (conf={result['confidence']:.3f})")
        return result["found"]

    def check_captra(self, screen_bgr=None, threshold=0.5) -> bool:
        if screen_bgr is None:
            screen_bgr = self.load_screenshot(use_cache=True)

        scales = TEMPLATE_SCALES.get("captra", DEFAULT_SCALES)
        result = self.match_template_multiscale(
            screen_bgr, self._tpl("captra.jpg"),
            threshold=threshold, scales=scales,
            early_exit_conf=0.9,
        )
        if result["found"]:
            logger.info(f"✅ Captcha phát hiện! (conf={result['confidence']:.3f})")
        else:
            logger.info(f"❌ Không thấy captcha (best_conf={result['confidence']:.3f})")
        return result["found"]

    def detect_error_state(self, screen_bgr=None, threshold=0.62) -> dict:
        """Phát hiện màn hình lỗi/nhắc xem video, trả về thông tin bbox/confidence."""
        if screen_bgr is None:
            screen_bgr = self.load_screenshot(use_cache=True)

        candidates = [
            "error_watch.jpg",
            "error_watch.png",
            "error_video.jpg",
            "error_video.png",
            "error.jpg",
            "error.png",
        ]

        return self._match_first_available_template(
            screen_bgr=screen_bgr,
            filenames=candidates,
            threshold=threshold,
            scales=TEMPLATE_SCALES.get("error", DEFAULT_SCALES),
            early_exit_conf=0.9,
            group_name="error",
        )

    def check_error_state(self, screen_bgr=None, threshold=0.62) -> bool:
        """Kiểm tra màn hình lỗi/nhắc xem video."""
        result = self.detect_error_state(screen_bgr=screen_bgr, threshold=threshold)

        if result["found"]:
            logger.info(
                f"✅ Phát hiện màn hình lỗi ({result['template_name']}, conf={result['confidence']:.3f})"
            )
        return result["found"]

    def find_back_area(self, screen_bgr=None, threshold=0.6) -> dict:
        """Tìm vùng nút back dựa trên template ảnh."""
        if screen_bgr is None:
            screen_bgr = self.load_screenshot(use_cache=True)

        candidates = [
            "back.jpg",
            "back.png",
            "btn_back.jpg",
            "btn_back.png",
            "icon_back.jpg",
            "icon_back.png",
        ]

        result = self._match_first_available_template(
            screen_bgr=screen_bgr,
            filenames=candidates,
            threshold=threshold,
            scales=TEMPLATE_SCALES.get("back", DEFAULT_SCALES),
            early_exit_conf=0.9,
            group_name="back",
        )

        # Chặn false-positive kiểu thanh menu browser (rộng nhưng thấp),
        # thường bị match nhầm khi dùng template back không chuẩn.
        bbox = result.get("bbox")
        if result.get("found") and bbox:
            _x, _y, w, h = bbox
            if h > 0:
                aspect_ratio = float(w) / float(h)
                if aspect_ratio >= 2.2:
                    logger.warning(
                        "⚠️  Bỏ qua back candidate do tỷ lệ quá dẹt "
                        f"(w={w}, h={h}, ratio={aspect_ratio:.2f}) — có thể là menu browser"
                    )
                    result["found"] = False
                    result["rejected_reason"] = "aspect_ratio"

        return result

    def click_back_template_center(self, screen_bgr=None, threshold=0.6, max_attempts=2) -> bool:
        """Click vào tâm vùng ảnh back."""
        if screen_bgr is None:
            screen_bgr = self.load_screenshot(use_cache=True)

        for attempt in range(max_attempts):
            result = self.find_back_area(screen_bgr=screen_bgr, threshold=threshold)
            if result["found"]:
                click_x, click_y = result["location"]
                self.adb.tap(click_x, click_y, randomize=True)
                self.invalidate_screenshot()
                logger.info(
                    f"✅ Đã click vùng back ({result['template_name']}, conf={result['confidence']:.3f})"
                )
                return True

            if attempt < max_attempts - 1:
                time.sleep(random.uniform(0.1, 0.2))
                screen_bgr = self.load_screenshot(force_refresh=True)

        logger.warning("⚠️  Không tìm thấy vùng back để click")
        return False

    def detect_task_title(self, screen_bgr=None, threshold=0.6) -> dict:
        """Phát hiện vùng tiêu đề nhiệm vụ và trả về điểm click dự kiến."""
        if screen_bgr is None:
            screen_bgr = self.load_screenshot(use_cache=True)

        result = self._match_first_available_template(
            screen_bgr=screen_bgr,
            filenames=["item_nv.jpg", "item_nv_v2.jpg", "item_nv.png", "item_nv_v2.png"],
            threshold=threshold,
            scales=TEMPLATE_SCALES.get("item_nv", DEFAULT_SCALES),
            early_exit_conf=0.9,
            group_name="item_nv",
        )

        if result.get("location") and result.get("bbox"):
            center_x, _ = result["location"]
            bbox_x, bbox_y, _bbox_w, bbox_h = result["bbox"]
            offset_left = 110
            click_x = max(0, int(center_x - offset_left))
            click_y = int(bbox_y + (bbox_h * 0.35))
            result["click_location"] = (click_x, click_y)
            result["task_anchor"] = (int(center_x), int(bbox_y + (bbox_h / 2)))

        return result

    # ---- CLICK functions (tìm + click qua RemoteADB) ----

    def click_task_title(self, screen_bgr=None, max_attempts=2) -> bool:
        logger.info("🔍 Tìm tiêu đề nhiệm vụ...")
        time.sleep(random.uniform(0.05, 0.15))

        if screen_bgr is None:
            screen_bgr = self.load_screenshot(use_cache=True)

        for attempt in range(max_attempts):
            try:
                result = self.detect_task_title(screen_bgr=screen_bgr, threshold=0.6)

                if result["found"]:
                    click_x, click_y = result.get("click_location", result["location"])

                    logger.info(f"✅ Tiêu đề tìm thấy (conf={result['confidence']:.3f})")
                    self.adb.tap(click_x, click_y, randomize=True)
                    self.invalidate_screenshot()
                    return True

            except Exception as e:
                logger.error(f"Lỗi lần thử {attempt + 1}: {e}")

            if attempt < max_attempts - 1:
                time.sleep(random.uniform(0.1, 0.2))
                screen_bgr = self.load_screenshot(force_refresh=True)

        logger.error("❌ Không tìm thấy tiêu đề nhiệm vụ!")
        return False

    def click_confirm_button(self, screen_bgr=None, max_attempts=2) -> bool:
        logger.info("🔍 Tìm nút xác nhận...")
        time.sleep(random.uniform(0.05, 0.1))

        if screen_bgr is None:
            screen_bgr = self.load_screenshot(use_cache=True)

        for attempt in range(max_attempts):
            try:
                scales = TEMPLATE_SCALES.get("btn_xacnhan", DEFAULT_SCALES)
                result = self.match_template_multiscale(
                    screen_bgr, self._tpl("btn_xacnhan.jpg"),
                    threshold=0.65, scales=scales,
                )

                if result["found"]:
                    click_x, click_y = result["location"]
                    logger.info(f"✅ Nút xác nhận tìm thấy (conf={result['confidence']:.3f})")
                    self.adb.tap(click_x, click_y, randomize=True)
                    self.invalidate_screenshot()
                    return True

            except Exception as e:
                logger.error(f"Lỗi lần thử {attempt + 1}: {e}")

            if attempt < max_attempts - 1:
                time.sleep(random.uniform(0.1, 0.15))
                screen_bgr = self.load_screenshot(force_refresh=True)

        logger.error("❌ Không tìm thấy nút xác nhận!")
        return False

    def click_start_video(self, screen_bgr=None, max_attempts=2) -> bool:
        logger.info("🔍 Tìm nút start video...")
        time.sleep(random.uniform(0.05, 0.1))

        if screen_bgr is None:
            screen_bgr = self.load_screenshot(use_cache=True)

        for attempt in range(max_attempts):
            try:
                scales = TEMPLATE_SCALES.get("btn_xacnhan", DEFAULT_SCALES)
                result = self.match_template_multiscale(
                    screen_bgr, self._tpl("start_video.png"),
                    threshold=0.65, scales=scales,
                )

                if result["found"]:
                    click_x, click_y = result["location"]
                    logger.info(f"✅ Nút start video tìm thấy (conf={result['confidence']:.3f})")
                    self.adb.tap(click_x, click_y, randomize=True)
                    self.invalidate_screenshot()
                    return True

            except Exception as e:
                logger.error(f"Lỗi lần thử {attempt + 1}: {e}")

            if attempt < max_attempts - 1:
                time.sleep(random.uniform(0.1, 0.15))
                screen_bgr = self.load_screenshot(force_refresh=True)

        logger.error("❌ Không tìm thấy nút start video!")
        return False

    # ---- Điều hướng ----

    def back(self):
        self.adb.back()
        self.invalidate_screenshot()

    def scroll_up(self, scroll_percent=None):
        """Kéo lên — giữ nguyên logic từ models.py gốc"""
        width, height = self.adb.get_screen_size()

        x = random.randint(int(width * 0.4), int(width * 0.6))
        start_y = random.randint(int(height * 0.6), int(height * 0.7))

        if scroll_percent is not None:
            scroll_distance = (scroll_percent / 100) * height
            if scroll_percent <= 30:
                duration = random.randint(200, 300)
                pause = random.uniform(1.0, 2.0)
            elif scroll_percent <= 50:
                duration = random.randint(300, 500)
                pause = random.uniform(0.5, 1.5)
            else:
                duration = random.randint(400, 600)
                pause = random.uniform(0.3, 0.8)
        else:
            scroll_types = ["short", "medium", "long"]
            scroll_type = random.choices(scroll_types, weights=[0.3, 0.5, 0.2])[0]

            if scroll_type == "short":
                scroll_distance = random.uniform(0.2, 0.3) * height
                duration = random.randint(200, 300)
                pause = random.uniform(1.0, 2.0)
            elif scroll_type == "medium":
                scroll_distance = random.uniform(0.4, 0.6) * height
                duration = random.randint(300, 500)
                pause = random.uniform(0.5, 1.5)
            else:
                scroll_distance = random.uniform(0.6, 0.8) * height
                duration = random.randint(400, 600)
                pause = random.uniform(0.3, 0.8)

        end_y = int(start_y - scroll_distance)

        self.adb.swipe(x, start_y, x, end_y, duration, randomize=True)
        self.invalidate_screenshot()
        time.sleep(pause)
        logger.info(f"📱 Kéo lên ({scroll_percent or 'random'}%)")

    # ---- Khởi tạo ----

    def preload_templates(self):
        """Pre-load tất cả templates vào cache"""
        templates = {
            "item_nv": ("item_nv.jpg", TEMPLATE_SCALES.get("item_nv")),
            "btn_xacnhan": ("btn_xacnhan.jpg", TEMPLATE_SCALES.get("btn_xacnhan")),
            "captra": ("captra.jpg", TEMPLATE_SCALES.get("captra")),
            "start_video": ("start_video.png", TEMPLATE_SCALES.get("btn_xacnhan")),
            "time_cho": ("time_cho.jpg", TEMPLATE_SCALES.get("item_nv")),
        }

        optional_template_groups = {
            "error": [
                "error_watch.jpg",
                "error_watch.png",
                "error_video.jpg",
                "error_video.png",
                "error.jpg",
                "error.png",
            ],
            "back": [
                "back.jpg",
                "back.png",
                "btn_back.jpg",
                "btn_back.png",
                "icon_back.jpg",
                "icon_back.png",
            ],
        }

        logger.info("🔄 Pre-loading templates...")
        for name, (filename, scales) in templates.items():
            path = self._tpl(filename)
            if os.path.exists(path):
                self._cache.get(path, scales=scales)
            else:
                logger.warning(f"⚠️  Template không tồn tại: {path}")

        for group_name, filenames in optional_template_groups.items():
            preloaded = False
            for filename in filenames:
                path = self._tpl(filename)
                if not os.path.exists(path):
                    continue

                self._cache.get(path, scales=TEMPLATE_SCALES.get(group_name, DEFAULT_SCALES))
                logger.info(f"✅ Optional template {group_name}: {filename}")
                preloaded = True
                break

            if not preloaded:
                logger.warning(
                    f"⚠️  Chưa có template nhóm '{group_name}': {', '.join(filenames)}"
                )

        logger.info("✅ Đã nạp trước tất cả templates!")
