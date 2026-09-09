# BEAM v10 PRO: hướng dẫn chạy và tích hợp

Bản nâng cấp tiếp tục nền React/Vite và FastAPI của v9, giữ bộ giao diện Digital Twin cùng dữ liệu OpenStudio gốc. Phần bổ sung tạo một luồng thống nhất từ hồ sơ bệnh nhân, đội ngũ và thiết bị đến lịch phòng mổ, điều kiện vận hành, năng lượng và ROI. Đây là bản phần mềm có thể chạy để trình diễn và thử nghiệm tích hợp; phần cứng BMS và mô hình tiên lượng lâm sàng cần được xác nhận riêng tại bệnh viện.

## 1. Chạy nhanh trên Windows

1. Giải nén toàn bộ `BEAM_v10_PRO.zip`, giữ nguyên cấu trúc thư mục. Cài Python 3.12 trở lên và bật tùy chọn thêm Python vào PATH.
2. Chạy `INSTALL_BEAM.bat` một lần để tạo môi trường Python và cài thư viện. Bản bàn giao đã kèm frontend build, không cần Node.js để sử dụng.
3. Chạy `START_BEAM.bat`. Trình duyệt mở `http://127.0.0.1:8000`. Giữ cửa sổ máy chủ đang chạy.
4. Lần đầu, đọc mã trong `beam-backend/data/runtime/bootstrap-key.txt`, nhập vào màn hình khởi tạo, tạo tài khoản quản trị với mật khẩu ít nhất 12 ký tự. Mã bị xóa sau khi khởi tạo thành công. Không có mật khẩu mặc định.
5. Đăng nhập để sử dụng. Khi dừng, nhấn Ctrl+C ở cửa sổ máy chủ, chờ ứng dụng lưu trạng thái. Lần mở tiếp theo giữ hồ sơ, lịch, cấu hình, audit và sổ năng lượng.

Nếu dùng `BEAM_DATA_DIR` tùy chỉnh, mã khởi tạo và cơ sở dữ liệu nằm trong thư mục đó. Không xóa thư mục runtime để sửa lỗi đăng nhập, vì sẽ làm mất dữ liệu. Sao lưu trước mọi thao tác phục hồi.

