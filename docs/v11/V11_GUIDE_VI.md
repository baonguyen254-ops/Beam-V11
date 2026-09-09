# BEAM v11 PRO: hướng dẫn sử dụng và tích hợp

Phiên bản ứng dụng **11.0.0**, hợp đồng telemetry **beam-final-v11**. Đây là bản nâng cấp từ gói v10 đã bàn giao, giữ toàn bộ bộ điều hành v9. Gói có frontend build sẵn, backend, dữ liệu OpenStudio gốc, công cụ nhập baseline, kiểm thử và các mẫu cấu hình.

## 1. Những yêu cầu đã được nối trong v11

| Yêu cầu | Chỗ sử dụng | Cách hoạt động và điều kiện |
|---|---|---|
| Năng lượng từng phòng | Phòng; Năng lượng & ROI | Công suất theo WebSocket, baseline từng phòng, tích phân điện năng có lưu bền; phân biệt mô phỏng và số đo |
| Chuẩn bị trước trạng thái kế tiếp | Phòng → dự báo/timeline | Học tốc độ nhiệt độ và RH, chọn thời gian chuẩn bị, giữ điều kiện ca đang mổ và 18 phút chuyển ca |
| Ca mổ và xếp lịch tự động | Ca mổ; Phòng → Lập lịch đề xuất; Autopilot cũ | Ràng buộc bệnh nhân, chuyên khoa, đội ngũ, thiết bị, OR, tiền phẫu, hồi tỉnh và turnover; xem trước rồi áp dụng nguyên tử |
| Trait thông minh | Phòng; Trí tuệ vận hành | Mẫu nhiệt/RH hợp lệ, phân vị tốc độ và chất lượng dữ liệu; thời lượng ca theo lịch sử thực tế |
| Tiên lượng theo ca | Phòng → Tiên lượng; Mô hình tiên lượng | Engine logistic theo đặc tả có phiên bản, holdout, duyệt độc lập, dữ liệu trước mổ, chốt bản tiên lượng có nguồn |
| Bệnh nhân và bác sĩ trong phòng | Phòng → Ca mổ & đội ngũ | Liên kết hồ sơ và danh sách phân công; không trình bày danh sách phân công như số người đo trực tiếp |
| Tuổi đời × hiệu năng thiết bị | Phòng → Thiết bị | Giờ còn lại, lịch bảo trì, đo hiệu năng, ngưỡng có nguồn, xu hướng sau bảo trì, thời gian tới giới hạn hiệu năng |
| ROI theo thời gian | Phòng; Năng lượng & ROI | Giây, phút, giờ, ngày, tháng, năm; vốn/OPEX phân bổ theo phòng, chi phí BMS phát sinh, CSV |

Digital Twin, Command Center toàn màn hình, heatmap, cửa/đường đi, semantic zoom, trend, điều khiển phòng, áp suất, các chế độ khẩn cấp và Light/Dark vẫn ở mục **Điều hành**. Không thay bằng dashboard minh họa tĩnh.

## 2. Cài mới và chuyển từ v10

Trên Windows: cài Python 3.12+, giải nén, chạy `INSTALL_BEAM.bat`, rồi `START_BEAM.bat`. Địa chỉ mặc định là `http://127.0.0.1:8000`. Giao diện được đóng gói sẵn nên người dùng không cần Node.js. Lần đầu đọc mã tạo quản trị viên tại đường dẫn hiển thị ở màn đăng nhập; mã này được xóa sau khi tạo tài khoản.

Mỗi máy chủ dùng một thư mục `BEAM_DATA_DIR`; nếu không cấu hình, mặc định là `beam-backend/data/runtime`. Có thể đặt `BEAM_DATA_DIR` ngoài thư mục mã nguồn để các lần cập nhật sau dùng chung dữ liệu.

Để chuyển dữ liệu v10:

