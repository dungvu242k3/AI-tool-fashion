# Giai đoạn 12 — Kiểm thử và audit dữ liệu

[Manifest tổng hợp](manifest.json) giữ kết quả cuối theo từng node test, JUnit từng lượt kể cả fail/skip, artifact/source hashes và scope coverage. Triển khai công cụ hoàn tất; **acceptance live chưa đạt**, không gọi đây là chứng nhận production hoặc chuyển sang giai đoạn 13.

## Kết quả kiểm thử cách ly

**67 test mới pass** qua bốn nhóm: 38 audit + 14 verification integration + 8 security + 7 final boundary. Fixture/HTTP/AI doubles chỉ trong tests/tmp, không được dùng làm dữ liệu nghiên cứu. Không chạy full suite, test cũ đã pass hoặc UI; không refetch Trends/Amazon.

Hai ca codec ban đầu trả CollectionError thay vì AuditFailure đã được sửa và retry đúng hai node; một ca symlink đã fail-closed đúng nhưng assertion code quá cụ thể theo platform, được sửa và retry đúng node. Không lặp test đã pass. Tổng lịch sử unit 70 lần thực thi cho 67 ca riêng biệt; không che các failure ban đầu.

Các nhóm kiểm chứng mới gồm snapshot schema/ownership/count/secret/size bounds, raw record/request matching, calculation/quality/currency/custom ranking policy, Markdown/JSON/file thực, cache/historical flags/multi-niche và positive/failed AI output fixture. Adversarial tests rehash publication/manifest sau khi sửa claim/metric/text, nhưng không đổi nguồn tương ứng: auditor vẫn từ chối. Test không dựa vào việc checksum đơn thuần phải fail.

## Audit trên dữ liệu thật, không gọi mạng

[Diagnostics audit](diagnostics/5e6305a72429435f8b8e7086fe418d9d.json) đọc [publication giai đoạn 9](../verification_phase09/latest_data.json) và [snapshot giai đoạn 11](../verification_phase11/snapshots/5b83164ff7214ddfba9b3dcf460007e2/manifest.json), được tạo từ record/request thật giai đoạn 3–5. Không fixture, collector thay thế, model giả hoặc đổi thời điểm nguồn.

- Đối chiếu **2 keyword Trends + 20 ASIN Amazon + 0 Reddit**, exact raw record/provenance/journal và dữ liệu suy ra.
- **1.219 numeric occurrences** trong toàn Markdown, gồm số Unicode, ID/URL/date/template/source text; giữ line/column và section reference. **625 structured numeric fields** có JSON Pointer.
- Recompute TrendMetrics qua validator; quality/health/price/ranking theo policy và summary; dựng lại sections. AI branch có cơ chế đối chiếu catalog/facts/quotes/proposals nhưng archive này không đủ gate và không có positive AI để audit.
- Research vẫn **partial / insufficient**, Amazon hub tổng không trở thành niche evidence, ranking/ideas rỗng. **0 network / 0 AI**, không publish lại report/latest hoặc sửa snapshot gốc.

Lệnh mặc định `python -B -m scripts.audit_publication_phase12` dùng đúng archive ở trên. Với run mới, truyền `--publication`, `--snapshots`, `--snapshot-run-id`, `--output`; CLI exit 1 khi fail và lưu diagnostics lỗi an toàn. Kiểm tra chỉ đọc không repair báo cáo.

Audit xác nhận **consistency với snapshot**, không phải chứng thực dữ liệu provider/market fit/độ mới hiện tại. Hàm tính toán production được dùng lại để verification, nên không độc lập phát hiện mọi lỗi công thức chung. Không có wire HTML hoặc raw rejected candidates để replay; validation counts chỉ reconcile. Claim số trong section phải tái dựng khớp, còn số trong metadata/input/warning/source quote được phân loại, không tự chứng nhận ý nghĩa thị trường. Ledger không phải semantic truth oracle. Checksum không phải chữ ký; bảo vệ quyền ghi thư mục output.

## Integration nguồn thật

Ba case thật trong `tests/live/test_providers_live.py` mặc định skip; không có mock fallback. Chỉ source chọn bằng `--live-provider` mới được gọi mạng; unit tests bên ngoài vẫn chặn outbound. Probe budgets nhỏ, tắt cache/AI, lấy query từ config, không nhận URL tùy ý, không ghi latest.

Trends/Amazon không chọn lại vì đã kiểm tra lịch sử; kết quả cũ ở diagnostics giai đoạn 3–4 không phải xác minh code/mạng hiện tại. Reddit trước đó fail nên được chọn đúng **một lượt**:

[Diagnostics Reddit thật](live/diagnostics/c1d491b84ed44a42adc846128b22b202.json): **22/10/2026, HTTP 403, 1 network request, 0 record**, provider public JSON vì không có OAuth credential. Test live **fail**, không retry tự động, không chuyển cache/mock hoặc tìm cách vượt chặn nguồn. Test không chọn skip; thiếu mạng hoặc zero record ở test đã chọn sẽ fail rõ ràng.

Còn thiếu acceptance: quyền truy cập Reddit hợp lệ/OAuth và xác minh post/permalink thật, positive live pipeline Ollama đủ evidence. Không tạo dữ liệu để đạt gate và không tuyên bố OAuth pass. Cần thay đổi điều kiện truy cập trước khi kiểm tra tiếp; không lặp request thất bại liên tục.

## Coverage thực đo, không full suite

Tool **coverage.py 7.16.2**, cấu hình `.coveragerc` branch/thread, denominator toàn `src`. [JSON report](coverage/coverage.json) được tạo từ `.coverage-current`: **chỉ 7 test final-source mới + retry đúng ca symlink fail** trên cùng mã nguồn chốt, không chạy lại ca pass để đo.

| Chỉ số | Đo được |
|---|---:|
| Statements/line | 3096 / 4715 — 65.66% |
| Branches | 671 / 1532 — 43.80% |
| Combined coverage.py | 60.30% |

Đây **không phải full-suite coverage hoặc coverage của toàn bộ 67 test**. `.coverage-audit` chứa lịch sử các đợt khi mã còn thay đổi, không dùng để tính tỷ lệ công bố. Live Reddit và audit archive không nhập vào tỷ lệ fixture tests này. Giữ dữ liệu/JUnit để đọc lại; chỉ cần `coverage report --data-file=reports/verification_phase12/coverage/.coverage-current`, không cần chạy lại test.

Chưa áp coverage gate hoặc công bố production readiness. `requirements-dev.txt` tách công cụ coverage khỏi runtime dependencies; không thay đổi chính sách collector/quality/ranking/AI của pipeline ở giai đoạn này.
