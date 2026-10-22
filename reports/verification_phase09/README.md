# Giai đoạn 9 — audit canonical publication trên dữ liệu thật đã lưu

Đây là audit **offline**, không phải một lần thu thập live mới hoặc báo cáo khuyến nghị thị trường. Không dùng fixture, mock collector hay model response giả. Chỉ tái sử dụng record đã validation ở giai đoạn 6 và request metadata thật trong các snapshot nguồn giai đoạn 3–5.

- [Markdown](report_trend_9e8b13a46039476a9584131f1933745a.md)
- [JSON/cache cùng publication](latest_data.json)
- [Diagnostics/nguồn gốc và checksum](diagnostics/9e8b13a46039476a9584131f1933745a.json)

Nguồn đầu vào: `../verification_phase06/diagnostics/ba0da4abf898429b9f4816722e73dd0a.json`. Manifest diagnostics liên kết các snapshot Trends `fb7b49420fdd40c599abe64bfb35d8f4`, Amazon `cf2eb6447ebf4f6caefc724d1f7d70f7` và Reddit `9f35f55a6a3445f993abbd279e797a47` cùng request IDs ban đầu. Timestamp/provenance của record không được thay bằng thời điểm audit.

Kết quả: 2 keyword Trends + 20 ASIN Amazon + 0 Reddit; 22 entry trong appendix evidence; `status=partial`, `data_quality=insufficient`, `mode=deterministic`, model không được gọi, không có ranking/idea/Top 3 giả. Amazon là Best Sellers hub tổng, không đủ evidence hỗ trợ niche; valid record không đồng nghĩa gate đạt.

Một ResearchResult được builder tập hợp, reporter và serializer sử dụng cùng object. Markdown file và `markdown_content` trong JSON khớp; repository đọc lại publication nguyên vẹn. Header ghi `execution_kind=offline_publication_audit`; cảnh báo/bảng nguồn nêu rõ request lịch sử, không phải request mới trong audit. Network requests và generation trong audit: **0**. Không ghi đè cache nghiên cứu chính ở reports/ hoặc snapshot gốc.

Mã chạy: `scripts/audit_publication_phase09.py`. Lần chạy đầu phát hiện khác biệt cấu trúc request metadata cũ (Reddit lưu list, hai nguồn kia lưu map); parser audit đã chuẩn hóa theo request ID, không sửa/tạo dữ kiện nguồn. Bản trình bày sau đó được xuất lại từ cùng snapshot/run ID khi bổ sung nhãn request lịch sử; không thu thập/scoring/AI lại.

Phạm vi chứng minh: đồng bộ canonical snapshot, JSON, Markdown, cache và khả năng giữ provenance của nhánh insufficient. Đây không phải xác minh lại khả năng truy cập provider, positive Ollama/live đầy đủ nguồn, dự báo kinh doanh hay market fit. SHA-256 phát hiện thay đổi nội dung, không xác thực người ghi/provider. API loopback roundtrip được kiểm tra riêng bằng dữ liệu test cách ly, không được gọi là kiểm chứng live dữ liệu nghiên cứu.