1. Dùng `tools/backup_data.py` tạo bản sao SQLite online, kiểm tra bản sao đã có và giữ riêng.
2. Dừng tiến trình v10 trước khi mở dữ liệu bằng v11. Không chạy hai backend dùng chung database.
3. Copy bản sao database vào thư mục dữ liệu riêng cho v11, đặt tên `beam.sqlite3`, hoặc trỏ `BEAM_DATA_DIR` tới thư mục dữ liệu đã sao chép.
4. Cài dependencies v11 rồi chạy. Migration từ schema 1 lên 2 thêm sổ năng lượng theo nguồn, giữ tài khoản, hồ sơ, lịch, lệnh đã ghi, cấu hình và lịch sử cũ.
5. Đăng nhập lại bằng tài khoản hiện có, kiểm tra ca/thiết bị/lịch sử. Bản sao v10 dùng để quay về; không dùng phần mềm v10 ghi vào database đã được v11 nâng cấp.

Ví dụ sao lưu trên Windows, chạy từ thư mục v11:

```bat
.venv\Scripts\python tools\backup_data.py "C:\BEAM_v10_PRO\beam-backend\data\runtime\beam.sqlite3" "C:\BEAM_backups\before-v11.sqlite3"
```

Công cụ sao lưu không ghi đè tệp đích đã có. Không copy riêng file SQLite đang chạy mà bỏ qua WAL; dùng công cụ backup được cung cấp.

## 3. Luồng vận hành một ca

Tạo bệnh nhân tại **Bệnh nhân & đội ngũ**, nhập bác sĩ/phân công chuyên khoa và thời gian không khả dụng. Quản trị viên đăng ký các thiết bị cho OR. Ba loại cốt lõi là máy gây mê, monitor bệnh nhân và bàn mổ; ca có thể yêu cầu loại bổ sung.

Tạo ca tại **Ca mổ**, chọn bệnh nhân, thủ thuật, chuyên khoa, mức khẩn và thời lượng. Khi Autopilot bật, scheduler tiếp tục tự xếp các ca có đủ nguồn lực. Khi muốn duyệt lịch trước, tắt Autopilot trong bộ điều hành cũ, dùng **Phòng → Lập lịch đề xuất**, chọn tối đa 16 ca chưa xếp lịch, xem kết quả và áp dụng. Các ca đang mổ hoặc đã có lịch không bị tự ý dịch chuyển bởi công cụ xem trước này.

Bản đề xuất hết hạn sau 90 giây. Thay đổi bệnh nhân, đội ngũ, lịch hoặc điều kiện phòng khiến bản cũ bị từ chối. Khi áp dụng, backend kiểm tra lại tài nguyên và cửa sổ chuẩn bị; một mục thất bại thì toàn bộ lần áp dụng được hoàn tác. Scheduler hiện là heuristic có ràng buộc, không tuyên bố tìm nghiệm tối ưu toàn cục.

Mở phòng để kiểm tra hồ sơ, đội ngũ, thiết bị và checklist. Bác sĩ xác nhận đồng ý phẫu thuật và tiền phẫu, rồi bấm **Xác nhận bắt đầu** khi tới thời gian và đủ điều kiện. Ca thật cần xác nhận bắt đầu/hoàn tất; thời gian trên lịch không tự chuyển ca thật sang hoàn tất. Hồi tỉnh và cửa sổ chuyển ca còn được giữ sau khi ca hoàn thành. Ca chờ quá giờ tiếp tục giữ phòng ở điều kiện hoạt động.

**Điều khiển phòng** đặt mục tiêu nhiệt/RH/lưu lượng và bỏ chế độ chạy thủ công cũ để mục tiêu mới có hiệu lực. **Theo lịch & AI** giải phóng cả chế độ lẫn mục tiêu thủ công của phòng. Khóa áp suất và chế độ khẩn cấp vẫn có ưu tiên cao hơn; bộ điều khiển toàn cơ sở vẫn có thể tắt Energy AI.

## 4. Trait và dự báo trạng thái

