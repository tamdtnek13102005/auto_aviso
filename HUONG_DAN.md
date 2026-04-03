# 🚀 HƯỚNG DẪN CHẠY AUTO AVISO (PHIÊN BẢN MỚI)

Dự án đã được tách thành mô hình **Client-Server**. Bạn sẽ có 2 thành phần:
1. **Local Agent (Proxy ADB)**: Chạy trên máy tính có cắm cáp nối với điện thoại.
2. **Server (Remote/API/Dashboard)**: Chạy ứng dụng web, chứa thuật toán nhận diện ảnh và luồng tự động hoá. Cung cấp giao diện bảng điều khiển (Dashboard).

---

## 🛠 1. Cài đặt môi trường

Mở Terminal (Command Prompt hoặc PowerShell) tại thư mục `auto_aviso` và chạy lệnh sau để cài đặt các thư viện cần thiết:

```bash
pip install -r requirements.txt
```

*(Yêu cầu máy tính đã cài đặt Python 3, lý tưởng là từ 3.8 trở lên và công cụ ADB)*

---

## 📱 2. Kết nối Điện thoại (ADB)

Hãy chắc chắn rằng:
- Bạn đã bật **USB Debugging** (Gỡ lỗi USB) trên điện thoại Android.
- Điện thoại đã cắm cáp vào máy tính chạy **Local Agent**.
- Kiểm tra kết nối bằng lệnh:
```bash
adb devices
```
*Đảm bảo danh sách thiết bị có hiện lên và không bị lỗi `unauthorized`.*

---

## ▶️ 3. Khởi chạy Hệ thống

Bạn cần chạy **Local Agent** trước, sau đó mới chạy **Server**. Nếu bạn chạy cả 2 trên cùng một máy tính, hãy mở 2 cửa sổ Terminal khác nhau.

### Bước 3.1: Chạy Local Agent (Cửa sổ Terminal 1)

Tại thư mục `auto_aviso`:

```bash
python -m local.agent
```

Hoặc dùng `uvicorn`:
```bash
uvicorn local.agent:app --host 0.0.0.0 --port 8000
```

*Agent sẽ khởi động ở địa chỉ `http://localhost:8000`. Cửa sổ này chịu trách nhiệm gửi lệnh vuốt/chạm (tap, swipe) tới điện thoại và chụp ảnh màn hình.*

---

### Bước 3.2: Chạy Server và Bảng Điều Khiển (Cửa sổ Terminal 2)

Tại thư mục `auto_aviso`:

```bash
python -m server.main
```

Hoặc dùng `uvicorn`:
```bash
uvicorn server.main:app --host 0.0.0.0 --port 5000
```

*Server sẽ khởi động ở địa chỉ `http://localhost:5000`. Đây là bộ não trung tâm (engine), sẽ gọi các API của Local Agent để điều khiển điện thoại.*

---

## 🌐 4. Sử dụng Bảng Điều Khiển (Dashboard)

Sau khi Server chạy thành công, mở trình duyệt web và truy cập vào:

👉 **http://localhost:5000**

Tại đây bạn sẽ thấy giao diện **Dashboard**:
1. Trạng thái kết nối của Agent cũng như trạng thái Tool (IDLE / RUNNING).
2. Các nút điều khiển: **Bắt đầu**, **Dừng**, và **Screenshot** (Xem ảnh màn hình hiện tại trên điện thoại).
3. Khu vực Thống kê theo thời gian thực (số lượng thành công, thất bại, tỉ lệ làm task, số lần gặp captcha...).
4. Nhật ký hệ thống (Logs) để bạn theo dõi lỗi.
5. Cài đặt các thông số như "Số lượt chạy" hay "Nghỉ sau bao nhiêu task".

---

## ⚙️ 5. Thay đổi Cấu hình nâng cao

Toàn bộ Cấu hình của Server đã được gom vào 1 file **`server/config.py`**. 
Nếu muốn thay đổi cơ chế vuốt, thời gian chờ, thay đổi cổng truy cập hay các độ scale của ảnh, bạn chỉ cần mở file này lên và chỉnh sửa tham số mong muốn, sau đó khởi động lại Server.

Ví dụ, chạy Server ở máy tính khác và cần kết nối tới Local Agent, hãy sửa dòng:
```python
AGENT_URL = os.getenv("AGENT_URL", "http://DIADIEM_IP_CUA_MAY_AGENT:8000")
```
