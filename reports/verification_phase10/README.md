# Giai đoạn 10 — Web đọc publication thật qua loopback

[Manifest](diagnostics/dd95abc54f5b4f7691e633dd41ab2fd0.json) lưu audit **chỉ đọc**, không phải một live research job mới. Mã chạy: `scripts/audit_web_phase10.py`.

Input là [publication giai đoạn 9](../verification_phase09/README.md), run `9e8b13a46039476a9584131f1933745a`, đã chứa snapshot thật và request/timestamp nguồn giai đoạn 3–5. Không dùng fixture, collector thay thế, response giả hoặc model response mock.

Server Web thực chạy tại loopback/port tạm; audit đọc đúng ba endpoint: `/api/config`, `/api/latest`, `/api/jobs/active`. Cả ba HTTP 200/no-store. Config trả Ollama mặc định và giới hạn 5 niche; đây là **thiết lập truy vấn**, không phải 3 niche đã có market evidence. Token CSRF không được lưu trong manifest.

`/api/latest` trả nguyên canonical publication đã lưu: 2 keyword Trends, 20 ASIN Amazon, Reddit 0; 22 evidence giữ URL/retrieved_at/request gốc; `status=partial`, quality insufficient; ranking/ideas vẫn rỗng. Checksum và bytes cache trước/sau không thay đổi. Amazon từ hub tổng không được nâng thành bằng chứng phù hợp niche.

- Loopback HTTP requests: **3**.
- Provider requests / model generation / research jobs started: **0 / 0 / 0**.
- Không ghi đè cache nghiên cứu chính hoặc snapshot gốc.
- Biên đọc cache vẫn kiểm tra canonical consistency; không chạy lại validator collection/quality/ranking hay xác minh lại nguồn live.

Phạm vi chứng minh: tương thích và giữ nguyên dữ kiện thật khi Web mới đọc archive. Không chứng minh hoạt động nguồn/OAuth mới, positive job Ollama đủ dữ liệu, browser visual QA hay market fit. Async job/form/tab/reconnect/security được kiểm tra riêng bằng test cách ly; không gọi các test đó là kiểm chứng live dữ liệu nghiên cứu. Job in-memory và local-only, không phải durable/distributed/public multi-user service.
