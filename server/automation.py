"""
Automation Controller - Vòng lặp chính + thống kê

Tương đương test.py nhưng chạy trong background thread,
có thể start/stop qua API, thu thập log realtime.
"""

import time
import random
import threading
import logging
from collections import deque
from enum import Enum

try:
    from .engine import BotEngine
    from .config import AUTOMATION_DEFAULTS as DEFAULT_CONFIG, LOG_BUFFER_SIZE
except ImportError:
    # Hỗ trợ import khi chạy trực tiếp file main.py
    from engine import BotEngine
    from config import AUTOMATION_DEFAULTS as DEFAULT_CONFIG, LOG_BUFFER_SIZE

logger = logging.getLogger("automation")

# ============================================
# LOG BUFFER - Thu thập log cho API
# ============================================

class LogBuffer(logging.Handler):
    """Handler thu thập log vào deque để API đọc"""

    def __init__(self, maxlen=None):
        super().__init__()
        self.logs = deque(maxlen=maxlen or LOG_BUFFER_SIZE)
        self.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))

    def emit(self, record):
        self.logs.append({
            "time": self.format(record).split(" - ")[0],
            "level": record.levelname,
            "message": self.format(record),
        })

    def get_logs(self, n=100):
        return list(self.logs)[-n:]

    def clear(self):
        self.logs.clear()

# ============================================
# TRẠNG THÁI
# ============================================

class AutomationState(str, Enum):
    IDLE = "idle"           # Chưa chạy
    RUNNING = "running"     # Đang chạy
    PAUSED = "paused"       # Tạm dừng
    STOPPING = "stopping"   # Đang dừng
    ERROR = "error"         # Lỗi

# ============================================
# THỐNG KÊ
# ============================================

class Stats:
    def __init__(self):
        self.reset()

    def reset(self):
        self.success_count = 0
        self.fail_count = 0
        self.captcha_count = 0
        self.long_task_count = 0
        self.start_time = time.time()
        self.button_wait_times = []
        self.long_task_wait_times = []

    def record_success(self):
        self.success_count += 1

    def record_failure(self):
        self.fail_count += 1

    def record_captcha(self):
        self.captcha_count += 1

    def record_long_task(self):
        self.long_task_count += 1

    def record_button_wait(self, wait_time, is_long_task=False):
        self.button_wait_times.append(wait_time)
        if is_long_task:
            self.long_task_wait_times.append(wait_time)

    def get_elapsed(self):
        return time.time() - self.start_time

    def get_avg_time(self):
        if self.success_count == 0:
            return 0
        return self.get_elapsed() / self.success_count

    def get_rate(self):
        elapsed_min = self.get_elapsed() / 60
        return self.success_count / max(elapsed_min, 0.01)

    def get_success_rate(self):
        total = self.success_count + self.fail_count
        if total == 0:
            return 0
        return (self.success_count / total) * 100

    def to_dict(self):
        elapsed = self.get_elapsed()
        return {
            "success_count": self.success_count,
            "fail_count": self.fail_count,
            "captcha_count": self.captcha_count,
            "long_task_count": self.long_task_count,
            "elapsed_seconds": round(elapsed, 1),
            "avg_time_per_task": round(self.get_avg_time(), 1),
            "tasks_per_minute": round(self.get_rate(), 2),
            "success_rate": round(self.get_success_rate(), 1),
            "avg_button_wait": round(
                sum(self.button_wait_times) / max(len(self.button_wait_times), 1), 1
            ),
            "avg_long_task_wait": round(
                sum(self.long_task_wait_times) / max(len(self.long_task_wait_times), 1), 1
            ),
        }


# ============================================
# AUTOMATION CONTROLLER
# ============================================

