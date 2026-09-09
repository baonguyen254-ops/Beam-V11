# v9 Feature Lineage / No-Regression Contract

v9 intentionally keeps these v8.1 features:

- Light/Dark theme system
- Fullscreen Command Center
- Floorplan semantic zoom / hard architectural boundary pass
- Room click/tap selection and fullscreen-aware modal portal
- Room Manual Setup: temperature, RH, airflow
- Room Manual Operating Mode
- Global Clinical HVAC & Lighting control plane
- Clinical control profiles
- Sterility / ΔP pressure trend and positive-pressure policy
- Pressure fault injection and recovery simulation
- Three emergency ventilation modes + clear emergency
- HIS stochastic intake, external case and manual scheduling
- HIS Scheduler AI
- Energy AI Supervisor
- Heatmaps / doors / clinical route / alarm hierarchy / utilization / trends

v9 adds calibrated EnergyPlus design information **around** those controls instead of replacing them.

Command Center now has a dedicated `HVAC + Sterility` supervisory workspace specifically to ensure advanced v8.1 controls remain visible in the wall-display experience.


## v10 PRO

Giữ toàn bộ nhóm điều hành v9, thêm registry bệnh nhân/nhân sự/thiết bị, lifecycle ca thật, resource scheduling, clinical evidence gates, online traits, SQLite persistence, signed energy ledger, ROI, auth/permissions, command idempotency, BMS/HIS gateway contracts và bộ kiểm thử v10. Xem V10_RELEASE_NOTES.md.


## v11 PRO

Giữ các nhóm trên và mở thêm màn Phòng. Bổ sung forecasting nhiệt/RH, schedule preview/apply, asset degradation, ROI theo phòng/nguồn, clinical model registry/evaluation/review/inference, archived prediction provenance, role-aware reads và gateway Modbus TCP. Kiểm tra nguồn flagship tiếp tục ở test_frontend_contract.py; kiểm tra hành vi mới ở test_v11.py, test_gateway_v11.py và tools/smoke_v11.py.
