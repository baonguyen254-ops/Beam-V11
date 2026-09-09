# BEAM v11 • Checkpoint 3: bản bàn giao

Đã tạo bản làm việc từ đúng gói v10 đã bàn giao. Bản v10 được giữ nguyên.
Backend và hợp đồng telemetry đã nâng lên 11.0.0. Màn Phòng là trang mặc định; Digital Twin và Command Center cũ nằm trong mục Điều hành.

## Đã hoàn thành tại checkpoint 3

- Hoàn tất màn điều hành từng phòng và các biểu mẫu nối frontend/backend; giữ 17 họ lệnh và các flagship v9/v10.
- Chốt tiên lượng theo ca lưu đầu vào, xác suất, phiên bản và bằng chứng đánh giá/phê duyệt; không cung cấp trọng số y khoa chưa kiểm định.
- Sửa phản hồi lịch HTTP có datetime, phục hồi biên nhận sau restart, dữ liệu trait cũ, nguồn kiểm tra thiết bị và ROI theo phạm vi/thời gian.
- Command Center khôi phục tổng theo nguồn khi đổi chế độ; ca demo chuyển vào lưu trữ khi vào CONNECTED, tránh chiếm chỗ ca thật.
- Đã chạy **100 pytest**, kiểm tra **17 họ lệnh**, **27 lệnh WebSocket**, **21 lệnh HTTP v11**, build TypeScript/Vite, launcher/static/CSV, backup và restart; tất cả đạt. Có 2 cảnh báo deprecation và cảnh báo kích thước bundle, chi tiết trong VALIDATION.md.
- Có hướng dẫn cài đặt/chuyển v10, cấu hình HIS/Modbus, mẫu dữ liệu mô hình/holdout và ma trận chức năng/điều kiện sử dụng.
- Gói có frontend đã build, source và dữ liệu OpenStudio gốc; không kèm database vận hành, khóa hay node_modules.
- Đã kiểm tra CRC và nội dung ZIP, giữ nguyên 7 tệp dữ liệu mô hình gốc, giải nén sang thư mục mới rồi chạy thành công kiểm tra khởi động/đăng nhập/CSV/backup/restart.

## Đã hoàn thành tại checkpoint 2

- Màn Phòng nối API phòng, hồ sơ bệnh nhân, đội ngũ, checklist, điều khiển, timeline, trait, thiết bị, ROI và biên nhận gateway.
- Biểu mẫu đo hiệu năng/ngưỡng thiết bị, phân bổ vốn/chi phí, nhập dữ liệu trước mổ và lịch đề xuất đều đi qua bộ xử lý lệnh có ACK/chống trùng.
- Màn quản lý mô hình: nhập JSON, đánh giá holdout, bác sĩ độc lập duyệt và thu hồi; báo cáo calibration.
- Báo cáo năng lượng chọn riêng dữ liệu thực/mô phỏng/lịch sử v10 trộn nguồn; ROI đúng phạm vi phòng được chọn.
- Dữ liệu lâm sàng được lọc theo vai trò ở cả HTTP và WebSocket.
- Gateway Modbus TCP có bộ giải mã thanh ghi, giới hạn ghi theo mapping, PLC interlock, đọc lại setpoint; mặc định chỉ đọc. Đã thử trên fake PLC localhost.
- 99 pytest passed; TypeScript/Vite production build passed. Chưa có kiểm thử giao diện bằng trình duyệt hoặc thiết bị bệnh viện thật.
- Đang hoàn thiện smoke test gói chạy, ví dụ cấu hình và tài liệu bàn giao.

## Đã hoàn thành tại checkpoint 1

- API tổng hợp danh sách phòng và chi tiết từng phòng: ca mổ, bệnh nhân, đội ngũ, thiết bị, checklist, timeline, điều khiển và ROI.
- Trait nhiệt độ lẫn độ ẩm, kiểm soát mẫu trùng và cũ, thời gian chuẩn bị theo dữ liệu; giữ điều kiện phòng trong cửa sổ turnover.
- Kế hoạch lịch xem trước, kiểm tra thay đổi tài nguyên, áp dụng nguyên tử và hoàn tác khi có xung đột.
- Lịch sử kiểm tra thiết bị, ngưỡng kỹ thuật có nguồn, xu hướng theo giờ sử dụng sau lần bảo trì gần nhất.
- Migration SQLite bổ sung sổ năng lượng tách mô phỏng/đo thật, giữ nguyên dữ liệu v10; ROI theo phòng, tỷ lệ phân bổ tối đa 100%, chi phí BMS có chống ghi trùng.
- Engine logistic JSON có phiên bản bất biến, đánh giá holdout AUC/Brier/calibration, bác sĩ khác tài khoản duyệt, hết hạn và thu hồi; kiểm tra dữ liệu đầu vào. Không kèm trọng số y khoa.
- Đề xuất gateway hết hạn sau 15 giây, kiểm tra chính sách thay đổi và phản hồi đọc lại setpoint; lưu biên nhận.
- Đã chạy 66 kiểm thử hồi quy v9/v10 và 15 kiểm thử hành vi v11: 81 passed. Đây chưa phải kiểm định thiết bị thật hay mô hình lâm sàng.

## Mốc khởi đầu

Checkpoint 0 giữ bản nền v10 đã bàn giao trước khi phát triển v11. Các checkpoint 1, 2 và 3 ghi lại tiến độ trên cùng bản nâng cấp; không ghi đè gói v10.

## Cần dữ liệu và nghiệm thu tại cơ sở để vận hành thật

Đặc tả thanh ghi/giới hạn PLC và kiểm tra liên động; mô hình tiên lượng có dữ liệu và phê duyệt lâm sàng phù hợp; baseline/M&V và phân bổ vốn thực tế; dữ liệu nhân sự, bệnh nhân, thiết bị và chính sách vận hành của bệnh viện. Các phần này không thể xác nhận từ bộ source demo. Chưa thực hiện browser QA, Windows native, Docker/Render, tải dài hạn hoặc nghiệm thu bệnh viện; xem VALIDATION.md.
