"""
=== CẤU HÌNH TRUNG TÂM ===
Tất cả config của server nằm ở đây.
Sửa file này để thay đổi cấu hình.
"""

import os

# ============================================
# KẾT NỐI
# ============================================

# URL của Local Agent (máy có phone)
AGENT_URL = os.getenv("AGENT_URL", "http://localhost:8000")

# Server host/port
SERVER_HOST = os.getenv("SERVER_HOST", "0.0.0.0")
SERVER_PORT = int(os.getenv("SERVER_PORT", "5000"))
BASE_URL = os.getenv("BASE_URL", f"http://localhost:{SERVER_PORT}")

# Tự động bắt đầu automation khi server khởi động
AUTO_START_ON_BOOT = os.getenv("AUTO_START_ON_BOOT", "1").strip().lower() in {
    "1", "true", "yes", "on"
}

# ============================================
# ĐƯỜNG DẪN
# ============================================

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

# Thư mục chứa ảnh template.
# Nếu truyền đường dẫn tương đối qua TEMPLATES_DIR, sẽ resolve theo PROJECT_ROOT.
_raw_templates_dir = os.getenv("TEMPLATES_DIR", "templates")
if os.path.isabs(_raw_templates_dir):
    TEMPLATES_DIR = _raw_templates_dir
else:
    TEMPLATES_DIR = os.path.abspath(os.path.join(PROJECT_ROOT, _raw_templates_dir))

# ============================================
# AUTOMATION MẶC ĐỊNH
# ============================================

AUTOMATION_DEFAULTS = {
    "max_count": 50,                    # Tổng số nhiệm vụ cần hoàn thành
    "break_interval": 25,               # Nghỉ sau mỗi N nhiệm vụ
    "break_duration_min": 2,            # Thời gian nghỉ tối thiểu (giây)
    "break_duration_max": 5,            # Thời gian nghỉ tối đa (giây)
    "captcha_timeout": 60,              # Thời gian chờ captcha tối đa (giây)
    "captcha_check_interval": 2,        # Khoảng kiểm tra captcha (giây)

    # Chờ nút xác nhận (nhiệm vụ thường)
    "button_wait_max": 15,
    "button_check_intervals": [1.0, 1.0, 1.0, 1.0, 2.0, 2.0, 3.0, 4.0],

    # Chờ nút xác nhận (nhiệm vụ dài / video)
    "long_task_button_wait_max": 180,
    "long_task_check_intervals": [
        *[2.0] * 15,   # 30s đầu: check mỗi 2s
        *[3.0] * 20,   # 60s tiếp: check mỗi 3s
        *[5.0] * 18,   # 90s cuối: check mỗi 5s
    ],

    # Delays
    "page_load_delay_min": 3.5,
    "page_load_delay_max": 4.5,
    "post_captcha_delay_min": 1.0,
    "post_captcha_delay_max": 2.0,
    "inter_action_delay_base": 0.5,
    "inter_action_delay_variance": 0.25,
    "retry_delay_base": 0.8,
    "retry_delay_variance": 0.3,

    # Error/back recovery
    "error_threshold": 0.55,
    "back_threshold": 0.50,
    "confirm_threshold": 0.7,
    "error_back_wait_seconds": 15,
}

# ============================================
# TEMPLATE MATCHING
# ============================================

# Scales mặc định cho template matching
DEFAULT_SCALES = [0.5, 0.6, 0.7, 0.8, 0.9, 1.0, 1.1, 1.2, 1.3, 1.4, 1.5]

# Scales tùy chỉnh cho từng template
TEMPLATE_SCALES = {
    "item_nv": [0.8, 0.9, 1.0, 1.1, 1.2],
    "btn_xacnhan": [0.7, 0.8, 0.9, 1.0, 1.1, 1.2],
    "captra": [0.5, 0.6, 0.7, 0.8, 0.9, 1.0, 1.1, 1.2, 1.3, 1.4, 1.5],
    "error": [0.6, 0.7, 0.8, 0.9, 1.0, 1.1, 1.2, 1.3, 1.4],
    "back": [0.6, 0.7, 0.8, 0.9, 1.0, 1.1, 1.2, 1.3, 1.4],
}

# Screenshot buffer TTL (giây) — tái sử dụng screenshot trong khoảng này
SCREENSHOT_BUFFER_TTL = 0.5

# ============================================
# LOG
# ============================================

LOG_BUFFER_SIZE = 1000      # Số dòng log giữ lại cho API
LOG_LEVEL = "INFO"          # DEBUG, INFO, WARNING, ERROR

# ============================================
# API ENDPOINTS (auto-generated từ BASE_URL)
# ============================================

API_ENDPOINTS = {
    "agent_health":       f"{BASE_URL}/api/agent/health",
    "agent_screenshot":   f"{BASE_URL}/api/agent/screenshot",
    "server_info":        f"{BASE_URL}/api/info",
    "automation_start":   f"{BASE_URL}/api/automation/start",
    "automation_stop":    f"{BASE_URL}/api/automation/stop",
    "automation_status":  f"{BASE_URL}/api/automation/status",
    "config_get":         f"{BASE_URL}/api/config",
    "config_update":      f"{BASE_URL}/api/config",
    "logs":               f"{BASE_URL}/api/logs",
    "dashboard":          f"{BASE_URL}/",
}


def print_api_info():
    """In ra thông tin API khi khởi động"""
    print("=" * 60)
    print("🚀 AUTO AVISO - SERVER")
    print("=" * 60)
    print(f"🌐 Base URL:    {BASE_URL}")
    print(f"📡 Agent URL:   {AGENT_URL}")
    print(f"▶️  Auto start: {'ON' if AUTO_START_ON_BOOT else 'OFF'}")
    print(f"📂 Templates:   {TEMPLATES_DIR}")
    print(f"📖 API Docs:    {BASE_URL}/docs")
    print(f"📊 Dashboard:   {BASE_URL}/")
    print("-" * 60)
    print("📡 API Endpoints:")
    print(f"   GET  {BASE_URL}/api/info                 → Thông tin server")
    print(f"   POST {BASE_URL}/api/automation/start      → Bắt đầu bot")
    print(f"   POST {BASE_URL}/api/automation/stop       → Dừng bot")
    print(f"   GET  {BASE_URL}/api/automation/status     → Trạng thái")
    print(f"   GET  {BASE_URL}/api/config                → Lấy config")
    print(f"   PUT  {BASE_URL}/api/config                → Cập nhật config")
    print(f"   GET  {BASE_URL}/api/logs                  → Log gần nhất")
    print(f"   GET  {BASE_URL}/api/agent/health          → Kiểm tra agent")
    print(f"   GET  {BASE_URL}/api/agent/screenshot      → Screenshot")
    print("=" * 60)