V11 học riêng tốc độ tăng/giảm nhiệt và tăng/giảm RH theo từng phòng, tách CONNECTED khỏi SIMULATION. Với BMS, mẫu cùng timestamp không được đếm lặp. Khoảng mất dữ liệu dài làm khởi động lại tập tốc độ; dữ liệu cũ không được gọi là dự báo đủ cơ sở.

Một chiều dự báo đang lệch mục tiêu cần tối thiểu 10 mẫu thích hợp. Thời gian sẵn sàng lấy chiều chậm hơn giữa nhiệt độ và RH. Khoảng tốc độ p20–p80 là biên kinh nghiệm, không phải khoảng tin cậy lâm sàng. Thời gian chuẩn bị có phần dự phòng và giới hạn; khi thiếu dữ liệu, dùng chính sách dự phòng thay vì dựng mẫu.

Timeline trình bày chuẩn bị môi trường, ca mổ, chuyển ca, tiền phẫu hoặc hồi tỉnh theo phòng. Mốc tương lai là kế hoạch; nhãn xác nhận thực tế cho biết các mốc chưa được nhân viên xác nhận. Đầu ra dự báo phụ thuộc tải và điều kiện tương tự, chưa phải bộ điều khiển MPC đã nghiệm thu cho hệ thống cơ điện cụ thể.

Trait thời lượng dùng trung vị/phân vị 80% từ các ca có giờ bắt đầu/kết thúc thực tế, cần ít nhất 5 ca trước khi đưa ra gợi ý. Nhân viên xác nhận thời lượng khi chỉnh ca; ứng dụng không lấy dữ liệu của cuộc mổ đang diễn ra để tự viết lại thời lượng đã xác nhận.

## 5. Thiết bị và hiệu năng còn lại

Đăng ký thiết bị khai báo tuổi thọ thiết kế, giờ sử dụng và chu kỳ bảo trì. **Bảo trì** ghi biên bản, pass/fail và hiệu năng đo, cập nhật mốc bảo trì nhưng không làm giảm bộ đếm sử dụng. **Ghi đo** bổ sung một lần kiểm tra hiệu năng, không reset bảo trì. Bộ đếm BMS chỉ tăng và có timestamp/nguồn.

**Ngưỡng** khai báo hiệu năng tối thiểu, hạn sử dụng theo lịch nếu có, chi phí thay thế dự kiến và nguồn tài liệu kỹ thuật. Thiết bị hết hạn, đo thấp hơn giới hạn, hết tuổi thọ hoặc tới kỳ bảo trì không được coi là sẵn sàng. CONNECTED yêu cầu kiểm tra thiết bị trong chế độ CONNECTED; kiểm tra mô phỏng và dữ liệu v10 chưa rõ nguồn không tự cấp điều kiện sử dụng thật.

- Giờ còn lại = max(0, tuổi thọ thiết kế − giờ sử dụng).
- Tuổi thọ × hiệu năng = tỷ lệ tuổi thọ còn lại × hiệu năng đo được. Đây là chỉ báo kỹ thuật, không phải xác suất sống sót của thiết bị.
- Dự báo tới ngưỡng dùng hồi quy tuyến tính trên tối đa 40 mốc của đoạn sau lần bảo trì gần nhất. Cần ít nhất 5 mốc giờ khác nhau, xu hướng suy giảm và R² ≥ 0,6; thiếu điều kiện thì hiển thị chưa đủ dữ liệu.

Thời gian dự báo tới ngưỡng là ngoại suy có điều kiện, không phải ngày hỏng hoặc chứng nhận an toàn. Hạn/ngưỡng phải lấy từ tài liệu nhà sản xuất hoặc kỹ thuật viên. Chi phí thay thế là dự toán; không tự hạch toán vào ROI tiết kiệm năng lượng khi chưa ghi chi phí BMS liên quan.

## 6. Tiên lượng ca mổ

