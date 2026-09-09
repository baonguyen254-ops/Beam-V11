# B.E.A.M. v10 PRO release notes

## Bài toán được xử lý

V9 có giao diện điều hành và baseline phong phú, nhưng hồ sơ, nguồn lực lâm sàng, lưu trữ dài hạn và đường đi xác nhận lệnh còn rời rạc. V10 giữ nền tảng đó, bổ sung backend bệnh viện và đưa các thao tác vào cùng hợp đồng dữ liệu có kiểm tra, audit và lưu bền.

| Nhóm lỗi / khoảng trống | Thay đổi |
|---|---|
| API/WS không có tài khoản | Bootstrap một lần, scrypt, session HttpOnly, kiểm tra origin và quyền hành động |
| Actor/role do trình duyệt khai báo | Backend lấy từ session/gateway và ghi đè payload |
| Mất ACK dễ tạo trùng | Command ID bền vững, fingerprint, retry cùng ID qua HTTP, xử lý kết quả đã có |
| LIVE trước khi có state hợp lệ | Kiểm tra contract/version và cấu trúc, watchdog 6 giây, khóa lệnh khi stale/mismatch |
| Modal bị state trực tiếp ghi đè | Form room chỉ khởi tạo khi đổi phòng; toast dùng portal trên modal/fullscreen |
| Hàng chờ chỉ hiển thị 8/16 ca | Giữ toàn bộ danh sách v9; workspace mới có tìm kiếm, phân trang, archive |
| Mất trạng thái khi khởi động lại | SQLite WAL lưu snapshot, registry, case archive, audit, command receipts và năng lượng |
| Lịch chỉ xét OR | Thêm bệnh nhân, ba vai trò đội ngũ, chuyên khoa, lịch nghỉ, thiết bị, chuẩn bị và hồi tỉnh |
| Ca thật tự chuyển theo thời gian | START/COMPLETE do người có quyền xác nhận, checklist và thời gian thật |
| Bỏ qua ca trễ/turnover | Giữ chỗ ca trễ, thời gian chuẩn bị, turnover và hồi tỉnh, chặn chế độ minimum/shutdown khi có lịch |
| Thiếu danh mục tài sản | Hồ sơ tài sản, giờ máy không giảm, tuổi đời còn lại, hạn bảo trì, biên bản hiệu năng và pass/fail |
| Nhầm checklist với tiên lượng y khoa | Readiness có nhãn riêng; tiên lượng cá nhân trả null khi chưa có model; đánh giá bác sĩ có nguồn |
| Chưa có học từ vận hành | EWMA tốc độ làm mát và gợi ý thời lượng từ ca thật đủ mẫu |
| ROI chỉ có phiên đang mở | Tích phân có dấu theo thời gian, giá tại mẫu, rollup và CSV, CAPEX/OPEX/ROI/payback có điều kiện |
| Sensor thật mất nhưng còn số mô phỏng | CONNECTED giữ giá trị cũ có nhãn, không bù mô phỏng, không ghi mới năng lượng khi nguồn hết hạn |
| Fault giả che tín hiệu thật | Inject/reset áp suất bị khóa trong CONNECTED; isolation không bỏ qua cảnh báo áp suất đo thật |
| Bật nhầm toàn bộ PREOP / hồi tỉnh chưa diễn ra | Hoạt động PREOP bám phòng được phân, hồi tỉnh ca thật chờ hoàn tất thật |
| SQL nhập thiếu hoặc trộn run | Chỉ nhận đủ năm theo lịch, kiểm tra interval/numeric, đối chiếu run và ghi file nguyên tử |
| Lệch múi giờ / năm nhuận baseline | Ánh xạ lịch theo timezone EPW/IANA; xử lý 29/2 mà không lệch tháng sau |
| Chạy bản bàn giao cần hai server | UI build kèm FastAPI một origin; launcher Python và installer Windows |

## Tính năng giữ nguyên

Sơ đồ 62 không gian và 8 OR, semantic zoom/pan, cửa và circulation, các heatmap, room controls, Room Manual Setup, Light/Dark, Command Center fullscreen/fallback, HVAC profiles, Lighting, Sterility controls, HIS stochastic simulator, Energy AI, annual/monthly/end-use tabular panels và toàn bộ file nguồn OpenStudio/EnergyPlus vẫn có trong gói. Chart cooling/weather chỉ xuất hiện khi nguồn có dữ liệu tương ứng.

## Giới hạn triển khai

V10 là phần mềm trình diễn và thử tích hợp có dữ liệu bền vững. Cần gateway phần cứng, chính sách kiểm soát môi trường được bệnh viện duyệt, model lâm sàng có quyền sử dụng và kiểm định, phân quyền đọc theo khoa/patient, nghiệm thu M&V, kiểm thử tải và quy trình vận hành trước sản xuất. Bộ lập lịch hiện là heuristic ràng buộc trong 48 giờ, chưa phải tối ưu toàn cục. Xem `V10_GUIDE_VI.md` để biết công thức và điều kiện sử dụng.