Trên macOS/Linux, mở terminal tại thư mục dự án:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r beam-backend/requirements.txt
.venv/bin/python RUN_BEAM.py --open
```

Mặc định máy chủ chỉ lắng nghe loopback. Một tiến trình, một worker là điều kiện kiến trúc hiện tại. Không chạy nhiều worker cùng một SQLite vì mỗi worker sẽ có bộ mô phỏng và trạng thái riêng.

## 2. Những tính năng v9 được giữ

| Nhóm | Trong v10 |
|---|---|
| Digital Twin | 62 không gian, 8 phòng mổ, sơ đồ và cửa từ OpenStudio, zoom/pan, nhãn theo độ phóng đại, luồng di chuyển |
| Heatmap | Trạng thái, nhiệt độ, độ ẩm, điện năng; trend, utilization, cảnh báo và chi tiết phòng |
| Command Center | Toàn màn hình và phương án chiếm viewport khi browser từ chối fullscreen |
| HVAC và chiếu sáng | Setpoint toàn cục, profile, mức đèn, điều khiển và chế độ riêng từng phòng |
| Sterility | Chính sách áp suất, cảnh báo, emergency modes và khóa an toàn; inject/reset áp suất chỉ ở mô phỏng |
| HIS | Ca ngẫu nhiên trong mô phỏng, ưu tiên ca, đặt lịch tự động/thủ công, luồng chuẩn bị và hồi tỉnh |
| Energy AI | Dự điều hòa phòng sắp có ca, setback phòng rảnh, giám sát và giải thích hành động |
| OpenStudio/EnergyPlus | Dữ liệu annual, monthly, end-use, HVAC design, báo cáo HTML, file OSM và bộ importer |
| Giao diện | Light/Dark, màn hình vận hành cũ và các không gian quản lý mới |

Các tài liệu v9 được giữ trong `docs/v9` để đối chiếu. Với cách chạy, API và trạng thái kiểm thử, dùng hướng dẫn v10 này và `VALIDATION.md`.

## 3. Quy trình ca mổ

Vào **Bệnh nhân & đội ngũ**, tạo bệnh nhân với mã bệnh án duy nhất, tên, ngày sinh, giới tính, thông tin dị ứng và bệnh nền. ASA là thông tin bác sĩ cung cấp, ứng dụng không tự suy ra. Tạo nhân sự gồm `SURGEON`, `ANESTHESIOLOGIST`, `NURSE`; khai báo chuyên khoa và khoảng thời gian không khả dụng.

Vào **Thiết bị**, đăng ký tài sản vào từng phòng. Mỗi ca luôn yêu cầu tối thiểu `ANESTHESIA_MACHINE`, `PATIENT_MONITOR`, `SURGICAL_TABLE`; có thể thêm loại thiết bị khác trong phân công ca. Tên loại là mã IN HOA và phải thống nhất giữa yêu cầu ca với hồ sơ tài sản.

Vào **Ca mổ**, chọn **Thêm ca mổ**, chọn bệnh nhân đã đăng ký, thủ thuật, chuyên khoa, ưu tiên và thời lượng. Nếu AI lập lịch đang bật, backend tìm slot đáp ứng đồng thời phòng đúng chuyên khoa, bệnh nhân không trùng lịch, đội ngũ đủ ba vai trò, thiết bị còn đủ giờ sử dụng trước bảo trì, phòng chuẩn bị và hồi tỉnh khả dụng. Mỗi phòng hỗ trợ hiện được coi là một chỗ; cần cấu hình mở rộng nếu bệnh viện có nhiều giường trong cùng phòng.

Ca không đủ điều kiện nằm trong hàng chờ với `constraint_reason`. Dùng **Phân công** để bổ sung bệnh nhân, đội ngũ, thiết bị và checklist. Bộ lập lịch thử lại theo nhịp, có giới hạn công việc mỗi vòng để giữ phản hồi giao diện. Phạm vi lập lịch 48 giờ; giữa hai ca trong một OR có 18 phút turnover. Những con số này là giả định vận hành của bản demo, cần bệnh viện phê duyệt trước khi áp dụng thật.

**Đặt lịch** thủ công vẫn đi qua toàn bộ ràng buộc. Thời điểm phải đủ thời gian chuẩn bị từ lúc tạo ca và lúc hiện tại. Giao diện gửi thời gian kèm múi giờ, backend không chấp nhận thời gian không có offset.

Ca thật không tự bắt đầu chỉ vì đồng hồ vượt lịch. Bác sĩ xác nhận đồng ý phẫu thuật và kiểm tra tiền phẫu, sau đó bấm **Bắt đầu thật** khi đủ thời gian và checklist vận hành đạt. Nếu chưa đạt nhiệt độ, RH, lưu lượng, áp suất hoặc nguồn lực, backend từ chối và nêu lý do. Ca bị trễ vẫn giữ phòng và nguồn lực, không được coi là đã xong theo thời lượng ước tính.

**Hoàn tất** ghi thời điểm kết thúc thật, vẫn giữ turnover và hồi tỉnh. **Hủy** chỉ áp dụng ca đang chờ và cần lý do. Hồ sơ kết thúc được lưu kho bền vững, truy cập bằng bộ lọc `ARCHIVE`; không bị mất khi danh sách ca trực tiếp được giới hạn dung lượng.

Trong mô phỏng, ca `HIS_RANDOM` có hồ sơ gắn nhãn Demo và tự chuyển trạng thái theo thời gian. Chuyển sang CONNECTED hủy các ca Demo đang chờ, ngừng sinh ca và loại dữ liệu Demo khỏi lựa chọn nguồn lực hợp lệ. Không thể chuyển chế độ khi đang có ca mổ.

## 4. Trait và dự báo

Trait làm mát học tốc độ giảm nhiệt quan sát được bằng EWMA, chỉ nhận mẫu liên tiếp đủ gần và lưu lượng phù hợp. Sau tối thiểu 10 mẫu hợp lệ, thời gian cần điều hòa có thể mở rộng thời gian chuẩn bị của Energy AI, giới hạn 12 đến 60 phút. Đây là ước tính từ tải tương tự, không phải mô hình nhiệt vật lý đã hiệu chỉnh cho từng bệnh viện.

Trait thời lượng dùng `actual_start` và `actual_end` của ca thật. Sau ít nhất 5 ca cùng tên thủ thuật, dashboard hiển thị trung vị và phân vị 80% làm gợi ý thời lượng có đệm. Người lập lịch xác nhận gợi ý khi sửa ca; lịch đã đặt không bị tự ghi đè.

**Chưa có mô hình dự đoán xác suất thành công cá nhân được cài đặt.** API trả `predicted_success_percent: null` và `VALIDATED_MODEL_REQUIRED`. Điểm readiness chỉ là tỷ lệ mục checklist vận hành đạt. Thông tin ca và BMS không đủ để tự tạo một tỷ lệ thành công có giá trị y khoa.

Phần lâm sàng hiện hỗ trợ đánh giá do bác sĩ nhập kèm tỷ lệ, kết cục, thời hạn theo dõi, nguồn/model/version, thời điểm và người ghi. Kết quả theo dõi chỉ nhận sau đủ 30 ngày từ kết thúc thật, với bằng chứng do bác sĩ xác minh. Khi có tối thiểu 30 kết quả thật cùng thủ thuật, ứng dụng hiển thị tỷ lệ quan sát và khoảng Wilson 95%; không hiệu chỉnh case-mix và không biến thành tiên lượng cho bệnh nhân riêng lẻ.

Để triển khai tiên lượng thật, bệnh viện cần chọn kết cục rõ ràng, thu thập biến lâm sàng phù hợp, xử lý dữ liệu thiếu, chọn mô hình được phép sử dụng, kiểm định ngoài mẫu và hiệu chỉnh tại cơ sở, rồi xác lập quy trình bác sĩ duyệt. ACS NSQIP là ví dụ về công cụ dùng đặc điểm bệnh nhân và thủ thuật để dự báo các kết cục trong 30 ngày. BEAM chỉ cung cấp liên kết ra trang gốc, chưa tích hợp hoặc tự động khai thác công cụ này. [Nguồn ACS](https://riskcalculator.facs.org/RiskCalculator/about.html).

## 5. Tuổi đời và hiệu năng thiết bị

Tuổi đời còn lại theo giờ bằng `max(0, design_life_hours − runtime_hours)`. Phần trăm còn lại chia cho tuổi thọ thiết kế. Hạn bảo trì tính từ số giờ máy ở lần bảo trì trước; giờ chạy không được giảm, không có chức năng reset tuổi máy về 0.

Hiệu năng là số đo kỹ thuật viên nhập trong **Bảo trì / đo**, kèm phương pháp hoặc biên bản, chi phí và quyết định đạt/không đạt. Không suy diễn hiệu năng từ phần trăm tuổi đời. Thiết bị không đạt chuyển OFFLINE; thiết bị hết tuổi thọ hoặc đến hạn bảo trì không được coi là sẵn sàng dù trạng thái khai báo AVAILABLE. CONNECTED yêu cầu có kiểm định đạt và tài sản thật.

Trong mô phỏng, giờ chạy tăng khi thiết bị thuộc phòng đang có ca. CONNECTED nhận đồng hồ giờ chạy từ gateway, không tự ước tính theo ca. Hiện chưa có MTBF/RUL bằng mô hình hỏng hóc, theo dõi phụ tùng hoặc kế hoạch bảo trì theo lịch tháng; các trường hợp đó cần dữ liệu OEM và lịch bảo trì của bệnh viện.

## 6. Năng lượng, baseline và ROI

Tab **Năng lượng & ROI** đọc sổ mẫu đã ghi, chọn toàn cơ sở hoặc từng phòng, độ phân giải giây, phút, giờ, ngày, tháng, năm và khoảng thời gian. CSV có cùng dữ liệu, không tự bù thời gian mất tín hiệu. Mẫu giây giữ 1 giờ gần nhất, mẫu phút giữ 3 ngày, mẫu giờ được lưu bền để tổng hợp ngày/tháng/năm. Không thể xem mẫu giây của nhiều tháng trước vì dữ liệu đã được tổng hợp.

Với mẫu công suất `P_actual`, baseline `P_base`, khoảng quan sát `dt` giây:

```text
actual_kWh = P_actual × dt / 3600
baseline_kWh = P_base × dt / 3600
saved_kWh = baseline_kWh − actual_kWh
savings_VND = saved_kWh × tariff_at_sample
carbon_kg = saved_kWh × emission_factor_at_sample
```

Khoản tiết kiệm giữ dấu âm khi tải thực tế vượt baseline. Giá điện/hệ số CO₂ thay đổi chỉ tác động mẫu sau khi lưu cấu hình. Khoảng vượt ranh giới giây, phút hoặc giờ được chia đúng tỷ trọng thời gian. Sau khi tạm dừng máy hoặc nghẽn vòng xử lý, một tick chỉ được tính tối đa 5 giây, không ghi nhận tiết kiệm cho toàn bộ thời gian máy ngừng hoạt động.

CONNECTED giữ mẫu sensor gần nhất trong thời gian còn hạn, theo phương pháp giữ mẫu. Mất công tơ cơ sở sẽ ngừng ghi năng lượng toàn cơ sở; mất sensor phòng sẽ ngừng ghi năng lượng phòng đó. Công tơ cơ sở và các đồng hồ phòng có thể phủ phạm vi khác nhau, nên không cộng tổng các phòng để ép bằng đồng hồ cơ sở. UI báo tỷ lệ thời gian có số đo thật và thời gian quan sát.

Baseline đi kèm là EnergyPlus full annual tabular với độ phân giải tham chiếu **MONTHLY_MEAN**. Có 8760 giờ mô phỏng không có nghĩa là đã có 8760 mẫu công tơ theo giờ. Giá trị kW tham chiếu trực tiếp hiện là trung bình tháng, chưa điều chỉnh thời tiết, số ca hay thay đổi hoạt động. Baseline phòng là mô hình đối chứng phân bổ từ thiết kế; số đo công tơ so với baseline này vẫn là ước tính tiết kiệm, chưa phải kết quả M&V được nghiệm thu.

Thiết bị y tế được dùng cùng giả định nhu cầu trong hai mô hình thực tế/đối chứng, không ghi nhận tiết kiệm bằng cách giả định tắt plug load y tế khi giảm HVAC. Công suất quạt và chiếu sáng vẫn theo chính sách v9; không gửi lệnh tắt thiết bị y tế.

ROI toàn cơ sở dùng lịch sử tích lũy, độc lập bộ lọc báo cáo:

```text
allocated_OPEX = annual_OPEX × observed_seconds / (365.25 × 86400)
net_operating_savings = observed_electricity_savings − allocated_OPEX
ROI_percent = 100 × (net_operating_savings − CAPEX) / CAPEX
projected_annual_net = savings / observed_seconds × 365.25 × 86400 − annual_OPEX
projected_payback_years = CAPEX / projected_annual_net
```

Nếu chưa nhập CAPEX, ROI là chưa xác định. Dự phóng chỉ mở sau ít nhất 24 giờ quan sát; payback chỉ có khi CAPEX và lợi ích ròng năm đều dương. OPEX trong công thức được phân bổ theo thời gian quan sát, chưa bao gồm tài trợ, khấu hao, giá điện giờ cao điểm hoặc chi phí ngừng máy. Dữ liệu mô phỏng vẫn là kinh tế mô phỏng, không phải lợi ích thực thu.

## 7. API BMS và HIS

Các endpoint tương tác người dùng dùng cookie HttpOnly, SameSite Strict. WebSocket `/ws` yêu cầu đăng nhập và origin hợp lệ. POST dùng session phải gửi Origin cùng miền hoặc nằm trong danh sách cho phép. Gateway sử dụng bearer token riêng ở phía máy chủ, tuyệt đối không cấu hình token trong biến `VITE_...`.

| Biến môi trường | Ý nghĩa |
|---|---|
| `BEAM_DATA_DIR` | Thư mục dữ liệu SQLite và mã khởi tạo |
| `BEAM_FLOORPLAN_PATH` | Tùy chọn file sơ đồ khác; phải giữ mapping tương thích |
| `BEAM_ALLOWED_ORIGINS` | Danh sách origin chính xác, phân cách dấu phẩy; không dùng `*` |
| `BEAM_INTEGRATION_TOKEN` | Token BMS do quản trị viên tạo ngẫu nhiên, đủ dài |
| `BEAM_HIS_INTEGRATION_TOKEN` | Token riêng cho HIS, chỉ được phép lệnh lâm sàng |

Gửi telemetry bằng `POST /api/integrations/telemetry`, header `Authorization: Bearer <BMS_TOKEN>` và `Content-Type: application/json`. Chỉ nhận trong CONNECTED; timestamp ISO 8601 có timezone, không tương lai, không quá hạn, phải tăng dần theo scope. Lấy mã phòng từ `/floorplan` sau đăng nhập.

```json
{"scope":"facility","timestamp":"<ISO-8601 hiện tại>","power_kw":72.5,"delta_p_pa":3.2,"source":"main-meter"}
```

```json
{"scope":"<room_id>","timestamp":"<ISO-8601 hiện tại>","power_kw":4.2,"temp_c":20.1,"humidity":49.5,"airflow_m3h":3200,"source":"room-gateway"}
```

Gateway đọc `GET /api/integrations/targets` để nhận mode, revision và setpoint mục tiêu. Phải tự kiểm tra fresh telemetry, trạng thái báo động, giới hạn PLC, feedback actuator, thiết bị đang bảo trì và chính sách bệnh viện trước khi áp dụng. Sau đó gửi `POST /api/integrations/actuation`:

```json
{"room_id":"<room_id>","revision":123,"applied":true,"detail":"PLC feedback confirmed; gateway interlocks passed"}
```

Receipt chỉ là xác nhận gateway cung cấp, không chứng minh thiết bị được nghiệm thu hoặc xác thực độc lập. V10 chưa có driver BACnet/Modbus/Schneider hay điều khiển PLC trực tiếp. Áp suất hiện là một tín hiệu cơ sở, chưa phải mạng chênh áp riêng từng phòng; không đưa các emergency modes demo vào điều khiển toàn bệnh viện khi chưa thiết kế và nghiệm thu logic.

Gửi giờ chạy bằng `POST /api/integrations/device-hours` với `device_id`, `runtime_hours`, `timestamp`, `source`. Timestamp phải trong 300 giây gần nhất và tăng dần; runtime không giảm. Thiết bị hết hạn bảo trì sẽ ảnh hưởng trực tiếp đến lịch ca.

HIS dùng `POST /api/integrations/his/commands`, bearer HIS riêng. Các lệnh hỗ trợ: `UPSERT_PATIENT`, `ADD_EXTERNAL_CASE`, `ASSIGN_CASE`, `UPDATE_CASE`, `MANUAL_SCHEDULE_CASE`, `CANCEL_CASE`, `START_CASE`, `COMPLETE_CASE`, `RECORD_OUTCOME`, `RECORD_CLINICAL_ESTIMATE`. Schema payload giống frontend; HIS không được tạo tài khoản hoặc đổi chính sách BMS.

```json
{"command_id":"his-event-0001","action":"UPSERT_PATIENT","record":{"mrn":"HIS-001","name":"<tên bệnh nhân>","date_of_birth":"1980-01-01","sex":"UNKNOWN"}}
```

Sau khi nhận `record_id`, dùng ID đó làm `patient_id` khi tạo ca. `command_id` phải ổn định khi retry cùng sự kiện. Backend lưu kết quả theo chủ thể và ID, trả `replayed: true` nếu đã xử lý, từ chối dùng lại ID với nội dung khác. HTTP/WebSocket ghi actor từ tài khoản hoặc token, không tin actor/role trong payload.

Giao diện sẽ đối chiếu cùng command_id qua HTTP khi thiếu ACK 8 giây hoặc WebSocket bị ngắt. Nếu cả hai đường đều mất, thông báo giữ ID để đối chiếu audit; không tự tạo ID khác. Kiểm tra dữ liệu trước khi nhập lại một ca.

## 8. Tài khoản, dữ liệu và sao lưu

ADMIN quản trị cấu hình, nhân sự, tài sản và tài khoản. CLINICIAN quản lý hồ sơ bệnh nhân và vòng đời ca. OPERATOR thao tác điều hành BMS. VIEWER chỉ đọc; backend vẫn từ chối lệnh dù sửa role trong trình duyệt. Session hết hạn sau 8 giờ; đăng xuất hủy token. Mật khẩu dùng scrypt và session chỉ lưu hash.

Phân quyền hiện theo nhóm thao tác, chưa chia theo khoa, bệnh viện hoặc bệnh nhân cụ thể. Tài khoản đã đăng nhập có thể đọc hồ sơ qua dashboard; chỉ cấp tài khoản cho người được phép xem dữ liệu đó. Trước vận hành dữ liệu thật cần bổ sung phân quyền đọc theo phạm vi, SSO/MFA hoặc chính sách tương đương, quy trình cấp/thu hồi quyền, mã hóa ổ đĩa và kiểm soát truy cập máy chủ. SQLite hiện chưa mã hóa ở tầng ứng dụng; tránh dùng dữ liệu định danh thật khi demo công khai.

Backup nhất quán khi máy chủ đang chạy:

```bash
python tools/backup_data.py beam-backend/data/runtime/beam.sqlite3 backups/beam-2026-09-08.sqlite3
```

Script không ghi đè file backup đã có và kiểm tra integrity. Bản sao có tài khoản, session và hồ sơ nhạy cảm, cần lưu riêng có bảo vệ. Muốn khôi phục, dừng toàn bộ máy chủ, sao lưu runtime hiện tại, dùng một thư mục dữ liệu sạch và đặt database đã kiểm tra thành `beam.sqlite3`; chỉ sau đó đổi `BEAM_DATA_DIR`. Không ghép file WAL/SHM của database khác. Kiểm tra đăng nhập, số lượng hồ sơ, lịch và tổng năng lượng trước khi đưa trở lại sử dụng.

Dữ liệu mẫu và dữ liệu thật cùng tồn tại trong mô hình nhưng có cờ Demo. Kho năng lượng giữ cả thời gian mô phỏng lẫn đo thật và có `measured_seconds`; nếu cần báo cáo triển khai sạch, tạo thư mục dữ liệu mới cho môi trường thật. Không xóa hoặc đổi dấu lịch sử để làm đẹp ROI.

## 9. Phát triển và baseline

Chạy `INSTALL_DEV.bat` nếu cần sửa frontend, sau đó `RUN_TESTS.bat` để chạy backend, kiểm tra hợp đồng frontend, WebSocket thật và build. Trên nền tảng khác:

```bash
python -m pip install -r beam-backend/requirements-dev.txt
python -m pytest -q beam-backend
python beam-backend/test_frontend_contract.py
python beam-backend/test_transport_contract.py
python tools/build_frontend.py
```

Rebuild cần Node.js 22, npm và mạng tải dependencies. Dev mode chạy uvicorn cổng 8000 một worker và `npm run dev` trong frontend cổng 5173; Vite proxy `/api` và `/ws` cùng origin. Không giữ đồng thời nhiều instance backend cùng thư mục dữ liệu.

Importer SQL chỉ nhận meter Hourly, đủ 8760/8784 giờ theo lịch, interval 60 phút và số hữu hạn không âm. Nếu ghép thêm vào baseline đã có, cần ít nhất hai chỉ số đối chiếu cùng run trong sai số 2%; khác run phải dùng file đích mới hoặc `--replace-run` có chủ đích. Lỗi nhập không làm mất baseline cũ. Các importer HTML và tabular v9 được giữ nguyên cùng bộ kiểm thử.

```bash
python beam-backend/tools/import_energyplus_sql.py /path/to/eplusout.sql --out /path/to/new-baseline.json
```

Build Docker có volume `/data`, chạy user không phải root và một worker. Dockerfile/Windows launcher được kiểm tra nội dung trong phiên này; xem `VALIDATION.md` để phân biệt kiểm thử đã chạy với kiểm thử cần thực hiện trên máy đích.

## 10. Phạm vi bàn giao

Hoàn thành phần dashboard, API, lưu trữ, ràng buộc lập lịch, luồng ca, hồ sơ bệnh nhân/nhân sự, vòng đời tài sản, trait vận hành, báo cáo năng lượng/ROI và các điểm nối gateway. Chưa có nghiệm thu thiết bị thực, model tiên lượng lâm sàng, thuật toán tối ưu toàn cục, M&V được chứng nhận, kiểm thử tải quy mô bệnh viện, HA hoặc phân quyền đa cơ sở. Không gọi bản này là bộ điều khiển y tế đã được chứng nhận; các giới hạn này là đầu vào triển khai thật cần được giải quyết với dữ liệu và hệ thống của bệnh viện.