V11 có engine suy luận thực thi được, không kèm bộ trọng số y khoa. Đích hiện hỗ trợ là `NO_MAJOR_COMPLICATION_30D`, nghĩa là không có biến chứng nặng trong 30 ngày; không gộp nó với sống sót, khả năng khỏi bệnh hoặc các định nghĩa “thành công” khác.

Quy trình:

1. Quản trị viên nhập JSON `LOGISTIC_V1`: hệ số, center/scale, phạm vi từng đầu vào, đúng nhãn thủ thuật/chuyên khoa, nguồn, quần thể và tiêu chí chấp nhận. ID phiên bản bất biến.
2. Đánh giá 20–500 hồ sơ holdout đã khử định danh mỗi lần. Engine kiểm tra dữ liệu, tính AUC, Brier và calibration ECE/bins. Ngưỡng kích hoạt tối thiểu mặc định 100 ca và 10 ca mỗi nhóm kết quả, cùng tiêu chí số học khai báo trước. Đây là rào kiểm tra phần mềm, không phải khuyến cáo cỡ mẫu lâm sàng.
3. Một tài khoản bác sĩ khác cả người đăng ký và người đánh giá ghi bằng chứng phê duyệt tại cơ sở và ngày hết hạn, tối đa một năm. Đánh giá lại luôn làm mất hiệu lực lần duyệt cũ, kể cả khi lần mới không đạt. Có thể thu hồi mô hình.
4. Tại phòng, nhập bộ dữ liệu trước mổ đúng bệnh nhân, thời điểm trong 72 giờ và nguồn. Tuổi được suy ra từ ngày sinh. ASA, cấp cứu, BMI và các xét nghiệm phải có đúng đơn vị; thiếu biến hoặc ngoài phạm vi thì không xuất phần trăm.
5. Khi đủ điều kiện, giao diện hiển thị dự báo và phiên bản/nguồn. **Chốt bản tiên lượng** ghi lại xác suất, giá trị đầu vào, mã băm đặc tả, lần đánh giá, người thực hiện và thời điểm; lệnh chống ghi trùng. Bản chốt vẫn nằm trong dữ liệu lưu khi mô hình bị thu hồi hoặc ca được lưu trữ.

Mô hình `simulation_only=true` không xuất dự báo trong CONNECTED. Mẫu `examples/clinical/model.template.json` cố ý để hệ số `null`; mẫu này không chạy như một mô hình y khoa. Các hệ số trong unit test chỉ dùng kiểm tra toán, không dùng cho bệnh nhân. V11 không thu thập trọng số hoặc tự động gọi công cụ ACS bằng cách cào trang.

