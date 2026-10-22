# Audit giai đoạn 7 — scoring và ranking

Đây là audit offline trên snapshot live thật đã validation ở giai đoạn 6. Không có request mạng mới; không chạy lại provider đã kiểm tra, không gọi AI và không thay record thiếu bằng fixture.

Kết quả: [diagnostics ranking](diagnostics/7ed1928b4ee5444db0162d08a6af7c28.json).

- Tái dùng 2 keyword Trends × 93 điểm và 20 ASIN Amazon đã được chấp nhận; Reddit 0 bài. Valid ratio 22/22, phủ nguồn có record 2/3, không tự biến thành confidence kinh doanh 100%.
- Gate vẫn `insufficient`: Amazon là hub Best Sellers tổng, không phải supporting evidence cho niche Christmas; Reddit chưa có post. Snapshot này không đủ điều kiện tạo ranking, dù số đo Trends và ASIN là thật.
- `RankingService` trả `status=unavailable`, `ranking=[]`, một niche trong `unranked`; component score/contribution/confidence để null, không cố tạo hạng hoặc Top 3. Quan sát gốc vẫn tồn tại trong các snapshot trước, không bị gán số đo 0.
- Artifact giữ nguyên origin run ID/request ID/retrieved_at/source URL/cache flag và dẫn về [audit validation giai đoạn 6](../verification_phase06/diagnostics/ba0da4abf898429b9f4816722e73dd0a.json). Record/statistics đã validation được tái dùng, quality gate được áp dụng cho input ranking; không có HTTP trace mới giả.

Nguồn live gốc không thay đổi:

- Google Trends: [snapshot giai đoạn 3](../verification_phase03/diagnostics/fb7b49420fdd40c599abe64bfb35d8f4.json), geo US, thu thập 21/10/2026; 1 partial/keyword không tính metric.
- Amazon: [snapshot giai đoạn 4](../verification_phase04/diagnostics/cf2eb6447ebf4f6caefc724d1f7d70f7.json), 20 ASIN từ hub tổng; Search/Movers chưa có card phù hợp.
- Reddit: [snapshot giai đoạn 5](../verification_phase05/diagnostics/9f35f55a6a3445f993abbd279e797a47.json), connection_error/0 post; chưa xác minh OAuth/permalink live.

Có thể tái lập audit từ thư mục gốc repository khi cần, không phải collector runtime/cache thị trường:

    .venv\Scripts\python -B -m scripts.audit_ranking_phase07

Mỗi lần chủ động chạy audit sẽ tạo diagnostics mới với audit timestamp/run ID mới, nhưng không đổi thời điểm gốc trong evidence và không dùng snapshot như TTL cache hiện tại.

Kiểm thử cách ly của giai đoạn 7: 78 Python + 6 UI mới pass. Các nhóm mới được chạy riêng; một assertion nhầm confidence với mẫu Search 5/20 đã được sửa và chỉ chạy lại đúng ca fail. Không chạy lại full suite hoặc ca đã pass. Fixture chỉ nằm trong tests/thư mục tạm; không có trong dữ liệu audit này. Test chứng minh công thức/contract/nhánh lỗi, không thay cho bằng chứng nguồn thật.

Giới hạn: chưa xác minh ranking đủ năm nhóm trên một live run hoàn chỉnh; không chứng nhận nguồn hiện đang truy cập được, mọi URL còn mở được, mức liên quan ngữ nghĩa hoặc độ chính xác dự báo kinh doanh. Tham số ranking là heuristic minh bạch, không phải benchmark doanh số; Top 3 chờ validator claim/evidence AI giai đoạn 8. Xem [README công thức](../../README.md#ranking-có-breakdown--giai-đoạn-7).
