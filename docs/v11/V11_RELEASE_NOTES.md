# BEAM v11 release notes

## Tính năng mới

- Màn Phòng mặc định, kết nối đồng thời WebSocket và API hồ sơ/nguồn lực.
- Trait nhiệt/RH tách nguồn, dự báo trạng thái kế tiếp và giữ cửa sổ chuyển ca.
- Kế hoạch lịch xem trước, thời hạn 90 giây, kiểm tra thay đổi và áp dụng nguyên tử.
- Lịch sử hiệu năng, giới hạn kỹ thuật và tuổi đời × hiệu năng thiết bị.
- Sổ năng lượng tách SIMULATION/CONNECTED/LEGACY_MIXED; ROI đúng phòng và khoảng chọn, phân bổ vốn, chi phí có chống trùng.
- Registry logistic model có phiên bản bất biến, holdout, duyệt độc lập, hết hạn/thu hồi, dữ liệu trước mổ và chốt dự báo có bằng chứng.
- Driver Modbus TCP cấu hình, interlock và read-back; hợp đồng proposal/expiry và biên nhận lưu bền.
- Phân quyền đọc dữ liệu lâm sàng ở HTTP và WebSocket.

## Các lỗi phối hợp đã sửa

- Phản hồi HTTP của lịch đề xuất nay tuần tự hóa datetime giống WebSocket; retry không tạo lịch trùng.
- Nút trả phòng về AI bỏ cả manual mode và manual targets, tránh trạng thái nhìn như tự động nhưng còn override.
- Form setpoint dùng cùng giới hạn với backend; đặt target mới bỏ manual mode cũ đang che mục tiêu.
- Payload mô hình lớn đi qua HTTP với cùng command ID, tránh đóng WebSocket vì vượt frame limit.
- ROI không còn luôn dùng số toàn viện khi người dùng chọn một phòng.
- Command Center cũ khôi phục tổng tiết kiệm theo đúng nguồn khi đổi chế độ; ca demo được chuyển vào lưu trữ khi vào CONNECTED để không chiếm tài nguyên của lịch thật.
- Biên nhận gateway mới hơn snapshot không bị mất khi restart.
- Kiểm tra mô phỏng không cấp điều kiện thiết bị trong CONNECTED; khoảng mất sensor dài không tái sử dụng tập tốc độ cũ như dữ liệu mới.
- UI/launcher/static assets/test contracts thống nhất 11.0.0 / beam-final-v11.

## Tương thích

Giữ 17 họ lệnh, các flagship Digital Twin/Command Center và dữ liệu mô hình v9/v10. Schema database tăng từ 1 lên 2 bằng migration bổ sung. Gateway v10 phải nâng sang proposal v11; receipt chỉ có room/revision/applied không còn đủ. API energy mặc định nguồn hiện tại và ROI đúng scope; dùng `source=ALL` chỉ khi cần đối chiếu lịch sử trộn.

V11 không cài sẵn trọng số tiên lượng y khoa. Register map, interlock, ngưỡng phòng mổ và mô hình cần xác nhận tại bệnh viện; không có hành động điều khiển thiết bị thật nào được thực hiện trong phiên phát triển này.
