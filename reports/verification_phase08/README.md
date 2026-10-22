# Audit giai đoạn 8 — grounded analysis gate trên dữ liệu thật

[Diagnostics](diagnostics/204ac00306bf48ac98d3823250925b18.json) là audit offline nhánh thiếu dữ liệu, không phải lượt thu thập mới hoặc báo cáo khuyến nghị thị trường.

Kết quả:

- Tái dùng 2 keyword Trends × 93 điểm và 20 ASIN Amazon đã qua validation; Reddit 0 post. Nguồn gốc là [audit giai đoạn 6](../verification_phase06/diagnostics/ba0da4abf898429b9f4816722e73dd0a.json), không phải fixture kiểm thử.
- Quality vẫn insufficient: hai series hợp lệ nhưng Amazon là hub Best Sellers tổng, không phải supporting evidence cho niche Christmas; Reddit chưa có bài.
- Analyzer thật trả `analysis_status=insufficient_data`, `generation_mode=deterministic`, `grounded_analysis=null`; attempts rỗng, model không được gọi. Không tạo fake response hoặc dùng mock model để lấp dữ liệu.
- Ranking unavailable; ideas/Top 3 rỗng. Không tạo “thành công đầy đủ” hay giả định market fit từ valid ratio 22/22.
- Số request provider/model mới: **0**. Evidence giữ original request IDs, query đã redaction, source URLs, retrieved_at và cache flag; audit timestamp mới không biến dữ liệu ngày 21/10 thành quan sát live vừa fetch.

Nguồn live gốc:

- [Google Trends giai đoạn 3](../verification_phase03/diagnostics/fb7b49420fdd40c599abe64bfb35d8f4.json): hai keyword, geo US, thu thập 21/10/2026; partial point không tính metric.
- [Amazon giai đoạn 4](../verification_phase04/diagnostics/cf2eb6447ebf4f6caefc724d1f7d70f7.json): 20 ASIN từ hub tổng; Search/Movers chưa có card phù hợp.
- [Reddit giai đoạn 5](../verification_phase05/diagnostics/9f35f55a6a3445f993abbd279e797a47.json): connection_error/0 post; chưa có credential để kiểm chứng OAuth live.

Lệnh chủ động tái lập khi cần, từ repository root:

    .venv\Scripts\python -B -m scripts.audit_grounded_phase08

Script tái dùng helper restore observations đã validation, không gọi collector, không dùng snapshot làm TTL cache và không gửi dữ liệu archive tới model. Mỗi lần chạy chủ động tạo diagnostics mới; không sửa snapshot cũ.

Kiểm thử cách ly của giai đoạn 8: **210 Python mới + 9 ca bị ảnh hưởng; 6 UI mới + 1 ca bị ảnh hưởng pass**. Chạy từng nhóm mới; một ca summary metadata ordering bị fail đã được sửa và chỉ chạy lại đúng ca đó. Không lặp các ca đã pass/full suite hoặc request nguồn đã kiểm tra. Fixture và response AI giả chỉ nằm trong tests/thư mục tạm, không có trong artifact này.

Giới hạn quan trọng: audit không đi qua generation/schema repair/sampling vì gate đã chặn từ đầu. Các nhánh đó được kiểm thử bằng dữ liệu cách ly, chưa được xác minh positive end-to-end với model thật trên một live run đủ evidence. Không chứng nhận nhà cung cấp hiện truy cập được, mọi URL còn mở được, nguồn có liên quan ngữ nghĩa hoặc đề xuất có market fit. Cần evidence niche-support hợp lệ trước khi có acceptance live đó; không được bypass gate để lấy một báo cáo đẹp.

Xem [contract, ngân sách và security](../../README.md#grounded-ai-analysis--giai-đoạn-8). Triển khai dừng ở giai đoạn 8, chưa phải hardening toàn ứng dụng hay schema typed toàn ResearchResult của các bước sau.