class AutomationController:
    """
    Điều khiển vòng lặp tự động hóa.
    Chạy trong background thread, start/stop qua API.
    """

    def __init__(self, engine: BotEngine):
        self.engine = engine
        self.config = dict(DEFAULT_CONFIG)
        self.stats = Stats()
        self.log_buffer = LogBuffer(maxlen=LOG_BUFFER_SIZE)

        self.state = AutomationState.IDLE
        self._stop_event = threading.Event()
        self._thread = None
        self._lock = threading.Lock()

        self.current_task = 0
        self.error_message = ""

        # Gắn log buffer vào root logger
        root_logger = logging.getLogger()
        root_logger.addHandler(self.log_buffer)

    # ---- Điều khiển ----

    def start(self, config_overrides: dict = None):
        """Bắt đầu automation"""
        with self._lock:
            if self.state == AutomationState.RUNNING:
                return {"error": "Đang chạy rồi!"}

            if config_overrides:
                self.config.update(config_overrides)

            self.stats.reset()
            self.current_task = 0
            self.error_message = ""
            self._stop_event.clear()
            self.state = AutomationState.RUNNING

            self._thread = threading.Thread(target=self._run_loop, daemon=True)
            self._thread.start()

            logger.info("🚀 Automation đã bắt đầu!")
            return {"status": "started", "target": self.config["max_count"]}

    def stop(self):
        """Dừng automation"""
        with self._lock:
            if self.state != AutomationState.RUNNING:
                return {"error": "Không đang chạy"}

            self.state = AutomationState.STOPPING
            self._stop_event.set()

            logger.info("⛔ Đang dừng automation...")
            return {"status": "stopping"}

    def get_status(self) -> dict:
        """Lấy trạng thái hiện tại"""
        return {
            "state": self.state.value,
            "current_task": self.current_task,
            "target": self.config["max_count"],
            "stats": self.stats.to_dict(),
            "error": self.error_message,
        }

    def get_config(self) -> dict:
        return dict(self.config)

    def update_config(self, updates: dict) -> dict:
        """Cập nhật config (chỉ khi không đang chạy)"""
        if self.state == AutomationState.RUNNING:
            return {"error": "Không thể thay đổi config khi đang chạy"}
        self.config.update(updates)
        logger.info(f"⚙️  Config đã cập nhật: {updates}")
        return {"status": "updated", "config": self.config}

    def get_logs(self, n=100) -> list:
        return self.log_buffer.get_logs(n)

    # ---- Private: Vòng lặp chính ----

    def _should_stop(self) -> bool:
        return self._stop_event.is_set()

    def _smart_wait(self, base=0.3, variance=0.15):
        wait_time = max(0.1, base + random.uniform(-variance, variance))
        time.sleep(wait_time)
        return wait_time

    def _run_loop(self):
        """Main loop — chạy trong thread riêng"""
        max_count = self.config["max_count"]
        count = 0

        logger.info("=" * 60)
        logger.info("🚀 AUTO AVISO — SERVER MODE")
        logger.info("=" * 60)
        logger.info(f"🎯 Target: {max_count} tasks")
        logger.info("=" * 60)

        # Pre-load templates
        try:
            self.engine.preload_templates()
        except Exception as e:
            logger.warning(f"Không thể preload templates: {e}")

        time.sleep(random.uniform(0.5, 1.0))

        try:
            while count < max_count and not self._should_stop():
                logger.info(f"\n{'=' * 50}")
                logger.info(f"🔄 Task [{count + 1}/{max_count}]")
                logger.info(f"{'=' * 50}")

                self.current_task = count + 1

                # Nghỉ giải lao
                if count > 0 and count % self.config["break_interval"] == 0:
                    duration = random.uniform(
                        self.config["break_duration_min"],
                        self.config["break_duration_max"],
                    )
                    logger.info(f"⏸️  Nghỉ {duration:.1f}s...")
                    # Nghỉ nhưng vẫn check stop
                    for _ in range(int(duration * 10)):
                        if self._should_stop():
                            break
                        time.sleep(0.1)
                    self.engine.invalidate_screenshot()

                # Thực thi 1 task
                success = self._execute_single_task()

                if success:
                    count += 1
                    self.stats.record_success()
                    self._log_progress(count, max_count)
                else:
                    self.stats.record_failure()
                    logger.warning("❌ Task thất bại, thử lại...")
                    self._smart_wait(
                        self.config["retry_delay_base"],
                        self.config["retry_delay_variance"],
                    )
                    continue

                # Delay giữa các task
                self._smart_wait(
                    self.config["inter_action_delay_base"],
                    self.config["inter_action_delay_variance"],
                )

        except Exception as e:
            logger.error(f"❌ Fatal error: {e}")
            import traceback
            logger.error(traceback.format_exc())
            self.error_message = str(e)
            self.state = AutomationState.ERROR
            return

        # Hoàn thành
        self._log_final(max_count)
        self.state = AutomationState.IDLE

    def _execute_single_task(self) -> bool:
        """Thực hiện 1 nhiệm vụ — tương đương execute_single_task() trong test.py"""
        is_long_task = False

        # Kiểm tra item NV có hiện trên màn hình không
        if not self.engine.check_nv():
            self.engine.scroll_up(30)
            time.sleep(random.uniform(0.5, 1.0))
            if self._should_stop():
                return False

        # === Step 1: Chụp màn hình + Click task ===
        logger.info("📸 Step 1: Chụp màn hình và click task...")
        screen = self.engine.load_screenshot(use_cache=False, force_refresh=True)

        if not self.engine.click_task_title(screen_bgr=screen):
            logger.warning("⚠️  Không tìm thấy task")
            return False

        logger.info("✅ Đã click task")
        time.sleep(random.uniform(2.0, 2.5))
        if self._should_stop():
            return False

        # === Step 1.5: Kiểm tra loại nhiệm vụ ===
        logger.info("📸 Kiểm tra loại nhiệm vụ...")
        screen = self.engine.load_screenshot(use_cache=False, force_refresh=True)

        if self.engine.check_btn_start_video(screen_bgr=screen):
            is_long_task = True
            self.stats.record_long_task()

            logger.info("🎥 NHIỆM VỤ DÀI! Bắt đầu video...")
            time.sleep(random.uniform(0.4, 1.0))

            if not self.engine.click_start_video(screen_bgr=screen):
                logger.warning("⚠️  Không thể nhấn nút start video")
                return False

            logger.info("✅ Đã nhấn start video")
            time.sleep(random.uniform(1.0, 2.0))
            self.engine.back()
            logger.info("✅ Quay lại sau khi bắt đầu video")

            time.sleep(random.uniform(0.5, 1.0))
            screen = self.engine.load_screenshot(use_cache=False, force_refresh=True)

        if self._should_stop():
            return False

        # === Step 2: Kiểm tra nhiệm vụ đang chạy ===
        has_time_wait = self.engine.check_time_cho()

        if has_time_wait:
            logger.info("✅ Phát hiện thời gian chờ, chờ nút xác nhận...")
        else:
            logger.info("⏱️  Không có thời gian chờ, kiểm tra error...")

            page_load = random.uniform(
                self.config["page_load_delay_min"],
                self.config["page_load_delay_max"],
            )
            time.sleep(page_load)
            if self._should_stop():
                return False

            screen = self.engine.load_screenshot(use_cache=False, force_refresh=True)

            error_threshold = self.config.get("error_threshold", 0.55)
            back_threshold = self.config.get("back_threshold", 0.52)
            confirm_threshold = self.config.get("confirm_threshold", 0.7)
            wait_after_back = float(self.config.get("error_back_wait_seconds", 15))

            if self.engine.check_error_state(screen_bgr=screen, threshold=error_threshold):
                logger.warning("⚠️  Phát hiện màn hình lỗi, xử lý back...")

                if not self.engine.click_back_template_center(screen_bgr=screen, threshold=back_threshold):
                    logger.warning("⚠️  Có lỗi nhưng không click được vùng back")
                    return False

                logger.info(f"⏳ Đợi {wait_after_back:.1f}s sau khi click vùng back...")
                for _ in range(max(1, int(wait_after_back * 10))):
                    if self._should_stop():
                        return False
                    time.sleep(0.1)

                self.engine.back()
                logger.info("⬅️  Đã back về sau xử lý lỗi")

                time.sleep(random.uniform(0.8, 1.3))
                screen = self.engine.load_screenshot(use_cache=False, force_refresh=True)

                logger.info("🔍 Kiểm tra nút xác nhận sau xử lý lỗi...")
                if self.engine.check_btn_xn(screen_bgr=screen, threshold=confirm_threshold):
                    if not self.engine.click_confirm_button(screen_bgr=screen):
                        logger.warning("⚠️  Không click được nút xác nhận sau xử lý lỗi")
                        return False

                    logger.info("✅ Đã click nút xác nhận sau xử lý lỗi")
                    return True

                logger.warning("⚠️  Không thấy nút xác nhận sau xử lý lỗi")
                return False

            logger.info("⏱️  Không có error, kiểm tra captcha...")

            if self.engine.check_captra(screen, threshold=0.5):
                logger.warning("🔒 Phát hiện CAPTCHA!")
                if not self._handle_captcha():
                    return False
                logger.info("✅ Captcha đã giải, tiếp tục...")
            else:
                # Không có time_cho và không có captcha → thử lại
                logger.info("🔄 Không có captcha và không có thời gian chờ, thử lại...")
                time.sleep(random.uniform(0.5, 1.0))
                # Gọi lại bằng vòng lặp thay vì đệ quy (tránh stack overflow)
                return False

        if self._should_stop():
            return False

        # === Step 3: Chờ nút xác nhận ===
        task_label = "video DÀI" if is_long_task else "thường"
        logger.info(f"🔍 Step 3: Chờ nút xác nhận (NV {task_label})...")

        intervals = (
            self.config["long_task_check_intervals"]
            if is_long_task
            else self.config["button_check_intervals"]
        )

        btn_found, screen, wait_time = self._wait_for_button(intervals)

        if not btn_found:
            logger.warning(f"⏱️  Hết thời gian chờ nút (NV {task_label})")
            return False

        self.stats.record_button_wait(wait_time, is_long_task=is_long_task)
        time.sleep(random.uniform(0.05, 0.15))

        if self._should_stop():
            return False

        # === Step 4: Click nút xác nhận ===
        logger.info("👆 Step 4: Click nút xác nhận...")

        if not self.engine.click_confirm_button(screen_bgr=screen):
            logger.warning("⚠️  Không click được nút xác nhận")
            return False

        logger.info("✅ Đã click nút xác nhận!")
        return True

    # ---- Helpers ----

    def _handle_captcha(self) -> bool:
        """Xử lý captcha — phát cảnh báo và chờ user giải"""
        # Phát âm cảnh báo trên máy local
        self.engine.adb.start_alert()
        time.sleep(3)
        self.engine.adb.stop_alert()

        logger.info(f"⏳ Chờ captcha được giải (tối đa {self.config['captcha_timeout']}s)...")

        start = time.time()
        while time.time() - start < self.config["captcha_timeout"]:
            if self._should_stop():
                return False

            time.sleep(self.config["captcha_check_interval"])
            screen = self.engine.load_screenshot(force_refresh=True)

            if not self.engine.check_captra(screen, threshold=0.5):
                elapsed = time.time() - start
                logger.info(f"✅ Captcha đã giải sau {elapsed:.1f}s")
                self.stats.record_captcha()

                delay = random.uniform(
                    self.config["post_captcha_delay_min"],
                    self.config["post_captcha_delay_max"],
                )
                time.sleep(delay)
                return True

        logger.error("❌ Hết thời gian chờ captcha!")
        self.stats.record_captcha()
        return False

    def _wait_for_button(self, check_intervals) -> tuple:
        """Chờ nút xác nhận xuất hiện"""
        total_waited = 0

        for idx, interval in enumerate(check_intervals):
            if self._should_stop():
                return False, None, total_waited

            time.sleep(interval)
            total_waited += interval

            screen = self.engine.load_screenshot(force_refresh=True)

            if self.engine.check_btn_xn(screen_bgr=screen, threshold=0.7):
                logger.info(f"✅ Nút tìm thấy sau {total_waited:.1f}s!")
                return True, screen, total_waited

            if idx % 5 == 0:
                remaining = sum(check_intervals[idx + 1:])
                logger.debug(f"⏳ Chờ nút... ({total_waited:.0f}s, còn ~{remaining:.0f}s)")

        return False, None, total_waited

    def _log_progress(self, count, target):
        stats = self.stats
        logger.info(f"✅ Hoàn thành {count}/{target}")
        logger.info(
            f"📊 OK: {stats.success_count} | Fail: {stats.fail_count} "
            f"| Captcha: {stats.captcha_count} | Video: {stats.long_task_count}"
        )
        logger.info(f"⚡ Tốc độ: {stats.get_rate():.1f}/phút | TB: {stats.get_avg_time():.1f}s/task")

    def _log_final(self, target):
        stats = self.stats
        elapsed = stats.get_elapsed()

        logger.info(f"\n{'=' * 60}")
        logger.info("🎉 HOÀN THÀNH!")
        logger.info(f"{'=' * 60}")
        logger.info(f"✅ Thành công: {stats.success_count}/{target}")
        logger.info(f"❌ Thất bại: {stats.fail_count}")
        logger.info(f"🔒 Captcha: {stats.captcha_count}")
        logger.info(f"🎥 Video: {stats.long_task_count}")

        if elapsed > 0:
            minutes = elapsed / 60
            logger.info(f"⏱️  Tổng thời gian: {minutes:.1f} phút")

        if stats.success_count > 0:
            logger.info(f"⚡ Tốc độ: {stats.get_rate():.1f} task/phút")
            logger.info(f"🎯 Tỉ lệ: {stats.get_success_rate():.1f}%")
        logger.info(f"{'=' * 60}")
