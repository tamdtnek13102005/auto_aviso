"""
=== AUTO AVISO - SERVER ===
Server chính: API điều khiển + Dashboard

Chạy: python -m server.main
Hoặc: uvicorn server.main:app --host 0.0.0.0 --port 5000 --reload
"""

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Optional
import logging
import os

from .remote_adb import RemoteADB
from .engine import BotEngine
from .automation import AutomationController
from .config import BASE_URL, AGENT_URL, TEMPLATES_DIR, API_ENDPOINTS, AUTO_START_ON_BOOT

# ============================================
# LOGGING
# ============================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("server")

# ============================================
# KHỞI TẠO
# ============================================

# URL của Local Agent — thay đổi khi deploy
AGENT_URL = os.getenv("AGENT_URL", "http://localhost:8000")
TEMPLATES_DIR = os.getenv("TEMPLATES_DIR", "./templates")

# Tạo các instances
adb = RemoteADB(agent_url=AGENT_URL)
engine = BotEngine(adb=adb, templates_dir=TEMPLATES_DIR)
controller = AutomationController(engine=engine)

# ============================================
# FASTAPI APP
# ============================================

app = FastAPI(
    title="Auto Aviso - Server",
    version="1.0.0",
    description="Server điều khiển tự động hóa nhiệm vụ Aviso",
)


@app.on_event("startup")
def startup_auto_run():
    """Tự động bắt đầu automation khi server khởi động."""
    if not AUTO_START_ON_BOOT:
        logger.info("Auto-start đang tắt (AUTO_START_ON_BOOT=0)")
        return

    try:
        result = controller.start()
        if result.get("status") == "started":
            logger.info("✅ Auto-start: automation đã bắt đầu")
        else:
            logger.warning(f"⚠️  Auto-start không bắt đầu được: {result}")
    except Exception as e:
        logger.error(f"❌ Auto-start gặp lỗi: {e}")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================================
# Pydantic Models
# ============================================

class StartRequest(BaseModel):
    max_count: Optional[int] = None
    break_interval: Optional[int] = None

class ConfigUpdate(BaseModel):
    max_count: Optional[int] = None
    break_interval: Optional[int] = None
    break_duration_min: Optional[float] = None
    break_duration_max: Optional[float] = None
    captcha_timeout: Optional[int] = None
    captcha_check_interval: Optional[int] = None
    page_load_delay_min: Optional[float] = None
    page_load_delay_max: Optional[float] = None

# ============================================
# API ROUTES
# ============================================

# --- Server Info ---

@app.get("/api/info")
def server_info():
    """Trả về base URL và danh sách tất cả API endpoints"""
    return {
        "base_url": BASE_URL,
        "agent_url": AGENT_URL,
        "templates_dir": TEMPLATES_DIR,
        "endpoints": API_ENDPOINTS,
    }


# --- Agent ---

@app.get("/api/agent/health")
def agent_health():
    """Kiểm tra Local Agent có kết nối không"""
    return adb.health_check()


@app.get("/api/agent/screenshot")
def agent_screenshot():
    """Proxy: lấy screenshot từ Local Agent"""
    try:
        data = adb.screencap_bytes()
        return Response(content=data, media_type="image/png")
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Agent error: {e}")


# --- Automation ---

@app.post("/api/automation/start")
def automation_start(req: StartRequest = None):
    """Bắt đầu tự động hóa"""
    overrides = {}
    if req:
        if req.max_count is not None:
            overrides["max_count"] = req.max_count
        if req.break_interval is not None:
            overrides["break_interval"] = req.break_interval

    result = controller.start(config_overrides=overrides if overrides else None)
    return result


@app.post("/api/automation/stop")
def automation_stop():
    """Dừng tự động hóa"""
    return controller.stop()


@app.get("/api/automation/status")
def automation_status():
    """Lấy trạng thái hiện tại"""
    return controller.get_status()


# --- Config ---

@app.get("/api/config")
def get_config():
    """Lấy cấu hình hiện tại"""
    return controller.get_config()


