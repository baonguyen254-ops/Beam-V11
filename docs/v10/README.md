# B.E.A.M. v10 PRO

**Hospital BMS, Surgical Digital Twin & Operational Intelligence**

V10 giữ sơ đồ OpenStudio, heatmap, Command Center, Light/Dark, bộ điều khiển HVAC/áp suất/chiếu sáng và Energy AI của v9. Bản nâng cấp nối thêm hồ sơ bệnh nhân, đội ngũ, tài sản, quy trình ca mổ, lập lịch có ràng buộc nguồn lực, trait vận hành và sổ năng lượng/ROI lưu bền.

## Chạy ngay

Trên Windows, cài Python 3.12+, giải nén gói, chạy `INSTALL_BEAM.bat`, rồi `START_BEAM.bat`. Mở `http://127.0.0.1:8000`; dùng mã trong `beam-backend/data/runtime/bootstrap-key.txt` để tạo quản trị viên lần đầu. Frontend đã được build sẵn, không cần Node.js khi chỉ sử dụng.

Trên macOS/Linux:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r beam-backend/requirements.txt
.venv/bin/python RUN_BEAM.py --open
```

## Tài liệu

- [Hướng dẫn tiếng Việt và API](V10_GUIDE_VI.md): cài đặt, luồng ca, thiết bị, trait, công thức, BMS/HIS, sao lưu và giới hạn.
- [Thay đổi v10](V10_RELEASE_NOTES.md): sửa lỗi, phần nâng cấp và phần giữ từ v9.
- [Kết quả kiểm thử](VALIDATION.md): các kiểm tra đã thực thi và phạm vi chưa kiểm thử.
- [Hợp đồng frontend/backend](INTERACTION_CONTRACT.md): phiên bản, ACK, API, trạng thái và nguồn dữ liệu.
- [HTTPS và dữ liệu bền vững](DEPLOY_HTTPS.md): điều kiện triển khai nội bộ.
- `docs/v9`: lưu các chỉ dẫn cũ để đối chiếu, không dùng thay hướng dẫn v10.

## Phạm vi

Mặc định SIMULATION với dữ liệu Demo. CONNECTED có API nhận sensor và gateway nhận mục tiêu, nhưng chưa có driver BACnet/Modbus/Schneider hoặc nghiệm thu PLC. Dữ liệu thật không bị thay bằng mô phỏng khi sensor mất tín hiệu. Cần một backend worker cho mỗi thư mục dữ liệu.

Chưa có mô hình tiên lượng thành công ca mổ được kiểm định; ứng dụng không tự tạo tỷ lệ lâm sàng. V10 cung cấp checklist sẵn sàng, ghi nhận đánh giá bác sĩ có nguồn và thống kê nhóm kết quả 30 ngày đủ cỡ mẫu. Baseline mặc định là trung bình tháng từ annual tabular EnergyPlus, nên tiết kiệm/ROI vẫn cần xác minh M&V trước khi dùng như kết quả đầu tư thật.

## Kiểm tra và sửa mã nguồn

`INSTALL_DEV.bat` cài phần phát triển và build UI. `RUN_TESTS.bat` chạy regression, kiểm tra hợp đồng, WebSocket thật và build. Cần Node.js 22 để rebuild; npm dùng `package-lock.json` qua `npm ci`. Bản phần mềm đã được kiểm thử trên Linux; kiểm tra launcher Windows/Docker trên máy đích theo `VALIDATION.md`.
