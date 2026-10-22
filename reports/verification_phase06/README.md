# Kiểm chứng giai đoạn 6 — validation và quality gate

Đây là audit offline trên dữ liệu live thật đã lưu, không phải lượt thu thập live mới hoặc báo cáo khuyến nghị. Số request mạng mới trong audit: 0.

Nguồn gốc giữ nguyên:

- Trends: `../verification_phase03/diagnostics/fb7b49420fdd40c599abe64bfb35d8f4.json` — 2 keyword × 93 điểm, geo US, thu thập 21/10/2026. Timestamp, partial flag, metric và request ID không được thay bằng dữ liệu fixture.
- Amazon: `../verification_phase04/diagnostics/cf2eb6447ebf4f6caefc724d1f7d70f7.json` — 20 ASIN từ hub Best Sellers tổng; Search/Movers chưa có card phù hợp.
- Reddit: `../verification_phase05/diagnostics/9f35f55a6a3445f993abbd279e797a47.json` — lỗi kết nối, 0 post; chưa có credential để kiểm chứng OAuth live.

Kết quả:

- Schema/provenance/metric chấp nhận 2 keyword Trends và 20 ASIN, không phải mọi card/record của nhà cung cấp. valid_ratio = 22/22; phủ nguồn có record = 2/3 nguồn được cấu hình.
- Gate = insufficient, qualifying_keyword_count = 2, supporting_record_count = 0. Hub Amazon tổng không đủ evidence bổ sung cho niche Christmas; Reddit không có post. Tỷ lệ schema hợp lệ 100% không tự biến thành chất lượng sufficient hoặc confidence kinh doanh 100%.
- Không gọi AI, không tạo ý tưởng/ranking/report thị trường, không sửa snapshot gốc. is_live trong provenance chỉ nguồn gốc của lần thu thập cũ, không có nghĩa audit vừa fetch lại hay dùng lại snapshot như TTL cache hiện tại.
- [Diagnostics audit](diagnostics/ba0da4abf898429b9f4816722e73dd0a.json) lưu liên kết snapshot/run ID/request ID/thời điểm gốc và các view raw_metric/derived_metric.

Kiểm thử riêng: 128 test Python mới + 2 ca bị ảnh hưởng và 4 test UI mới pass. Lượt đầu có lỗi fixture thiếu URL; chỉ chạy lại 91 ca chưa pass, giữ nguyên 15 ca đã pass. Không chạy lại toàn suite hoặc các kiểm tra live đã pass. Fixture chỉ nằm trong tests/ và thư mục tạm của test, không nằm trong audit này.

Giới hạn: audit không chứng nhận nguồn đang truy cập được, không xác minh toàn bộ URL sản phẩm/post, không kiểm định ngữ nghĩa tất cả claim AI. Ranking và validator AI toàn phần vẫn chờ giai đoạn 7–8.
