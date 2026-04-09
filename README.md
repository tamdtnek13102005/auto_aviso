# 🤖 Auto Aviso

adb devices
adb tcpip 5555
adb connect 192.168.1.111:5555
adb kill-server
adb disconnect
cloudflared tunnel --url http://localhost:8000
Bot tự động hóa nhiệm vụ Aviso, kiến trúc Client-Server.

## Kiến trúc

```
┌──────────────┐     HTTP API     ┌──────────────┐     ADB      ┌───────────┐
│    SERVER     │ ──────────────→ │ LOCAL AGENT   │ ──────────→ │   PHONE   │
│  (brain)      │ ←────────────── │ (ADB proxy)   │ ←────────── │ (Android) │
│  port 5000    │                 │  port 8000    │              └───────────┘
└──────┬───────┘                 └──────────────┘
       │
       │  Dashboard
       ↓
   🌐 Browser
```

## Cài đặt

```bash
pip install -r requirements.txt
```

## Chạy

### 1. Local Agent (trên máy có phone)

```bash
cd auto_aviso
python -m local.agent
# → http://0.0.0.0:8000
```

### 2. Server (trên server hoặc cùng máy)

```bash
cd auto_aviso
# Nếu agent chạy trên máy khác, set URL:
# set AGENT_URL=http://192.168.1.100:8000

python -m server.main
# → Dashboard: http://0.0.0.0:5000
# → API Docs:  http://localhost:5000/docs
```

## API Endpoints

### Local Agent (port 8000)

| Method | Endpoint | Mô tả |
|--------|----------|--------|
| GET | `/api/health` | Kiểm tra agent + ADB |
| GET | `/api/screenshot` | Chụp màn hình (PNG) |
| POST | `/api/tap` | Chạm tọa độ (x, y) |
| POST | `/api/swipe` | Vuốt |
| POST | `/api/back` | Nút Back |
| GET | `/api/screen-size` | Kích thước màn hình |
| POST | `/api/alert/start` | Phát cảnh báo captcha |
| POST | `/api/alert/stop` | Dừng cảnh báo |

### Server (port 5000)

| Method | Endpoint | Mô tả |
|--------|----------|--------|
| GET | `/` | Dashboard điều khiển |
| POST | `/api/automation/start` | Bắt đầu bot |
| POST | `/api/automation/stop` | Dừng bot |
| GET | `/api/automation/status` | Trạng thái + thống kê |
| GET | `/api/config` | Lấy config |
| PUT | `/api/config` | Cập nhật config |
| GET | `/api/logs` | Log gần nhất |
| GET | `/api/agent/health` | Kiểm tra agent |
| GET | `/api/agent/screenshot` | Proxy screenshot |

## Cấu trúc thư mục

```
auto_aviso/
├── local/
│   └── agent.py           # Local Agent - ADB proxy
├── server/
│   ├── main.py            # Server API + Dashboard
│   ├── remote_adb.py      # HTTP client → Local Agent
│   ├── engine.py          # Template matching + bot functions
│   └── automation.py      # Vòng lặp chính + thống kê
├── templates/             # Ảnh mẫu template matching
├── amthanh/               # File âm thanh cảnh báo
├── models.py              # (legacy - chạy standalone)
├── test.py                # (legacy - chạy standalone)
└── requirements.txt
```

## Environment Variables

| Biến | Mặc định | Mô tả |
|------|----------|-------|
| `AGENT_URL` | `http://localhost:8000` | URL của Local Agent |
| `TEMPLATES_DIR` | `./templates` | Thư mục chứa ảnh template |
