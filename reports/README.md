# Tình trạng các báo cáo

Các file `report_trend_20261020_*.md` và `latest_data.json` được tạo trước khi áp dụng chính sách dữ liệu thật. Chúng có thể chứa sản phẩm, thảo luận, metric và khuyến nghị từ fallback viết sẵn. Đây là **báo cáo legacy/demo, không dùng để nộp hoặc ra quyết định**.

Giữ các file này để đối chiếu lịch sử. `/api/latest` chỉ nhận cache `metadata.data_policy = live-only-v9` cùng canonical `research-result-v1`/checksum/Markdown/alias nhất quán; không tự nâng cache cũ. `/api/reports` liệt kê các file chính sách cũ riêng trong `legacy_reports`.

Báo cáo mới có dòng `<!-- data-policy: live-only-v9 -->`, bảng trạng thái nguồn, assessment của gate, phụ lục evidence/timestamp/request và link `diagnostics/RUN_ID.json`. Dòng này xác định phiên bản chính sách của luồng tạo báo cáo, không bảo đảm nguồn bên ngoài luôn hoạt động hoặc AI đã chứng minh market fit. Cache v1–v8 là lịch sử trước canonical publication v9; không đồng nghĩa tất cả chúng chứa dữ liệu demo/fallback.

Báo cáo `partial`/`failed` là kết quả chẩn đoán thực tế. Cần đọc các cảnh báo và quality gate trước khi sử dụng. Thư mục `verification_phase01/` lưu kết quả chạy thử nguồn thật khi kiểm tra giai đoạn 0–1; không phải bộ báo cáo mẫu hoàn chỉnh để nộp.

`verification_phase02/` lưu lần kiểm tra live giai đoạn 2: 6 HTTP attempt, 0 bản ghi; Trends trả 404, hai truy vấn Amazon trả 200 nhưng không có product card hợp lệ, Reddit lỗi kết nối sau 3 lần thử. Kết quả `failed`/`insufficient` được giữ nguyên, không có dữ liệu thay thế. File diagnostics lưu đầy đủ các attempt và hai lần retry Reddit; không lưu raw response body.

`verification_phase06/` là audit offline của các snapshot live giai đoạn 3–5, không phải lượt thu thập mới. Schema chấp nhận 22 record thật (2 Trends, 20 Amazon) nhưng gate insufficient: sản phẩm từ hub tổng không đủ evidence cho niche và Reddit không có bài. Không tự tạo record mới, không ghi đè snapshot gốc, không dùng fixture, không tạo report nghiên cứu/khuyến nghị từ audit này.

`verification_phase03/diagnostics/fb7b49420fdd40c599abe64bfb35d8f4.json` là lượt xác minh Trends sau sửa: 2 keyword thực, geo US, timeframe today 3-m; mỗi keyword 93 điểm và 1 partial không dùng tính metric. Có 6 HTTP attempt, một 429 hồi phục sau retry, status success. Google Suggest tắt trong lượt này để giảm request. File giữ cả series, metrics, cấu hình và trace gốc đã che token; không phải báo cáo toàn pipeline và không có dữ liệu giả.

Hai file chẩn đoán trước trong verification_phase03 ghi lỗi URL bootstrap 404 và lỗi đọc cờ partial bị lược bỏ; được giữ để đối chiếu quá trình sửa, không dùng làm kết quả cuối. Dữ liệu cache luôn ghi from_cache, giữ retrieved_at gốc; không được coi là một lần fetch mới.

Giai đoạn 4 lưu tại `verification_phase04/diagnostics/`:

- `cf2eb6447ebf4f6caefc724d1f7d70f7.json`: 3 request thật đều HTTP 200, 20 ASIN duy nhất từ Best Sellers tổng; Search/Movers không có card hợp lệ nên status partial. Thiếu price/rank/review vẫn null; có giá VND thì giữ VND, không quy USD. Đây là kiểm tra adapter, **không phải bằng chứng nhu cầu Christmas hoặc báo cáo khuyến nghị niche**.
- `f74ac24a823f44ddb660edeade4a63f7.json`: kiểm tra riêng hai trang chưa đọc được và một URL sản phẩm. Search 503 sau ba lần thử; Movers chỉ có hub; ASIN B07BGLT25K mở được, product title khớp record. Chỉ lưu trích đoạn văn bản nhìn thấy và thống kê DOM có giới hạn, không lưu raw HTML/cookie/token.
- `213bd739f5e04891b4c64a16a4c5080a.json`: Movers hub không có card sản phẩm; các link /dp/ trong footer là dịch vụ thẻ, không bị thu thập như market product.

Chưa xác minh thủ công cả 20 URL hoặc xác nhận mọi selector trên mọi danh mục/locale. Source HTML và quyền truy cập có thể thay đổi; không thay failure bằng mock data và không chạy lại các nguồn đã xác minh thành công trong lượt này.

`verification_phase09/` là audit đồng bộ publication trên chính các snapshot thật đã lưu, không phải live run mới: canonical ResearchResult duy nhất → Markdown/JSON/cache; 22 evidence có URL/timestamp/request gốc, kết quả vẫn insufficient và không có idea. Request trong bảng nguồn là lịch sử từ snapshot, không phải network I/O của audit. Xem [manifest và giới hạn](verification_phase09/README.md).

`verification_phase10/` là audit đọc chính publication giai đoạn 9 qua Web server loopback thật: 3 GET, không tạo job hoặc gọi provider/model. API giữ nguyên cache, timestamp, evidence và trạng thái insufficient; không biến defaults truy vấn trong form thành dữ kiện mới. Xem [manifest/phạm vi](verification_phase10/README.md); chưa có chứng nhận browser visual QA hoặc positive live job đủ nguồn.

`verification_phase11/` là audit snapshot tại biên collector (sau validation, trước processing) trên archive thật: 2 Trends + 20 ASIN + 0 Reddit, giữ ID/timestamp gốc, roundtrip đúng và không admit archive làm cache fresh. 0 network/AI, không tạo latest/report nghiên cứu mới, không có wire HTML/OAuth body. Xem [manifest/phạm vi](verification_phase11/README.md); không phải benchmark speedup hoặc chứng nhận live accuracy/positive full pipeline.

`verification_phase12/` giữ [audit/manifest/coverage/JUnit](verification_phase12/README.md): 67 test fixture mới pass, audit publication với snapshot thật (1219 numeric occurrences/625 structured numeric fields, 0 network/AI), không ghi lại research latest. Probe Reddit thật riêng vẫn HTTP 403/1 request/0 record; Trends/Amazon không refetch. Coverage chỉ từ bảy ca mới cuối trên mã chốt, không full suite. Acceptance live/OAuth/positive Ollama đủ evidence chưa đạt; không lấy fixture hoặc archive làm bằng chứng live mới.
