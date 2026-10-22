# Giai đoạn 11 — Snapshot collector trên dữ liệu thật đã lưu

[Diagnostics](diagnostics/5b83164ff7214ddfba9b3dcf460007e2.json) và [manifest](snapshots/5b83164ff7214ddfba9b3dcf460007e2/manifest.json) được tạo bằng `scripts/audit_snapshots_phase11.py`. Đây là **audit offline**, không phải live research run mới hoặc benchmark tốc độ mạng.

Input lấy từ audit giai đoạn 6, khôi phục chính request journal và record thật của Trends/Amazon/Reddit giai đoạn 3–5; không dùng fixture, response giả, collector thay thế hay đồng hồ giả. Kiểm tra lại contract trước khi ghi biên snapshot mới, không truy cập lại provider. Giữ nguyên toàn bộ evidence/request IDs, timestamps và dữ kiện nguồn.

- Lưu/đọc lại đúng **2 keyword Trends + 20 ASIN Amazon + 0 Reddit**, equality toàn collection JSON sau validation.
- Giữ đầy đủ time series/metrics, listing provenance và request/validation/warnings. File snapshot không phải HTTP/HTML nguyên xi, không chứa credential/cookie/body OAuth.
- Manifest-last ghi ba file theo source allowlist, byte count và SHA-256; reader đối chiếu schema/run/niche/source/path/count/size/checksum.
- Thử admit các collection archive bằng cache policy/đồng hồ thật: **cả ba không được nhận làm cache fresh** (quá tuổi hoặc không phải success sạch). Không thay timestamp để làm cache hit.
- **Network/provider calls: 0. AI calls: 0.** Không chạy pipeline research, không xuất Markdown/latest mới, không ghi đè cache/snapshot gốc.

Quality assessment gốc vẫn **insufficient**: Amazon từ Best Sellers hub tổng không đủ supporting evidence cho niche và Reddit không có bài. Audit không tạo record/idea hoặc số đo thị trường mới. SHA-256 phát hiện corruption, không xác thực provider hay ngăn người có quyền ghi thư mục sửa cả payload/manifest.

Phạm vi xác nhận là persistence/traceability trên archive thật. Không chứng nhận positive live Reddit OAuth, pipeline Ollama đủ evidence, accuracy production, quota phân tán hoặc mức tăng tốc thực tế. Concurrency/cache/timeout/storage failure và publication khi cache-hit được kiểm tra riêng bằng **79 fixture tests mới + 6 ca cũ bị ảnh hưởng**, không gọi các test fixture đó là dữ liệu nghiên cứu thật; không lặp test đã pass/full suite hoặc re-fetch provider.
