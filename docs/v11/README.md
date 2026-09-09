# B.E.A.M. v11 PRO

**Hospital BMS · Surgical Digital Twin · Room Intelligence**

V11 lấy từng phòng làm trung tâm: ca mổ, bệnh nhân, đội ngũ, thiết bị, điều kiện bắt đầu, trạng thái kế tiếp và năng lượng được nối trong một màn điều hành. Toàn bộ Digital Twin, Command Center, heatmap, Light/Dark, HVAC, áp suất, chiếu sáng, HIS Scheduler và Energy AI của v9/v10 được giữ lại.

## Chạy trên Windows

1. Cài Python 3.12 trở lên và giải nén toàn bộ ZIP.
2. Chạy `INSTALL_BEAM.bat` một lần, sau đó `START_BEAM.bat`.
3. Mở `http://127.0.0.1:8000`. Lần đầu, dùng mã trong `beam-backend/data/runtime/bootstrap-key.txt` để tạo quản trị viên.

Giao diện đã build sẵn, chỉ cần Node.js 22 khi sửa và build lại mã frontend. Mặc định là dữ liệu mô phỏng; không có mật khẩu chung được cài sẵn.

## Tài liệu chính

- [V11_GUIDE_VI.md](V11_GUIDE_VI.md): luồng sử dụng, chuyển dữ liệu v10, công thức, mô hình, gateway và API.
- [V11_RELEASE_NOTES.md](V11_RELEASE_NOTES.md): tính năng, sửa lỗi và thay đổi hợp đồng.
- [VALIDATION.md](VALIDATION.md): kiểm thử đã thực hiện và giới hạn xác minh.
- [INTERACTION_CONTRACT.md](INTERACTION_CONTRACT.md): frontend, HTTP, WebSocket và gateway.
- [V11_PROGRESS.md](V11_PROGRESS.md): các checkpoint.
- [DEPLOY_HTTPS.md](DEPLOY_HTTPS.md): triển khai nội bộ.

V11 có engine tiên lượng logistic, đánh giá holdout và duyệt mô hình; gói không chứa mô hình y khoa đã được bệnh viện kiểm định. Có driver Modbus TCP cấu hình được, mặc định chỉ đọc; cần mapping và nghiệm thu PLC tại nơi triển khai. Các ngưỡng vận hành kế thừa là cấu hình nguyên mẫu, không phải chứng nhận phòng mổ.

## Linux/macOS và phát triển

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r beam-backend/requirements.txt
.venv/bin/python RUN_BEAM.py --open
```

`INSTALL_DEV.bat` cài môi trường phát triển. `RUN_TESTS.bat` chạy regression, hợp đồng WebSocket, build và smoke test. Một backend worker cho một thư mục dữ liệu SQLite. Tài liệu v9/v10 được giữ để đối chiếu; hướng dẫn hiện tại là v11.