Đánh giá thủ công của bác sĩ vẫn được lưu riêng với nguồn và endpoint. Thống kê nhóm thủ thuật cần tối thiểu 30 kết quả thật đã đủ theo dõi 30 ngày và có khoảng Wilson; đó không phải tiên lượng cá nhân. Tài liệu tham khảo: [TRIPOD+AI](https://www.bmj.com/content/385/bmj-2023-078378) về báo cáo mô hình, [đánh giá hiệu năng mô hình](https://www.bmj.com/content/384/bmj-2023-074820), và [ACS Risk Calculator](https://riskcalculator.facs.org/) về ý nghĩa của ước tính nguy cơ. Quy trình v11 là lựa chọn triển khai phần mềm, không phải chứng nhận tuân thủ những tài liệu này.

## 7. Điện năng, baseline và ROI

Chọn phạm vi toàn viện hoặc từng phòng và nguồn số liệu tại **Năng lượng & ROI**. Có giây, phút, giờ, ngày, tháng, năm; lọc thời gian và xuất CSV. Chỉ số tức thời theo khung WebSocket khoảng một giây; hồ sơ/trait/ROI tổng hợp được tải lại định kỳ khoảng 5 giây. Dữ liệu điện được tích phân theo thời gian quan sát thực tế của vòng lặp.

```text
điện thực tế (kWh) = Σ công suất thực tế (kW) × dt / 3600
điện baseline (kWh) = Σ công suất baseline (kW) × dt / 3600
tiết kiệm = baseline − thực tế
tiền tiết kiệm = Σ chênh lệch kWh × giá điện tại thời điểm mẫu
tiết kiệm vận hành ròng = tiền tiết kiệm − OPEX phân bổ − chi phí BMS phát sinh
ROI (%) = (tiết kiệm vận hành ròng − CAPEX) / CAPEX × 100
```

Tiết kiệm được giữ dấu âm khi tiêu thụ vượt baseline. Mất dữ liệu BMS thì không thêm các khoảng quan sát thiếu; không bù bằng mô phỏng. Giá điện mới chỉ áp dụng cho mẫu mới. Không tính ROI phần trăm khi CAPEX bằng 0; hoàn vốn dự phóng cần ít nhất 24 giờ quan sát và dòng tiền dương.

Giây lưu một giờ, phút lưu ba ngày; giờ giữ lâu dài và tổng hợp thành ngày/tháng/năm theo múi giờ báo cáo. Báo cáo gồm trọn bucket giao với khoảng chọn, có `bucket_alignment_seconds`, tỷ lệ phủ và giới hạn tối đa 5.000 điểm trả về. Không thể truy xuất từng giây của một năm trước sau khi hết retention; vẫn có tổng giờ/ngày/tháng/năm. Dữ liệu thiếu không trở thành giá trị 0.

Migration phân loại các bucket v10 thành SIMULATION, CONNECTED hoặc LEGACY_MIXED. Bucket đã trộn mà không đủ dữ liệu để tách được giữ nguyên nhãn trộn. Báo cáo mặc định theo chế độ hiện tại; có thể chọn nguồn khác. API cho phép ALL để đối chiếu, nhưng giao diện không dùng ALL như thành tích đo thật.

Command Center cũ cũng khôi phục số tích lũy theo đúng nguồn khi đổi chế độ. Khi chuyển sang CONNECTED, ca demo được chuyển vào lưu trữ để không giữ chỗ phòng/hồi tỉnh trong lịch thật; ca thật vẫn được giữ. Ca đang diễn ra phải kết thúc trước khi đổi chế độ.

Phân bổ vốn/OPEX ở từng phòng là phần trăm vốn/OPEX toàn viện; tổng tối đa 100%, phần còn lại là chưa phân bổ. Chi phí BMS phát sinh được ghi một lần theo chứng từ, không ghi lại khoản đã nằm trong annual OPEX. Chi phí bảo dưỡng thiết bị y tế ở danh mục không tự mặc định là chi phí dự án tiết kiệm điện.

Baseline mặc định vẫn là annual tabular EnergyPlus và tham chiếu trung bình tháng, không tự biến thành dữ liệu hourly measured. Công cụ nhập EnergyPlus SQL đủ năm được giữ lại. Phần toàn viện gồm tải chung và tỷ lệ end-use; không mặc định tổng mọi công suất phòng bằng tổng công tơ toàn viện. Hiệu quả đầu tư dùng thực tế cần M&V/baseline phù hợp tại bệnh viện; dự phóng phần mềm chưa phải cam kết tiết kiệm.

## 8. Gateway Modbus TCP và HIS

Backend v11 cung cấp hợp đồng mục tiêu có `proposal_id`, `revision`, thời điểm cấp và hết hạn 15 giây. Gateway gửi biên nhận đúng proposal/phòng/revision, kèm giá trị setpoint đã đọc lại. Backend từ chối lệnh hết hạn, chính sách đã đổi, phản hồi lệch hoặc thiếu sensor tươi. Biên nhận lưu bền, kể cả khi máy chủ khởi động lại trước lần snapshot đầy đủ tiếp theo.

`tools/gateway_modbus.py` hỗ trợ FC03/04 đọc, FC16 ghi holding registers, uint16/int16/uint32/float32, byte/word order và scale/offset. Địa chỉ là zero-based, không dùng trực tiếp số 4xxxx trong catalog. Tham khảo [Modbus specifications](https://www.modbus.org/modbus-specifications) và [giới thiệu function codes](https://www.modbus.org/introduction-to-modbus).

Copy mẫu `examples/gateway-modbus.template.json`, điền theo register map chính thức của đúng PLC/meter. Không có địa chỉ Schneider mặc định được đoán sẵn. Mẫu để địa chỉ `null` nên bị từ chối trước khi đọc/ghi nếu chưa cấu hình. Bản đồ thiết bị có thể cần bổ sung adapter theo model cụ thể; hiện không có BACnet/Modbus RTU/HL7/FHIR driver.

Khởi chạy telemetry-only:

```bash
python tools/gateway_modbus.py site-gateway.json --once
```

Backend và gateway đọc token BMS riêng từ `BEAM_INTEGRATION_TOKEN`. Không đặt token trong JSON hoặc mã nguồn. Gateway dùng HTTPS khi BEAM ở máy khác và không theo chuyển hướng HTTP. Để thử ghi sau nghiệm thu, cần đồng thời `--apply`, `commissioned: true`, tham chiếu nghiệm thu và thanh ghi PLC write-enable đang bằng 1. Mọi setpoint phải nằm trong min/max đã khai báo; chương trình kiểm tra cả nhóm trước khi bắt đầu ghi và đọc lại sau ghi.

Các setpoint được ghi tuần tự; lỗi giữa nhóm có thể để một phần giá trị mới trên PLC. Gateway báo không hoàn tất, không giả định có rollback phần cứng. PLC phải tự bảo vệ áp suất/airflow và giữ trạng thái thích hợp khi lỗi mạng. BEAM chỉ là lớp điều hành cấp cao; vòng điều khiển nhanh và liên động vật lý vẫn thuộc PLC/BMS tại chỗ.

API HIS dùng token khác `BEAM_HIS_INTEGRATION_TOKEN` với danh sách lệnh lâm sàng cho phép. Có CRUD bệnh nhân, nhập/sửa/phân công ca, xếp lịch, bắt đầu/hoàn tất, ghi kết quả, dữ liệu trước mổ và chốt tiên lượng. Đây là hợp đồng JSON, không phải đã kết nối EHR của một bệnh viện cụ thể.

## 9. Vai trò, kiểm thử và phạm vi thực tế

ADMIN quản lý cấu hình, thiết bị, tài khoản và đăng ký/đánh giá mô hình. CLINICIAN quản lý hồ sơ/ca, dữ liệu lâm sàng, kế hoạch lịch và duyệt mô hình. OPERATOR điều hành BMS; VIEWER chỉ đọc. HTTP và WebSocket đều ẩn bệnh nhân/đánh giá lâm sàng khỏi OPERATOR/VIEWER; phân quyền do server quyết định, không chỉ ẩn nút.

Đây là phân quyền theo vai trò cho một cơ sở. Chưa có SSO, phân vùng dữ liệu theo từng khoa hoặc quy trình khóa/mở tài khoản trên UI. Triển khai thật cần chính sách dữ liệu, backup và mạng do cơ sở cấu hình. Không có tài khoản, khóa bootstrap hoặc hồ sơ bệnh nhân thật trong ZIP.

Xem `VALIDATION.md` để biết chính xác kiểm thử đã chạy. Chưa thực hiện kiểm thử thị giác/thao tác trình duyệt, Windows native, Docker/Render, tải dài hạn, nghiệm thu PLC/phòng mổ, kiểm định mô hình y khoa hoặc M&V. Tín hiệu ΔP chính kế thừa đang là cấp cơ sở, không phải mạng điều khiển áp suất độc lập đã nghiệm thu cho từng OR. Các giới hạn này không được biến thành số liệu “đã kiểm định” trên dashboard.