@app.put("/api/config")
def update_config(updates: ConfigUpdate):
    """Cập nhật cấu hình"""
    update_dict = {k: v for k, v in updates.dict().items() if v is not None}
    return controller.update_config(update_dict)


# --- Logs ---

@app.get("/api/logs")
def get_logs(n: int = Query(default=100, ge=1, le=1000)):
    """Lấy log gần nhất"""
    return {"logs": controller.get_logs(n)}


# ============================================
# DASHBOARD (HTML inline)
# ============================================

@app.get("/", response_class=HTMLResponse)
def dashboard():
    """Dashboard điều khiển"""
    return DASHBOARD_HTML


# ============================================
# DASHBOARD HTML
# ============================================

DASHBOARD_HTML = """
<!DOCTYPE html>
<html lang="vi">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Auto Aviso — Dashboard</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg-primary: #0f0f23;
            --bg-secondary: #1a1a2e;
            --bg-card: #16213e;
            --bg-card-hover: #1a2744;
            --accent-blue: #4361ee;
            --accent-cyan: #4cc9f0;
            --accent-green: #06d6a0;
            --accent-red: #ef476f;
            --accent-orange: #ff9f1c;
            --accent-purple: #7209b7;
            --text-primary: #e8e8f0;
            --text-secondary: #8b8ba7;
            --text-muted: #555577;
            --border: #2a2a4a;
            --shadow: 0 4px 24px rgba(0, 0, 0, 0.4);
            --radius: 14px;
        }

        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }

        body {
            font-family: 'Inter', sans-serif;
            background: var(--bg-primary);
            color: var(--text-primary);
            min-height: 100vh;
        }

        /* Header */
        .header {
            background: linear-gradient(135deg, var(--bg-secondary), var(--bg-card));
            border-bottom: 1px solid var(--border);
            padding: 20px 32px;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }

        .header h1 {
            font-size: 1.5rem;
            font-weight: 700;
            background: linear-gradient(135deg, var(--accent-cyan), var(--accent-blue));
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }

        .header-status {
            display: flex;
            align-items: center;
            gap: 12px;
        }

        .status-dot {
            width: 10px;
            height: 10px;
            border-radius: 50%;
            animation: pulse 2s infinite;
        }

        .status-dot.connected { background: var(--accent-green); }
        .status-dot.disconnected { background: var(--accent-red); }
        .status-dot.running { background: var(--accent-cyan); }

        @keyframes pulse {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.4; }
        }

        /* Main layout */
        .main {
            max-width: 1400px;
            margin: 0 auto;
            padding: 24px 32px;
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 24px;
        }

        .full-width {
            grid-column: 1 / -1;
        }

        /* Cards */
        .card {
            background: var(--bg-card);
            border: 1px solid var(--border);
            border-radius: var(--radius);
            padding: 24px;
            box-shadow: var(--shadow);
            transition: border-color 0.3s;
        }

        .card:hover {
            border-color: rgba(67, 97, 238, 0.3);
        }

        .card-title {
            font-size: 0.85rem;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            color: var(--text-secondary);
            margin-bottom: 16px;
            display: flex;
            align-items: center;
            gap: 8px;
        }

        /* Stat grid */
        .stat-grid {
            display: grid;
            grid-template-columns: repeat(4, 1fr);
            gap: 16px;
        }

        .stat-item {
            text-align: center;
            padding: 16px 12px;
            background: rgba(255,255,255,0.02);
            border-radius: 10px;
            border: 1px solid rgba(255,255,255,0.04);
        }

        .stat-value {
            font-size: 2rem;
            font-weight: 700;
            line-height: 1.2;
        }

        .stat-value.green { color: var(--accent-green); }
        .stat-value.red { color: var(--accent-red); }
        .stat-value.blue { color: var(--accent-cyan); }
        .stat-value.orange { color: var(--accent-orange); }
        .stat-value.purple { color: var(--accent-purple); }

        .stat-label {
            font-size: 0.75rem;
            color: var(--text-secondary);
            margin-top: 6px;
            text-transform: uppercase;
            letter-spacing: 0.05em;
        }

        /* Buttons */
        .btn-group {
            display: flex;
            gap: 12px;
            margin-bottom: 20px;
        }

        .btn {
            padding: 12px 28px;
            border: none;
            border-radius: 10px;
            font-family: 'Inter', sans-serif;
            font-size: 0.9rem;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.25s;
            display: flex;
            align-items: center;
            gap: 8px;
        }

        .btn:active { transform: scale(0.97); }

        .btn-start {
            background: linear-gradient(135deg, var(--accent-green), #05b88a);
            color: #000;
        }

        .btn-start:hover { box-shadow: 0 0 20px rgba(6, 214, 160, 0.35); }

        .btn-stop {
            background: linear-gradient(135deg, var(--accent-red), #d63c5e);
            color: #fff;
        }

        .btn-stop:hover { box-shadow: 0 0 20px rgba(239, 71, 111, 0.35); }

        .btn-secondary {
            background: rgba(255, 255, 255, 0.06);
            color: var(--text-primary);
            border: 1px solid var(--border);
        }

        .btn-secondary:hover { background: rgba(255, 255, 255, 0.1); }

        .btn:disabled {
            opacity: 0.4;
            cursor: not-allowed;
        }

        /* Progress bar */
        .progress-wrap {
            margin: 16px 0;
        }

        .progress-bar {
            height: 8px;
            background: rgba(255, 255, 255, 0.06);
            border-radius: 4px;
            overflow: hidden;
        }

        .progress-fill {
            height: 100%;
            background: linear-gradient(90deg, var(--accent-blue), var(--accent-cyan));
            border-radius: 4px;
            transition: width 0.5s ease;
        }

        .progress-text {
            display: flex;
            justify-content: space-between;
            margin-top: 8px;
            font-size: 0.8rem;
            color: var(--text-secondary);
        }

        /* State indicator */
        .state-badge {
            display: inline-flex;
            align-items: center;
            gap: 6px;
            padding: 6px 14px;
            border-radius: 20px;
            font-size: 0.8rem;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.05em;
        }

        .state-idle { background: rgba(139,139,167,0.15); color: var(--text-secondary); }
        .state-running { background: rgba(76,201,240,0.15); color: var(--accent-cyan); }
        .state-stopping { background: rgba(255,159,28,0.15); color: var(--accent-orange); }
        .state-error { background: rgba(239,71,111,0.15); color: var(--accent-red); }

        /* Log panel */
        .log-container {
            background: #0a0a18;
            border-radius: 10px;
            padding: 16px;
            height: 350px;
            overflow-y: auto;
            font-family: 'JetBrains Mono', 'Fira Code', monospace;
            font-size: 0.78rem;
            line-height: 1.6;
            border: 1px solid rgba(255,255,255,0.04);
        }

        .log-container::-webkit-scrollbar {
            width: 6px;
        }

        .log-container::-webkit-scrollbar-track {
            background: transparent;
        }

        .log-container::-webkit-scrollbar-thumb {
            background: var(--border);
            border-radius: 3px;
        }

        .log-line {
            padding: 2px 0;
            word-break: break-all;
        }

        .log-line.INFO { color: var(--text-secondary); }
        .log-line.WARNING { color: var(--accent-orange); }
        .log-line.ERROR { color: var(--accent-red); }
        .log-line.DEBUG { color: var(--text-muted); }

        /* Config form */
        .config-grid {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 12px;
        }

        .config-item {
            display: flex;
            flex-direction: column;
            gap: 4px;
        }

        .config-item label {
            font-size: 0.75rem;
            color: var(--text-secondary);
        }

        .config-item input {
            background: rgba(255,255,255,0.04);
            border: 1px solid var(--border);
            border-radius: 8px;
            padding: 8px 12px;
            color: var(--text-primary);
            font-family: 'Inter', sans-serif;
            font-size: 0.85rem;
        }

        .config-item input:focus {
            outline: none;
            border-color: var(--accent-blue);
        }

        /* Screenshot */
        .screenshot-container {
            text-align: center;
        }

        .screenshot-container img {
            max-height: 400px;
            border-radius: 10px;
            border: 1px solid var(--border);
        }

        /* Responsive */
        @media (max-width: 768px) {
            .main {
                grid-template-columns: 1fr;
                padding: 16px;
            }
            .stat-grid {
                grid-template-columns: repeat(2, 1fr);
            }
        }
    </style>
</head>
<body>
    <!-- Header -->
    <div class="header">
        <h1>🤖 Auto Aviso Dashboard</h1>
        <div class="header-status">
            <div class="status-dot" id="agentDot"></div>
            <span id="agentStatus" style="font-size:0.85rem; color:var(--text-secondary)">Đang kiểm tra...</span>
        </div>
    </div>

    <div class="main">
        <!-- Controls -->
        <div class="card full-width">
            <div class="card-title">⚡ Điều khiển</div>
            <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 16px;">
                <div class="btn-group">
                    <button class="btn btn-start" id="btnStart" onclick="startAutomation()">▶ Bắt đầu</button>
                    <button class="btn btn-stop" id="btnStop" onclick="stopAutomation()" disabled>⏹ Dừng</button>
                    <button class="btn btn-secondary" onclick="refreshScreenshot()">📷 Screenshot</button>
                </div>
                <div>
                    <span class="state-badge state-idle" id="stateBadge">IDLE</span>
                </div>
            </div>

            <!-- Progress -->
            <div class="progress-wrap" id="progressWrap" style="display:none;">
                <div class="progress-bar">
                    <div class="progress-fill" id="progressFill" style="width: 0%"></div>
                </div>
                <div class="progress-text">
                    <span id="progressText">0 / 50</span>
                    <span id="progressPercent">0%</span>
                </div>
            </div>
        </div>

        <!-- Stats -->
        <div class="card full-width">
            <div class="card-title">📊 Thống kê</div>
            <div class="stat-grid">
                <div class="stat-item">
                    <div class="stat-value green" id="statSuccess">0</div>
                    <div class="stat-label">Thành công</div>
                </div>
                <div class="stat-item">
                    <div class="stat-value red" id="statFail">0</div>
                    <div class="stat-label">Thất bại</div>
                </div>
                <div class="stat-item">
                    <div class="stat-value orange" id="statCaptcha">0</div>
                    <div class="stat-label">Captcha</div>
                </div>
                <div class="stat-item">
                    <div class="stat-value purple" id="statVideo">0</div>
                    <div class="stat-label">Video (dài)</div>
                </div>
                <div class="stat-item">
                    <div class="stat-value blue" id="statRate">0</div>
                    <div class="stat-label">Task/phút</div>
                </div>
                <div class="stat-item">
                    <div class="stat-value blue" id="statAvg">0s</div>
                    <div class="stat-label">TB/task</div>
                </div>
                <div class="stat-item">
                    <div class="stat-value green" id="statSuccessRate">0%</div>
                    <div class="stat-label">Tỉ lệ</div>
                </div>
                <div class="stat-item">
                    <div class="stat-value blue" id="statElapsed">0s</div>
                    <div class="stat-label">Thời gian</div>
                </div>
            </div>
        </div>

        <!-- Config -->
        <div class="card">
            <div class="card-title">⚙️ Cấu hình</div>
            <div class="config-grid">
                <div class="config-item">
                    <label>Số nhiệm vụ</label>
                    <input type="number" id="cfgMaxCount" value="50" min="1">
                </div>
                <div class="config-item">
                    <label>Nghỉ sau (NV)</label>
                    <input type="number" id="cfgBreakInterval" value="25" min="1">
                </div>
                <div class="config-item">
                    <label>Captcha timeout (s)</label>
                    <input type="number" id="cfgCaptchaTimeout" value="60" min="10">
                </div>
                <div class="config-item">
                    <label>Agent URL</label>
                    <input type="text" id="cfgAgentUrl" value="" readonly
                           style="color:var(--text-muted); cursor:not-allowed;">
                </div>
            </div>
            <div style="margin-top: 16px;">
                <button class="btn btn-secondary" onclick="saveConfig()">💾 Lưu Config</button>
            </div>
        </div>

        <!-- Screenshot -->
        <div class="card">
            <div class="card-title">📱 Màn hình</div>
            <div class="screenshot-container">
                <img id="screenshotImg" src="" alt="Chưa có screenshot"
                     style="max-width:100%; display:none;">
                <div id="screenshotPlaceholder" style="color:var(--text-muted); padding:60px 0;">
                    Nhấn 📷 Screenshot để xem
                </div>
            </div>
        </div>

        <!-- Logs -->
        <div class="card full-width">
            <div class="card-title">
                📋 Log
                <button class="btn btn-secondary" style="margin-left:auto; padding:6px 14px; font-size:0.75rem;"
                        onclick="clearLogs()">Xóa</button>
            </div>
            <div class="log-container" id="logContainer"></div>
        </div>
    </div>

    <script>
        const API_BASE = window.location.origin;
        let refreshInterval = null;
        let logAutoScroll = true;

        // ---- Auto-refresh ----
        function startPolling() {
            refreshInterval = setInterval(() => {
                fetchStatus();
                fetchLogs();
            }, 2000);

            // Agent health check mỗi 10s
            checkAgent();
            setInterval(checkAgent, 10000);
        }

        // ---- Agent Health ----
        async function checkAgent() {
            try {
                const res = await fetch(`${API_BASE}/api/agent/health`);
                const data = await res.json();
                const dot = document.getElementById('agentDot');
                const text = document.getElementById('agentStatus');

                if (data.adb_connected) {
                    dot.className = 'status-dot connected';
                    text.textContent = `Agent OK (${data.device_count} device)`;
                } else {
                    dot.className = 'status-dot disconnected';
                    text.textContent = 'Agent: không kết nối ADB';
                }
            } catch {
                document.getElementById('agentDot').className = 'status-dot disconnected';
                document.getElementById('agentStatus').textContent = 'Agent: offline';
            }
        }

        // ---- Status ----
        async function fetchStatus() {
            try {
                const res = await fetch(`${API_BASE}/api/automation/status`);
                const data = await res.json();
                updateUI(data);
            } catch (e) {
                console.error('Status error:', e);
            }
        }

        function updateUI(data) {
            const state = data.state;
            const stats = data.stats;

            // State badge
            const badge = document.getElementById('stateBadge');
            badge.textContent = state.toUpperCase();
            badge.className = `state-badge state-${state}`;

            // Buttons
            document.getElementById('btnStart').disabled = (state === 'running' || state === 'stopping');
            document.getElementById('btnStop').disabled = (state !== 'running');

            // Progress
            const progressWrap = document.getElementById('progressWrap');
            if (state === 'running' || state === 'stopping') {
                progressWrap.style.display = 'block';
                const pct = data.target > 0 ? (data.current_task / data.target * 100) : 0;
                document.getElementById('progressFill').style.width = pct + '%';
                document.getElementById('progressText').textContent = `${data.current_task} / ${data.target}`;
                document.getElementById('progressPercent').textContent = pct.toFixed(0) + '%';
            } else {
                progressWrap.style.display = 'none';
            }

            // Stats
            document.getElementById('statSuccess').textContent = stats.success_count;
            document.getElementById('statFail').textContent = stats.fail_count;
            document.getElementById('statCaptcha').textContent = stats.captcha_count;
            document.getElementById('statVideo').textContent = stats.long_task_count;
            document.getElementById('statRate').textContent = stats.tasks_per_minute.toFixed(1);
            document.getElementById('statAvg').textContent = stats.avg_time_per_task.toFixed(1) + 's';
            document.getElementById('statSuccessRate').textContent = stats.success_rate.toFixed(0) + '%';
            document.getElementById('statElapsed').textContent = formatTime(stats.elapsed_seconds);
        }

        function formatTime(sec) {
            if (sec < 60) return sec.toFixed(0) + 's';
            if (sec < 3600) return (sec / 60).toFixed(1) + 'm';
            return (sec / 3600).toFixed(1) + 'h';
        }

        // ---- Actions ----
        async function startAutomation() {
            const maxCount = parseInt(document.getElementById('cfgMaxCount').value) || 50;
            const breakInterval = parseInt(document.getElementById('cfgBreakInterval').value) || 25;

            try {
                const res = await fetch(`${API_BASE}/api/automation/start`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ max_count: maxCount, break_interval: breakInterval }),
                });
                const data = await res.json();
                if (data.error) {
                    alert('Lỗi: ' + data.error);
                }
                fetchStatus();
            } catch (e) {
                alert('Không thể kết nối server');
            }
        }

        async function stopAutomation() {
            try {
                await fetch(`${API_BASE}/api/automation/stop`, { method: 'POST' });
                fetchStatus();
            } catch (e) {
                alert('Không thể kết nối server');
            }
        }

        async function refreshScreenshot() {
            try {
                const img = document.getElementById('screenshotImg');
                const placeholder = document.getElementById('screenshotPlaceholder');
                img.src = `${API_BASE}/api/agent/screenshot?t=${Date.now()}`;
                img.style.display = 'block';
                placeholder.style.display = 'none';
            } catch (e) {
                alert('Không thể lấy screenshot');
            }
        }

        async function saveConfig() {
            const updates = {
                max_count: parseInt(document.getElementById('cfgMaxCount').value),
                break_interval: parseInt(document.getElementById('cfgBreakInterval').value),
                captcha_timeout: parseInt(document.getElementById('cfgCaptchaTimeout').value),
            };
            try {
                const res = await fetch(`${API_BASE}/api/config`, {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(updates),
                });
                const data = await res.json();
                if (data.error) {
                    alert('Lỗi: ' + data.error);
                } else {
                    alert('✅ Config đã lưu!');
                }
            } catch (e) {
                alert('Không thể kết nối server');
            }
        }

        // ---- Logs ----
        async function fetchLogs() {
            try {
                const res = await fetch(`${API_BASE}/api/logs?n=200`);
                const data = await res.json();
                renderLogs(data.logs);
            } catch (e) {
                console.error('Log error:', e);
            }
        }

        function renderLogs(logs) {
            const container = document.getElementById('logContainer');
            const wasAtBottom = container.scrollTop + container.clientHeight >= container.scrollHeight - 30;

            container.innerHTML = logs.map(log =>
                `<div class="log-line ${log.level}">${escapeHtml(log.message)}</div>`
            ).join('');

            if (wasAtBottom || logAutoScroll) {
                container.scrollTop = container.scrollHeight;
            }
        }

        function clearLogs() {
            document.getElementById('logContainer').innerHTML = '';
        }

        function escapeHtml(text) {
            const div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
        }

        // ---- Load config ----
        async function loadConfig() {
            try {
                const res = await fetch(`${API_BASE}/api/config`);
                const cfg = await res.json();
                document.getElementById('cfgMaxCount').value = cfg.max_count || 50;
                document.getElementById('cfgBreakInterval').value = cfg.break_interval || 25;
                document.getElementById('cfgCaptchaTimeout').value = cfg.captcha_timeout || 60;
            } catch (e) {
                console.error('Config load error:', e);
            }
        }

        // ---- Init ----
        document.addEventListener('DOMContentLoaded', () => {
            loadConfig();
            startPolling();
            fetchStatus();
            fetchLogs();
        });
    </script>
</body>
</html>
"""


# ============================================
# ENTRY POINT
# ============================================

if __name__ == "__main__":
    import uvicorn
    from . import print_api_info, SERVER_HOST, SERVER_PORT

    print_api_info()
    uvicorn.run(app, host=SERVER_HOST, port=SERVER_PORT)
