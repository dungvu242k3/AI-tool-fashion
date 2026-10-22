# Kế hoạch nâng cấp AI Product Trend Research Tool

## 1. Mục tiêu

### Trạng thái triển khai cập nhật ngày 22/10/2026

Trạng thái hiện tại: đã có mã/công cụ giai đoạn 0–12, chi tiết từng mục bên dưới. **Acceptance live giai đoạn 12 vẫn chưa đạt**: Reddit public JSON HTTP 403/1 request/0 record, chưa có OAuth và positive live Ollama đủ evidence. Giai đoạn 13 chưa làm. Các ghi chú giai đoạn 0–8 bên dưới là lịch sử tại thời điểm triển khai, không phải trạng thái dừng hiện tại.

- Giai đoạn 0: đã bổ sung regression tests; 12 trường hợp ban đầu đều fail trên code cũ rồi pass sau khi sửa. Baseline cũ là 19 test pass, chưa đo coverage.
- Giai đoạn 1: đã xóa fallback market data, metric mặc định và metadata giả khỏi runtime.
- Giai đoạn 2: đã chuẩn hóa `CollectionResult[T]`, warning có cấu trúc, HTTP transport dùng chung chính sách timeout/retry, provenance từng record và source health theo niche/toàn run. Collector chỉ nhận record liên kết được tới request thành công; diagnostics được ghi nguyên tử trước bước xử lý/AI.
- Giai đoạn 3: đã tách `TrendsProvider`/pytrends adapter, lưu series đầy đủ, tính metric bằng hàm thuần, ngưỡng cấu hình, Google Suggest riêng và cache RAM TTL/LRU có giới hạn. Cache giữ nguồn/thời điểm cũ, không ghi request mới giả; input/JSON/cache bị giới hạn và chuỗi ngoài được escape khi render.
- Kiểm tra live giai đoạn 3: đã sửa URL bootstrap bỏ slash cuối. Lượt cuối lấy được 2 keyword × 93 điểm thật, loại 1 partial/keyword khỏi metric; 6 HTTP attempt gồm một 429 đã retry thành công. Google Suggest tắt ở lượt xác minh này. Dữ liệu/trace: `reports/verification_phase03/diagnostics/fb7b49420fdd40c599abe64bfb35d8f4.json`. Các lượt chẩn đoán trước được giữ riêng, không dùng thay kết quả cuối.
- Kiểm thử giai đoạn 3: 45 test mới + 8 test Trends bị ảnh hưởng và 1 test UI mới pass. Không chạy lại toàn bộ test cũ hoặc nguồn Amazon/Reddit.
- Giai đoạn 4: đã tách request settings/parser/value validation cho Amazon; hỗ trợ nguồn Search/Best Sellers/Movers theo URL và nội dung thật; ASIN dedup giữ listing provenance, snapshot giá/rating không bị ghép giữa request. Sponsored mặc định bị loại; tiền tệ giữ nguyên, nhóm khoảng giá theo currency, không FX. Contract v4 từ chối record thiếu ASIN/listing hoặc dữ kiện/provenance sai; không có bypass legacy trong validation.
- Giai đoạn 5: đã tách Reddit settings/provider/parser/validation; ưu tiên OAuth app-only, public JSON chỉ khi không có credential hoặc chọn tường minh; không downgrade khi OAuth lỗi. Truy vấn toàn bộ subreddit × seed trong ngân sách, dedup post ID giữ snapshot đầu tiên, lọc created_utc, giữ selftext/permalink/score/comment thật. Trích dẫn ứng viên pain point phải có Reddit evidence ID và nguyên văn; phần phân tích cộng đồng tự do không được xuất khi chưa kiểm định.
- Kiểm thử giai đoạn 5: 145 test Python mới + 3 test Reddit bị thay đổi và 2 test UI mới pass; chỉ chạy lại ba ca AI bị fail do fixture chưa đủ gate, không chạy toàn bộ test cũ. Đã kiểm tra redirect/credential/.netrc, OAuth refresh hữu hạn, input/query/JSON có giới hạn, post/date/count/provenance và pain-point contract.
- Live giai đoạn 5: public JSON r/giftideas × christmas gift ideas, 2 attempt connection_error, failed/0 post; chưa có credential nên chưa kiểm tra OAuth, score/comment/permalink live. Không tạo bài thay thế hoặc báo cáo thị trường. Xem `reports/verification_phase05/diagnostics/9f35f55a6a3445f993abbd279e797a47.json`; acceptance live vẫn chưa đạt, không coi unit test là dữ liệu thật.
- Giai đoạn 6: đã bổ sung schema/provenance boundary có giới hạn, validation Trends và metric tính lại, thống kê candidate/valid/rejected/duplicate/retained, dedup chung theo keyword+geo+timeframe / ASIN / post ID. Processor copy sâu, giữ nguyên số đo/thứ tự và không fallback identity bằng title; raw_metric/derived_metric tách riêng, cache lên live-only-v6.
- Gate giai đoạn 6: cần hai keyword khác nhau có series hợp lệ cùng geo/timeframe và một nguồn bổ sung đã validation; hub Amazon tổng không được tính như niche evidence. Context phải khớp snapshot cả kiểu dữ liệu; digest phát hiện thay đổi sau đánh giá. Source coverage/valid ratio có mẫu số công khai, mẫu rỗng/thiếu thống kê để null, không tự reweight/confidence giả. Niche không đạt gate không gọi AI, không có idea, được nhóm Dữ liệu chưa đủ trong report/UI.
- Kiểm thử giai đoạn 6: 128 test Python mới + 2 ca bị ảnh hưởng và 4 test UI mới pass. Lượt đầu lỗi fixture thiếu URL; chỉ chạy lại 91 ca chưa pass, không lặp 15 ca đã pass. Các ca bổ sung chạy riêng, gồm metadata warning/thời gian cấp collection và credential trong query record; không full suite, không kiểm tra lại provider live đã pass.
- Audit giai đoạn 6 dùng snapshot live thật giai đoạn 3–5, không gọi mạng: 2 Trends + 20 ASIN hợp lệ, Reddit 0. Valid ratio 22/22 và source coverage 2/3 nhưng gate vẫn insufficient vì Amazon là hub tổng/Reddit thiếu evidence. Lưu origin timestamp/request ID, không xuất khuyến nghị: `reports/verification_phase06/diagnostics/ba0da4abf898429b9f4816722e73dd0a.json`.
- Giai đoạn 7: đã tách policy có version/hash, công thức thuần cho 5 component và một RankingService dùng chung. Chỉ score snapshot qua gate/còn khớp digest; thiếu component để null, không reweight, lưu observed contribution/tổng đủ nhóm/cận trên/coverage/confidence dữ liệu. Context Trends không khớp thì unranked; recent interest chỉ so khi dùng chung một request chuẩn hóa, không so score 0–100 giữa các batch riêng.
- Ranking giai đoạn 7 phân biệt rating có hỗ trợ review, tương tác Reddit và rào cản review mẫu organic Search với doanh số/cạnh tranh toàn thị trường. Sponsored/hub tổng/scalar snapshot chính không hợp scope bị loại khỏi score; thiếu số đo không điền 0. Tie-break bằng metric thật; khóa bằng nhau đồng hạng, tên chỉ ổn định hiển thị. Heuristic chưa được kiểm định bằng kết quả kinh doanh; confidence không phải xác suất thành công.
- Kiểm thử giai đoạn 7: 78 test Python mới + 6 test UI mới pass. Chạy các nhóm mới riêng, không chạy lại full suite/ca đã pass. Assertion cuối nhầm confidence khi Search chỉ phủ 5/20 primary được sửa và chỉ chạy lại đúng một ca fail. Markdown/JSON/UI/diagnostics dùng cùng ranking_assessment; cache lên live-only-v7. Có giới hạn input/precision, JSON-safe/null/zero, policy invalid, context mismatch, Sponsored/primary scope và XSS.
- Audit giai đoạn 7 tái dùng record/statistics đã validation ở audit 6, không fetch/kiểm tra lại provider: 2 keyword Trends + 20 ASIN, Reddit 0; gate vẫn insufficient và ranking unavailable/0 niche được xếp, không tạo idea hoặc dữ liệu thay thế. Giữ nguồn/request ID/thời điểm gốc tại `reports/verification_phase07/diagnostics/7ed1928b4ee5444db0162d08a6af7c28.json`; không tuyên bố đã xác minh ranking đầy đủ bằng dữ liệu live đủ mọi nhóm.
- Giai đoạn 8: đã thay Markdown parser bằng JSON schema đóng dùng chung cho Ollama/local validator. Catalog chỉ nhận snapshot qua gate/còn khớp digest; fact phải đúng metric/value ở mọi evidence dẫn, quote phải nguyên văn trong context đã gửi, idea phải có basis đóng và nhãn đề xuất. why_now do server dựng, không nhận claim tài chính/market/rank/URL tự do. Context sampling có cap/count/ID công khai, không cắt dữ liệu nguồn hoặc thay ranking.
- Giai đoạn 8 bổ sung tối đa một lượt repair, lỗi vẫn fail-closed về dữ kiện, không có ý tưởng mặc định. Client loopback, request/body/deadline hữu hạn, không redirect/ambient auth/proxy/.netrc, chặn tên cloud thông dụng và không log output sai. Summary nhận facts/quotes/ranking reference/ideas đầy đủ, chọn tối đa ba slot nghiên cứu theo policy công khai, không tạo idea score hoặc tuyên bố đã chứng minh market fit. Cache lên live-only-v8; ResearchResult toàn run vẫn là dict hiện có.
- Kiểm thử giai đoạn 8: 210 test Python mới + 9 ca bị ảnh hưởng và 6 test UI mới + 1 ca UI bị ảnh hưởng pass. Chạy từng nhóm mới, chỉ chạy lại một ca summary fail sau khi sửa thứ tự metadata ideas, không lặp 58 ca cùng nhóm đã pass/full suite. Fixture/AI response cách ly trong tests, không dùng làm dữ liệu nghiên cứu hoặc bằng chứng acceptance live.
- Audit giai đoạn 8: tái dùng 22 record live đã validation, Reddit 0, thiếu supporting evidence nên insufficient_data/deterministic, 0 generation và không có idea/Top 3. Không gọi lại provider hay gửi snapshot cũ tới model: `reports/verification_phase08/diagnostics/204ac00306bf48ac98d3823250925b18.json`. Chưa có positive end-to-end grounded generation trên một live run đủ evidence; không biến việc pass unit test thành xác nhận khả năng nghiên cứu thị trường.
- Kiểm thử giai đoạn 4: 76 test Python mới và 1 test UI mới pass; chỉ chạy phần mới/chưa pass. Live Amazon: 20 ASIN từ Best Sellers tổng, 3 HTTP 200, partial do Search/Movers chưa có card. Kiểm tra riêng trang lỗi: Search 503 sau retry, Movers là hub không có listing; URL ASIN B07BGLT25K mở được và title khớp. Xem `reports/verification_phase04/`; chưa xác minh toàn bộ 20 URL và không coi dữ liệu hub tổng là evidence cho niche Christmas.
- Kiểm tra live giai đoạn 2: 6 HTTP attempt, Trends 404; Amazon 2 response 200 nhưng không có product card hợp lệ; Reddit lỗi kết nối sau 3 lần thử. Kết quả `failed`/`insufficient`, 0 record, không tạo dữ liệu thay thế. Xem `reports/verification_phase02/` và file diagnostics đi kèm.
- Gate score/URL giai đoạn 1 đã được thay bằng gate series/provenance giai đoạn 6; không có legacy bypass để mở AI bằng số đo rời. Nguồn lỗi vẫn có chẩn đoán và không được trình bày như đã hoàn tất đầy đủ.
- Đã tách phần render dữ kiện, kiểm tra điều kiện dữ liệu và lưu cache thành các module riêng; pipeline nhận collector dependencies để kiểm thử độc lập.
- Web/CLI ghi đúng chế độ; `--fast` chỉ thu thập thật và tổng hợp dữ liệu, không gọi LLM. Web mặc định yêu cầu Ollama và có checkbox chọn không AI.
- Đã đánh dấu 10 báo cáo cũ là LEGACY/DEMO; API từ chối cache cũ. Nội dung lịch sử được giữ để đối chiếu.
- Ranking cũ đã được thay bằng heuristic có breakdown của giai đoạn 7; grounded JSON/claim-source validator giai đoạn 8 đã triển khai. Top 3 chỉ có khi có đề xuất grounded từ niche được xếp hạng, không còn chờ triển khai nhưng vẫn rỗng nếu dữ liệu/AI chưa đủ điều kiện.
- Chạy thử live một niche: Trends trả 429, Amazon trả 503, Reddit từ chối kết nối. Kết quả đúng là `failed`, `insufficient`, 0 keyword/product/discussion, không gọi LLM, không tạo ý tưởng. Xem `reports/verification_phase01/`.
- Kiểm tra giai đoạn 0–1: 83 test Python và 4 test giao diện pass; kiểm tra cú pháp của ba module JavaScript pass. Giai đoạn 2: 151 test Python đã pass; 5 test mới cho các chỉnh sửa cuối cũng pass (provenance hỏng, độc lập metadata từng record, Reddit record lỗi, che token JSON và giữ diagnostics khi phân tích lỗi). Không chạy lại các test đã pass theo yêu cầu. Dữ liệu fixture chỉ nằm trong bộ test, HTTP bên ngoài bị chặn trong unit tests; integration HTTP chỉ mở server loopback.
- Tại mốc giai đoạn 8, chưa triển khai các phần sau. Hiện ResearchResult/Web job/concurrency/audit đã có ở giai đoạn 9–12; acceptance live Reddit và positive live AI vẫn chưa hoàn tất. Audit archive không thay thế xác minh live.

Nâng cấp MVP hiện tại thành công cụ nghiên cứu xu hướng có thể kiểm chứng:

- Chỉ dữ liệu live thu thập từ nguồn thật mới được dùng làm bằng chứng.
- Không sử dụng mock data, số liệu mẫu, URL giả hoặc fallback viết sẵn trong báo cáo.
- Nguồn lỗi phải được ghi là `failed`/`partial`, không được tự tạo dữ liệu thay thế.
- Mọi số liệu và kết luận phải truy ngược được tới URL, query và thời điểm thu thập.
- Markdown, JSON và Web UI phải dùng chung một kết quả và một bảng xếp hạng.
- Metadata phải ghi đúng chế độ thực thi và model thực sự được sử dụng.

## 2. Chính sách dữ liệu bắt buộc

1. Runtime không được chứa danh sách sản phẩm, rating, review, upvote, comment, trend score hoặc market claim giả lập.
2. Không được dùng giá trị mặc định có vẻ như dữ liệu thật, ví dụ `$24.99`, rating `4.5`, `850 reviews`, trend `rising` hoặc score `85`.
3. Trường không lấy được phải là `null`, danh sách rỗng hoặc `unavailable`.
4. Google Suggest chỉ là gợi ý truy vấn, không phải bằng chứng từ khóa đang tăng.
5. Amazon Search không được ghi nhãn là Best Sellers hoặc Movers & Shakers.
6. LLM không được tạo thêm số liệu; mọi claim định lượng phải có evidence ID hợp lệ.
7. Báo cáo mẫu để nộp phải được tạo từ live run, có timestamp và snapshot dữ liệu nguồn.
8. Fixture kiểm thử chỉ được nằm trong `tests/`, không bao giờ được đi vào runtime hoặc báo cáo.

## 3. Kiến trúc mục tiêu

```text
User input / Config
        |
        v
Live source collectors ---> Raw evidence snapshots
        |                         |
        v                         v
Validation + provenance + source health
        |
        v
Normalized evidence records
        |
        +----> Deterministic metrics + ranking
        |
        +----> Grounded LLM analysis
        |
        v
Canonical ResearchResult
        |
        +----> Markdown
        +----> JSON cache
        +----> Web dashboard
```

Nguyên tắc thiết kế:

- Collector chỉ lấy và parse dữ liệu.
- Processor validate, normalize, deduplicate và tính metric có công thức rõ ràng.
- Analyzer chỉ diễn giải evidence, không tự tạo evidence.
- Ranking chỉ tồn tại tại một service.
- Reporter và Web chỉ render cùng một `ResearchResult`.
- Dependency được truyền qua constructor để dễ kiểm thử.

## 4. Schema dữ liệu cần bổ sung

### 4.1. SourceStatus

Các trường cần có:

- `source`: tên nguồn chính xác.
- `status`: `success`, `partial`, `failed` hoặc `not_configured`.
- `fetched_at`: thời điểm gọi nguồn.
- `request_url`: URL request nếu có.
- `record_count`: số record hợp lệ.
- `error_code` và `error_message`: lỗi đã làm sạch.
- `is_live`: xác nhận đây là dữ liệu live.

### 4.2. Evidence metadata

Mỗi keyword, sản phẩm và discussion phải có:

- `evidence_id`.
- `source` và `source_url`.
- `query` đã sử dụng.
- `retrieved_at`.
- `is_live`.
- `raw_snapshot_path` nếu lưu snapshot.
- `confidence` tính theo độ đầy đủ của record.

### 4.3. RunMetadata

Các trường cần có:

- `run_id`, `started_at`, `completed_at`.
- `category`, danh sách niche.
- `mode`: `ollama` hoặc `deterministic`.
- `model_name`: `null` nếu model không thực sự được gọi.
- `source_statuses`.
- `data_quality`: `sufficient`, `partial` hoặc `insufficient`.
- `warnings`.

## 5. Kế hoạch triển khai từng giai đoạn

### Giai đoạn 0 — Khóa hành vi sai bằng test

1. Thêm test: collector lỗi không được trả market data hard-code.
2. Thêm test: trường Amazon thiếu không nhận giá/rating/review mặc định.
3. Thêm test: Google Trends lỗi không tạo `rising` hoặc score giả.
4. Thêm test: report không ghi Ollama nếu chạy deterministic mode.
5. Thêm test: pipeline không trả `success=true` khi toàn bộ nguồn bắt buộc thất bại.
6. Ghi nhận baseline hiện tại: 19 test pass nhưng chưa có số coverage được chứng minh.

Điều kiện hoàn thành:

- Test mới phải fail với code cũ và pass sau khi sửa.
- Báo cáo cũ có fallback phải được đánh dấu legacy/demo, không dùng làm báo cáo nộp.

### Giai đoạn 1 — Xóa mock và fallback khỏi runtime

1. Xóa `_get_fallback_products()` khỏi luồng runtime.
2. Xóa `_get_fallback_discussions()` khỏi luồng runtime.
3. Xóa Google Suggest tự tạo như `best {keyword} 2026`.
4. Xóa analysis, product ideas, ranking và số liệu viết sẵn trong `LLMAnalyzer`.
5. Xóa metadata giả trong `/api/latest` như 16.5 giây, 15 keyword, 24 product.
6. Thay fallback bằng `CollectionResult` có trạng thái lỗi.
7. Đổi metric không parse được thành `None`.
8. Không tạo báo cáo “thành công đầy đủ” nếu dữ liệu không đạt quality gate.

Điều kiện hoàn thành:

- `src/` không còn URL nguồn giả hoặc số liệu thị trường mẫu.
- Tắt mạng rồi chạy phải nhận kết quả failed/partial, không nhận báo cáo xu hướng hoàn chỉnh.

### Giai đoạn 2 — Chuẩn hóa collector contract và provenance

- [x] Tạo `CollectionResult[T]` gồm `records`, `status`, `warnings`, `request_metadata`.
- [x] Cập nhật `BaseCollector.collect()` trả `CollectionResult` thay vì list.
- [x] Lưu URL, status code, query và timestamp của mỗi HTTP attempt, kể cả retry/redirect.
- [x] Dùng connect timeout và read timeout riêng; cấu hình qua biến môi trường.
- [x] Retry có giới hạn cho `429`, `500`, `502`, `503`, `504`.
- [x] Dùng exponential backoff có jitter, tôn trọng `Retry-After` và ngân sách chờ/cooldown.
- [x] Không retry lỗi parse hoặc lỗi 4xx không tạm thời.
- [x] Loại các `except Exception: []` và lưu warning có cấu trúc, không ghi credential/cookie/body vào diagnostics.
- [x] Pipeline tổng hợp source health cho từng niche và toàn run; report/JSON/UI hiển thị cùng kết quả.

Điều kiện hoàn thành:

- [x] Mỗi record có evidence ID, nguồn, URL, query, timestamp và request ID chính/phụ; chỉ liên kết request 2xx không lỗi.
- [x] Lỗi nguồn không bị nuốt và không được trình bày như thành công; record thiếu provenance bị loại.
- [x] Lưu diagnostics theo run ID ngay sau thu thập; từ chối cache v1 không có contract provenance v2.

Chưa bao gồm raw snapshot, metric/time series mới, ranking hoặc validator claim AI; các phần này giữ nguyên lịch ở giai đoạn sau.

### Giai đoạn 3 — Sửa Google Trends

- [x] Giữ pytrends 4.9.2 sau interface `TrendsProvider`; logic parse/provider không trộn vào phép tính.
- [x] Batch tối đa 5 keyword, thứ tự xác định, khử seed trùng và lưu nhóm so sánh.
- [x] Lưu đầy đủ timestamp/value/is_partial, giữ điểm partial nhưng không tính vào metric, không nội suy số thiếu.
- [x] Tính `recent_mean`, `previous_mean`, `growth_percent`, `slope`, `volatility`; lưu cửa sổ, ngưỡng và phiên bản công thức. Baseline 0 không tạo tỷ lệ vô hạn.
- [x] Phân loại rising/stable/declining từ hai cửa sổ bằng nhau và ngưỡng cấu hình; thiếu dữ liệu trả unavailable.
- [x] Không cộng 15 điểm cho rising (đã gỡ từ giai đoạn 1); score luôn là điểm thật cuối kỳ hoàn tất.
- [x] Google Suggest thật nằm trong `suggestions`, có request provenance riêng, không tham gia tính metric/classification.
- [x] URL kiểm chứng chứa keyword, timeframe và geo; endpoint gọi nguồn cố định, input có giới hạn.
- [x] Hết retry 429 mà không có record trả failed; nếu batch trước thành công thì giữ partial. Không khởi động batch tiếp khi nguồn còn bị rate-limit.
- [x] Cache batch live đã chuẩn hóa trong RAM: TTL/LRU/giới hạn dung lượng, khóa đồng bộ, copy độc lập, không cookie/token/body; không dùng expired/stale làm fallback.

Điều kiện hoàn thành:

- [x] Mỗi kết luận tăng/giảm/ổn định được tính từ time series thật, có timestamp/window và công thức kiểm chứng.
- [x] Suggest được ghi nhãn riêng trong JSON/Markdown/UI, không trình bày như growth signal.

Chi tiết công thức, giới hạn, cấu hình và cache provenance nằm trong README. Policy lên `live-only-v3`; không thực hiện giai đoạn 4, ranking, distributed cache, raw snapshot hay grounded AI validator.

### Giai đoạn 4 — Sửa dữ liệu Amazon

- [x] Phân biệt Search Results/Best Sellers/Movers trong request, record và listing; URL ranking cấu hình tường minh, không chọn danh mục giả.
- [x] Chỉ ghi nhãn sau response 2xx, URL cuối và heading đúng loại; nhận diện captcha/trang lỗi không trả record.
- [x] Search position không được đưa vào bestseller rank; Movers listing_rank tách riêng, không tự lấy thứ tự DOM làm rank.
- [x] Đọc ASIN từ card/link, từ chối xung đột, deduplicate bằng ASIN; giữ các listing và request provenance riêng.
- [x] Sponsored mặc định bị loại trên cả ba nguồn; có cấu hình giữ nhưng phải gắn cờ và hiển thị rõ.
- [x] Parser title/price/rating/review/position/URL độc lập, giới hạn số card/HTML, không chạy JS.
- [x] Giá trị thiếu/sai định dạng để None, không bổ sung metric mẫu hoặc ép số đếm rút gọn thành số giả.
- [x] URL canonical /dp/ASIN cùng marketplace, không follow link tùy ý/tracking.
- [x] Validate rating 0–5, review không âm/JSON-safe, currency và Decimal string; validate cả listing/provenance trước processor.
- [x] Không quy đổi VND/USD hay suy currency ISO từ ký hiệu $.
- [x] Giữ currency gốc và tách khoảng giá theo currency; không triển khai quy đổi FX vì chưa có yêu cầu.
- [x] Block/captcha/403 hoặc hết retry 429 dừng request tiếp theo; nguồn không đủ dữ liệu ghi failed/partial, không mock/fallback.

Điều kiện hoàn thành:

- [x] URL canonical được đối chiếu bằng ASIN thực; đã mở một URL live và xác nhận title khớp. Kiểm tra thủ công toàn bộ mẫu vẫn thuộc audit giai đoạn 12–13.
- [x] Giá/rating/review chỉ lấy trong card nguồn; giá không đọc được giữ null. Snapshot scalar đầu tiên không bị ghép với metric của listing/request khác.

Live acceptance còn giới hạn: Search đang trả 503, Movers hub không có listing trong response hiện tại; không tuyên bố cả ba nguồn luôn hoạt động. Policy `live-only-v4` chặn cache cũ; chỉ nâng cấp Amazon và những phần output/validation liên quan, chưa làm Reddit/ranking/quality gate giai đoạn sau.

### Giai đoạn 5 — Sửa dữ liệu Reddit

- [x] Ưu tiên Reddit API chính thức khi có credential: app-only client_credentials, token RAM/expiry, tối đa một refresh 401.
- [x] Public JSON là adapter live khi chưa có credential/chọn tường minh, không mock và không tự downgrade từ lỗi OAuth.
- [x] Không chọn subreddit ngẫu nhiên; query order xác định, bỏ trùng input.
- [x] Truy vấn tất cả subreddit × seed đã cấu hình trong giới hạn; vượt ngân sách từ chối trước I/O, không âm thầm cắt query.
- [x] Một trang/query, giới hạn query/post/JSON; deduplicate post ID và giữ snapshot đầu tiên, không ghép metric từ response sau.
- [x] Lưu created_utc, score, comment count, permalink, title và selftext gốc; thiếu dữ kiện giữ unknown, không dựng lại số upvote thô từ score.
- [x] Body thiếu/rỗng không có summary giả. content_summary chỉ là trích đoạn, không phải suy luận cộng đồng.
- [x] Pain point chỉ nhận object trích dẫn ứng viên: ít nhất một ID Reddit có sẵn và quote nguyên văn trong mọi post đã dẫn. AI output thiếu/sai block bị từ chối; section Phân tích thay bằng dữ kiện và trích dẫn hợp lệ, kể cả niche không có Reddit, đến khi có validator toàn phần giai đoạn 8. Ý tưởng AI vẫn là suy luận, không phải market fact.
- [x] Lọc bài theo created_utc, cửa sổ rolling đã lưu trong query; mốc chốt là lúc bắt đầu collect. Loại ngày sai/tương lai/nội dung đã removed/deleted.
- [x] Nguồn bị chặn/hết quota/lỗi kết nối dừng request tiếp theo; failed nếu 0 post, partial nếu đã có post. Pipeline giữ dữ liệu nguồn khác; không proxy/bypass/mock.
- [x] Chặn redirect token/search, không log/lưu credential/token/body grant; không dùng auth .netrc/Session ngoài ý muốn; escape title/excerpt/quote ở Markdown/UI.

Điều kiện hoàn thành:

- [x] Contract/parser không tự tạo permalink, ID, thời điểm, số liệu hoặc nhận định pain point; test mới/bị ảnh hưởng đã pass.
- [ ] Xác minh permalink mở tới post thật ở môi trường chạy: chưa có post live do connection_error.
- [ ] Đối chiếu score/comment trực tiếp từ response live: chưa có JSON live, chưa có credential OAuth.

Phần code giai đoạn 5 đã triển khai, policy lên live-only-v5 để từ chối cache thiếu contract Reddit mới. Kiểm chứng mạng chỉ thử một subreddit/seed, 2 attempt lỗi; lưu diagnostics thật và không thay bằng fixture. Tài liệu cấu hình/giới hạn ở README. Chưa thực hiện quality gate đầy đủ, ranking, validator mọi claim AI, retention hoặc các giai đoạn 6 trở đi.

### Giai đoạn 6 — Validation và quality gate

- [x] Validate schema ngay sau collector; container/journal/query/record có giới hạn, reject metadata sai origin/thời gian/credential chưa che trước persistence.
- [x] Loại record không có URL nguồn, retrieved_at timezone-aware hoặc không liên kết request thành công cùng provider. Kiểm tra cả listing phụ và cache provenance.
- [x] Dedup bằng khóa chung: keyword.strip().casefold() + geo + timeframe; ASIN; post ID. Không fallback title; giữ scalar snapshot đầu tiên và listing evidence Amazon. ID evidence lặp là lỗi, không phải duplicate trung tính.
- [x] Không mutate/ép kiểu/boost/sort score gốc. Processor copy sâu, quality đối chiếu snapshot cả giá trị lẫn kiểu (False không bằng 0 trong contract) và gắn digest với dữ liệu đã đánh giá.
- [x] Tách raw_metric và derived_metric trong output; các alias phẳng còn lại để tương thích và không có công thức thứ hai. Chưa tạo commerce/community score vì ranking thuộc giai đoạn 7.
- [x] Data quality có candidate/valid/rejected/duplicate/retained, tỷ lệ hợp lệ, độ phủ nguồn cấu hình và lý do cụ thể. Mẫu rỗng/không biết để null, không có confidence số giả hoặc tự reweight.
- [x] Gate tối thiểu: hai keyword khác nhau có series ≥4 điểm hoàn tất cùng geo/timeframe, metric/label tính lại khớp và một evidence Amazon Search/ranking có danh mục cụ thể hoặc Reddit đã validation. Không dùng Suggest/score rời hoặc hub tổng để vượt gate.
- [x] Niche không đạt gate không gọi LLM, không tạo idea/khuyến nghị; chỉ xuất trong Dữ liệu chưa đủ. JSON/Markdown/UI nhận cùng assessment; state mâu thuẫn không mở khuyến nghị.
- [x] Giữ diagnostics ngay sau collection và bổ sung gate trước AI, vẫn còn khi bước phân tích lỗi. Escape lý do/niche/model/nguồn ngoài khi render; UI ưu tiên raw_metric null/zero đúng nghĩa.

Kiểm chứng: 128 test Python mới + 2 ca bị ảnh hưởng, 4 test UI mới pass. Audit offline snapshot live thật chấp nhận 22 record nhưng gate insufficient đúng vì chưa có supporting evidence cho niche; không tạo dữ liệu giả, không gọi lại mạng hay tuyên bố pipeline live đã đầy đủ. Xem README và reports/verification_phase06/. Không triển khai ranking/giai đoạn 7 hoặc validator ngữ nghĩa AI toàn phần/giai đoạn 8.

### Giai đoạn 7 — Thiết kế lại scoring và ranking

- [x] Một `RankingService` thuần, policy bất biến có version/hash và dependency injection; pipeline chỉ gọi một lần sau gate, lưu kết quả trước AI.
- [x] Tính riêng momentum, recent interest, commerce proxy Amazon, community proxy Reddit và competition proxy khi đủ mẫu. Raw measurements không bị sửa, input truy ngược evidence/request/time; không biến Search position/review lịch sử thành doanh số.
- [x] Công khai công thức median/normalize, trọng số cố định 30/20/20/20/10%, ngưỡng mẫu 2/2/3/3/5, reference constants, precision và giới hạn trong README/policy. Đây là heuristic có cấu hình, chưa phải phương pháp dự báo được hiệu chỉnh bằng kết quả bán hàng.
- [x] Không reweight khi thiếu nguồn/metric: null từng nhóm, observed contribution, total_score chỉ khi đủ năm nhóm, cận trên và component coverage riêng. Confidence là độ đầy đủ input × valid_ratio, không phải xác suất thành công; unknown denominator giữ null.
- [x] Không so trực tiếp recent interest giữa batch/request chuẩn hóa riêng. Không tương thích geo/timeframe/window thực tế thì không phân hạng; khác sort/time filter/cửa sổ Reddit thì không sử dụng community trong so sánh. Không tự fetch thêm hoặc chọn cohort thuận lợi để lấp thiếu.
- [x] Tie-break bằng metric thật theo thứ tự policy đã công bố; không theo config/collector/LLM. Metric bằng nhau đồng hạng 1,1,3; tên chỉ giữ thứ tự hiển thị ổn định.
- [x] Mỗi điểm có component score/contribution/formula/sample_size/candidate_count/context/evidence; lý do unranked và explanation so sánh có nêu khoảng bất định chồng lấp.
- [x] Markdown, JSON, UI và diagnostics cùng đọc `ranking_assessment` trong kết quả pipeline hiện có; `ranking` chỉ là alias tương thích, không tính lại. Có schema frozen cho ranking, chưa mở rộng schema typed toàn ResearchResult ở giai đoạn 9.
- [x] Analyzer không chấm hoặc sắp hạng; summary legacy chỉ render unavailable nếu không nhận canonical result. Không chọn Top 3 từ ý tưởng chưa qua validator giai đoạn 8.
- [x] Kiểm tra security/input: từ chối số không finite/bool/precision và policy sai, giới hạn niche/record, snapshot digest, không I/O/eval trong ranking, JSON độc lập, escape output/link và UI fail-closed khi rank mâu thuẫn gate. Policy lên `live-only-v7`, không nhận cache v6 như output đã có ranking mới.

Điều kiện hoàn thành:

- [x] Cùng một run chỉ có một ranking ở mọi output; test integration đối chiếu JSON/cache/Markdown/diagnostics, UI không sắp/tính lại.
- [x] Có thể giải thích vì sao niche A đứng trên niche B từ contribution/metric tie-break thật và kiểm tra được inputs; không khẳng định điểm heuristic là tiềm năng kinh doanh đã được chứng minh.

Kiểm chứng: 78 test Python mới và 6 test UI mới pass, không full suite hoặc lặp ca đã pass. Audit offline 22 record live cũ vẫn không đủ gate nên ranking unavailable, không tạo hạng/idea giả; chưa có acceptance live cho ranking đủ năm nhóm. Xem [công thức và giới hạn](README.md#ranking-có-breakdown--giai-đoạn-7) và [audit giai đoạn 7](reports/verification_phase07/README.md). Không triển khai giai đoạn 8–13 trong lần này.

### Giai đoạn 8 — Grounded AI analysis

- [x] Xóa parser Markdown tự do khỏi analyzer runtime; schema `grounded-analysis-v1` đóng dùng chung trong `format` và validator local, pin jsonschema 4.26.0. Không có legacy acceptance path.
- [x] Tạo catalog bất biến sau gate/digest, kiểm tra tên niche và kiểm tra lại snapshot trước/sau generation. Mỗi record giữ evidence ID/request ID/URL/time/cache flag; không gửi full series/cookie/token/HTTP body nguồn.
- [x] Facts chỉ được chọn metric whitelist/value thật ở đúng nguồn của mọi evidence dẫn. Text/đơn vị/scope/timestamp do server render, không nhận trường văn xuôi để đổi rating/review/Search position thành sales/rank/margin.
- [x] Quote Reddit phải nguyên văn trong đúng phần context đã gửi, không chỉ nằm trong body đầy đủ. Quote nguồn không được gắn nhãn là sự thật thị trường đã chứng minh.
- [x] Ideas có basis_fact_ids/basis_quote_ids tồn tại, evidence_ids đúng hợp basis, cần fact Trends + supporting Amazon/Reddit. Text chỉ là thiết kế/đối tượng giả định, có filter bảo thủ với số/currency/URL/claim kinh doanh/markup; why_now được dựng từ facts, không tự viết nguyên nhân hoặc số mới. Có thể abstain ideas=[]; không tạo idea thay thế cho đủ số lượng.
- [x] Context có cap theo nguồn, ID/count selected/available/omitted công khai và cờ body_truncated. Mặc định tối đa 5 keyword/6 ASIN/4 post, prefix 800 ký tự; dữ liệu gốc và ranking không bị lấy mẫu theo AI. Vượt count/byte budget còn lại thì context_rejected, không cắt ngầm hoặc gọi model với input thiếu không được ghi nhận.
- [x] Strict JSON trước schema: byte/depth/node/Unicode/finite-number budget, từ chối duplicate key, unknown field, ID lạ/trùng, source/value/basis sai. Không eval/remote schema/repair JSON bằng regex hoặc lấy evidence ngoài catalog để cứu output.
- [x] Tối đa hai generation/niche: một lần đầu + một repair cho output/schema/grounding sai, chỉ gửi code/path an toàn, không nhét raw output sai vào prompt. Lỗi HTTP/kết nối không tạo vòng retry hoặc chuyển provider/model khác.
- [x] Cả hai lượt không hợp lệ thì giữ EvidenceRenderer từ số đo thật, không có idea/quote AI. Persist audit outcome/attempt/error code/status cùng output đã kiểm tra; diagnostics quality/ranking có sẵn từ trước AI nếu phân tích hỏng.
- [x] Transport Ollama loopback-only, normalize localhost, không redirect, chặn endpoint/model URI hoặc tên cloud thông dụng, budget body/time/context/token, không ambient proxy/auth/.netrc/cookie, không log credential/body sai và đóng resource đúng ownership. Không tự sửa cấu hình daemon; muốn cam kết local-only phải tắt cloud ở daemon, không coi tên alias/loopback là bằng chứng inference offline.
- [x] Summary deterministic nhận dữ liệu/metrics + ranking đầy đủ + grounded facts/quotes/ideas, không gọi model thêm hoặc chấm điểm ý tưởng giả. Chọn tối đa ba slot theo canonical niche order, round-robin/content ID; không tuyên bố là ba sản phẩm hiệu quả nhất. Trả ít hơn nếu không đủ đề xuất, không tự tạo slot trống.
- [x] JSON/Markdown/UI đọc chung grounded result/analysis_summary; top_ideas là alias, slot không tự đánh số lại. UI chặn free-form/stale/thiếu citation hoặc sai digest/outcome và dựng link từ record gốc; không dùng URL/financials do model cung cấp. Policy lên live-only-v8, cache v7 không qua cửa sau.

Điều kiện hoàn thành:

- [x] Trong contract được chấp nhận, mọi fact định lượng phải có metric/value khớp evidence; không dùng regex số trong prose hoặc ID hợp lệ đơn thuần làm bằng chứng cho claim mới.
- [x] Dữ kiện đo được, nội dung nguồn chưa kiểm chứng và đề xuất thiết kế/đối tượng được tách kiểu/nhãn rõ ràng. Validator không chứng minh ngữ nghĩa đầy đủ, causality, market fit hoặc chân dung khách hàng; các phần đó giữ chưa xác minh.

Kiểm chứng: 210 Python mới + 9 ca bị ảnh hưởng, 6 UI mới + 1 ca bị ảnh hưởng pass; không full suite/kiểm tra lại nguồn đã pass. Audit thật chỉ xác minh nhánh insufficient không gọi AI, chưa có acceptance positive trên live run đủ dữ liệu. Công thức/contract/giới hạn: [README](README.md#grounded-ai-analysis--giai-đoạn-8); dữ liệu và nguồn gốc: [verification_phase08](reports/verification_phase08/README.md). Dừng ở giai đoạn 8; không triển khai schema typed toàn ResearchResult, tab/job UI hay concurrency của giai đoạn 9–11.

### Giai đoạn 9 — Đồng bộ Report, JSON và Web

Trạng thái: **Hoàn thành phạm vi giai đoạn 9**. Không mở rộng sang input/tab/jobs/concurrency giai đoạn 10–11.

1. [x] Canonical `ResearchResult` có version, sở hữu snapshot độc lập và bất biến đệ quy; `RunContext` và builder tách việc tập hợp kết quả khỏi orchestration/views.
2. [x] Pipeline tạo object này đúng một lần sau analysis; không thu thập/scoring/AI thêm khi publish.
3. [x] Markdown reporter render trực tiếp từ object, không tự tạo timestamp/mode/cost hoặc nhận payload kwargs riêng.
4. [x] JSON cache serialize cùng object. Alias chỉ ở serializer; atomic từng file, ghi latest sau Markdown; không đọc Markdown ngược để tạo JSON.
5. [x] Web/API hiển thị cùng publication, không tính lại score hoặc tự tạo metadata. HTTP JSON no-store; cache hiện tại được kiểm tra toàn envelope, policy v9 từ chối v8 trở xuống.
6. [x] Header ghi actual/requested mode, model thật dùng/đã thử, timestamp/run ID và loại live/offline. Digest/raw/derived/quality/source health/summary links không được lệch nhau.
7. [x] Bảng “Tình trạng nguồn dữ liệu” cùng nguồn canonical; phân biệt request trong snapshot lịch sử với request mới khi audit offline.
8. [x] Appendix evidence giữ URL, timestamp gốc, request/dependencies, cache flag và mọi liên kết niche/record/listing được xuất.
9. [x] Báo cáo partial/failed có cảnh báo nổi bật trong Markdown và Web; dữ liệu thiếu vẫn null/unknown, không tự tạo record/ý tưởng.

Kiểm chứng: **99 test Python mới + 11 ca cũ bị ảnh hưởng trực tiếp, 3 UI mới pass**; không full suite hoặc re-fetch provider. Các ca fail ban đầu được sửa và chỉ chạy lại đúng ca lỗi; có một lượt lọc `-k` vô tình khớp tên file nên chạy lại nhóm vừa pass (đã thông báo), sau đó chuyển sang node ID cụ thể. Một ca identity được chạy lại khi tách builder làm đổi seam thực thi. Bao phủ immutable ownership, cùng object/alias/header, state/quality/raw-digest/provenance/summary consistency, strict JSON/budgets/checksum/path, no-store API, atomic failure, UTF-8/LF byte consistency và escaping. Fixture/AI responses cách ly ở tests/tmp, không phải dữ liệu nghiên cứu.

Audit dùng snapshot thật đã validation của giai đoạn 6 và request gốc giai đoạn 3–5, không xác minh lại provider: 2 Trends + 20 ASIN Amazon hub tổng + 0 Reddit; 22 evidence, `partial / insufficient / deterministic`, 0 network/generation, không có idea/ranking giả. Xem [verification_phase09](reports/verification_phase09/README.md) và [contract/giới hạn](README.md#canonical-researchresult--giai-đoạn-9). Chưa có live run đủ nguồn để chứng nhận positive Ollama end-to-end; checksum không xác thực nguồn và atomic từng file không phải transaction nhiều file.

### Giai đoạn 10 — Nâng cấp Web UI và input

Trạng thái: **Hoàn thành phạm vi giai đoạn 10**. Không triển khai concurrency provider, distributed/durable queue hoặc public/multi-user deployment.

1. [x] Form nhập category, 3–5 niches, 1–8 seed/niche, geo/timeframe; thêm subreddit tùy chọn có giới hạn để niche mới không bị gán cộng đồng giả. Intent đóng băng, truyền xuống collector và lưu cùng metadata/Markdown có nhãn input, không phải evidence.
2. [x] Chọn `Ollama` hoặc `Deterministic without LLM`; actual mode vẫn do output phân tích quyết định. Model là cấu hình server, không nhận endpoint/model/credential/output override qua Web.
3. [x] Mặc định Ollama, không bật Fast Mode ngầm; API legacy fast_mode không được tự nâng/đoán. CLI hiện có giữ nguyên.
4. [x] Sinh tab/pane từ kết quả canonical, không còn ba tên niche hardcode; ID chỉ số an toàn, escaping/ARIA/keyboard và xóa pane cũ khi cache không hợp lệ.
5. [x] Badge nguồn Live/Partial/Failed và Cached/Not configured/Snapshot; không gọi cache/audit là live mới, không gán Live khi thiếu số record/request xác nhận.
6. [x] Giữ confidence/ranking breakdown/evidence từ server, ghi rõ confidence không phải xác suất kinh doanh; Web không tự tính score.
7. [x] POST tạo job 202, GET poll callback nguồn/bước thật và lấy publication riêng của đúng job. Single-flight/idempotency, chống click trùng, resume job khi mất kết nối/reload; không fake progress hoặc tự retry POST. Worker completed không ép research thành success.
8. [x] Lỗi an toàn rõ ràng trên UI; exception/chi tiết nằm trong log server có job ID. Chặn nguồn gốc khác, Host rebind, CSRF, framing/encoding mơ hồ; CSP/no inline handler, asset allowlist, bỏ font ngoài và no-store.
9. [x] `/api/latest` vẫn đọc cache thật qua contract v9; lỗi/legacy/no_report success=false, không tạo metadata hoặc dữ liệu từ Markdown. Cache canonical cũ không bị thêm intent giả.
10. [x] Validate trước worker: UTF-8 JSON 32 KiB, unknown/duplicate field/type/control/NaN/overflow, 3–5 niche, text 200, tối đa 8 seed và 4 subreddit/niche, geo/timeframe hợp lệ. Job tối đa 8, TTL 1 giờ (không xóa active), result 32 MiB/job và 64 MiB tổng payload RAM.

Kiểm chứng: **110 Python mới + 5 ca cũ bị đổi API contract, 25 UI mới + 2 ca bị ảnh hưởng pass**. Không full suite hoặc provider re-fetch. Chạy test mới/bị ảnh hưởng; lỗi fixture đóng store trước thử idempotency, ID tham số test quá dài và assertion duplicate Content-Type chưa nhận 415 được sửa theo ca. Có thêm một ca liền kề được chạy lại khi xử lý fixture ID quá dài, không lặp cả nhóm pass. Bao phủ input immutability/query mapping, real callback/single-flight/race/retention/atomic terminal state, CSRF/Host/Origin/framing/charset, async HTTP → pipeline → đúng canonical result/cache kể cả research failed, tab/editor/XSS/badges/keyboard và polling/reconnect không thu thập lại. Test records/responses chỉ ở tests/tmp, không đưa vào runtime hoặc audit.

[Audit thật giai đoạn 10](reports/verification_phase10/README.md) chỉ GET Web local trên publication thật đã lưu: 2 Trends + 20 ASIN hub tổng + 0 Reddit, vẫn insufficient/partial; 3 loopback HTTP request, 0 job/provider/generation, cache/timestamp gốc không đổi. Không chứng nhận browser visual QA hoặc positive live research/AI đủ nguồn. Xem [contract và giới hạn](README.md#web-input-và-jobs--giai-đoạn-10). Job in-memory, không sống qua restart/không multi-process/authenticated-public; giai đoạn 11 chưa làm.

### Giai đoạn 11 — Tối ưu hiệu năng

Chỉ thực hiện sau khi độ chính xác đạt yêu cầu:

1. [x] Chạy song song ba nguồn độc lập bằng thread pool 1–3 worker, mỗi nguồn tuần tự qua niche; kết quả/progress giữ contract.
2. [x] Lease process-wide theo provider và instance, cấu hình 1–4/provider (mặc định 1), bounded wait; cache-key single-flight, không chia sẻ session state giữa nguồn.
3. [x] Cache collection sau validation theo source + toàn query/geo/timeframe + provider/settings/policy/scope, TTL/LRU/byte budget; chỉ success sạch, không stale/error/partial fallback, giữ nguyên provenance và tuổi evidence.
4. [x] Snapshot theo `run_id`: **validated collector output trước processor**, không phải raw HTTP/HTML hoặc record bị reject; toàn series/listing/post/trace an toàn, checksum/size/identity, atomic từng file + manifest cuối. Collision/path escape/size/storage failure fail rõ trước AI/latest.
5. [x] Giữ atomic write `latest_data.json` đã triển khai giai đoạn 9 (không viết lại/test lại phần đã pass).
6. [x] Giữ Markdown full run ID giai đoạn 9; snapshot có thư mục run ID riêng và từ chối collision.
7. [x] `PerformanceSettings`/`TREND_PERF_*`, `HTTPPolicy`/`TREND_HTTP_*`; HTTP streaming byte cap, owned session tắt implicit credential/proxy, đóng tài nguyên đúng ownership.
8. [x] Loại requirements `httpx`, `praw` không dùng; giữ `pytrends`/`requests` và dependency thực dùng, không uninstall môi trường người dùng.

Giai đoạn 11 triển khai cơ chế, **không tuyên bố precondition live accuracy/positive end-to-end đã đạt**: quality gate/ranking/AI rules không hạ; dữ liệu thiếu vẫn partial/failed/insufficient. Giới hạn provider/cache là trong process, chưa distributed quota/queue/cancel/hard job deadline. Snapshot là tại biên collector đã validation, không wire replay; storage/retention/permission cần vận hành riêng. Chi tiết mặc định/ngân sách và giới hạn ở [README](README.md#hiệu-năng-và-snapshot--giai-đoạn-11).

Kiểm thử **79 Python mới + 6 ca cũ bị ảnh hưởng pass**, từng nhóm mới 60 + 16 + 2 + 1; không chạy lại ca đã pass/full suite/UI cũ/provider live, chưa công bố coverage hoặc speedup mạng. Ca pipeline cache-hit dùng fixture cách ly, không phải live acceptance. [Audit thật giai đoạn 11](reports/verification_phase11/README.md): collector snapshot roundtrip 2 Trends + 20 ASIN hub tổng + 0 Reddit từ archive thật, giữ ID/timestamp, không biến archive thành cache fresh; 0 network/AI, không thay latest nghiên cứu chính. Giai đoạn 12–13 chưa làm.

### Giai đoạn 12 — Kiểm thử và audit dữ liệu

1. [x] Kế thừa unit parser/trend/validation/dedup/ranking đã pass giai đoạn 3–9; không chạy lại. Bổ sung closed snapshot codec, audit tính lại metric/quality/ranking theo policy lưu và oracle khoảng giá Decimal/currency độc lập.
2. [x] Bổ sung đường đi failure → pipeline → snapshot → audit: 429, timeout, selector đổi, JSON thiếu field, Ollama offline; cache/file sai được audit fail-closed, không repair hoặc tạo dữ kiện/idea thay thế.
3. [x] Bộ live integration thật cho ba provider, mặc định skip; chọn riêng bằng `--live-provider`, probe budgets hữu hạn/no cache/model/mock, diagnostics an toàn theo run ID. Không refetch Trends/Amazon đã kiểm tra.
   - [ ] Acceptance live đầy đủ: Reddit được chọn lại một lượt vì trước đó fail; vẫn HTTP 403, 1 request/0 record public JSON, chưa có OAuth; không tuyên bố pass hoặc tìm cách bypass nguồn. Cần quyền truy cập/credential hợp lệ và positive live end-to-end, không tự mở rộng scope/đổi nguồn.
4. [x] Kiểm thử end-to-end fixture pipeline → JSON/Markdown file → snapshot audit, có ranked/cached/multi-niche/custom policy/AI thành công hoặc lỗi, không chỉ so hai view cùng sai. Chèn claim/sửa score rồi rehash vẫn bị phát hiện khi đối chiếu nguồn/tính lại. Đây không phải positive live market run.
5. [x] Audit chỉ đọc: strict publication và file Markdown thật, typed retained snapshots, record/trace/provenance, quality/health/currency/ranking/summary, facts/quotes/proposals và tái dựng section. Ledger Unicode numeric occurrences có line/column/reference, structured numeric fields có JSON Pointer; phân biệt metadata/ID/date/template/source text với market metric. Không dùng số xuất hiện chỗ khác làm bằng chứng, không semantic-certify mọi văn bản nguồn/warning, không xác thực provider hoặc raw rejected candidates.
6. [x] coverage.py 7.16.2/dev requirements/.coveragerc, JSON/JUnit/manifest hashes thật. Chỉ công bố coverage **7 ca mới cuối + retry đúng ca fail trên mã chốt**, source=src: line 65.66%, branch 43.80%, combined 60.30%; không full-suite/all-67 coverage, không gộp số đo từ phiên bản mã thay đổi hoặc chạy lại test pass để nâng tỷ lệ.
7. [x] Không opt-in thì skip; live source được chọn không mạng/bị chặn/zero record thì fail với diagnostics thật, không chuyển fixture/cache. Unit block HTTP giữ nguyên ngoài tests/live; không có secret/body trong lỗi client hoặc artifact.

Kết quả: **67 ca mới pass** (38 + 14 + 8 + 7), không test cũ/UI/full suite. Hai lỗi bọc CollectionError và một assertion path symlink được sửa; chỉ retry đúng ba node fail, không lặp nhóm pass. Ba live case ban đầu skip; chọn riêng Reddit sau đó fail HTTP 403, còn Trends/Amazon skip/không refetch. [Manifest/JUnit/coverage](reports/verification_phase12/README.md) giữ đầy đủ lịch sử thay vì xóa fail.

[Audit archive thật](reports/verification_phase12/diagnostics/5e6305a72429435f8b8e7086fe418d9d.json) đối chiếu publication giai đoạn 9 với snapshot giai đoạn 11: 2 Trends + 20 ASIN hub tổng + 0 Reddit; 1219 numeric occurrences/625 structured numeric fields, vẫn partial/insufficient/ranking/ideas rỗng, 0 network/AI và không ghi latest nghiên cứu mới. Đây không chứng nhận live accuracy, market fit hoặc positive Ollama đủ nguồn. Đã triển khai cơ chế giai đoạn 12, nhưng **acceptance live chưa hoàn tất**; không chuyển sang giai đoạn 13.

### Giai đoạn 13 — README, báo cáo mẫu và video demo

1. Sửa README để mô tả đúng nguồn thực tế.
2. Ghi rõ yêu cầu internet, Ollama và credential nếu cần.
3. Ghi giới hạn nguồn và hành vi khi báo cáo partial.
4. Ghi đúng chi phí API; không đồng nhất chi phí API bằng 0 với mọi chi phí vận hành.
5. Tạo lại 2–3 báo cáo hoàn toàn từ live runs.
6. Giữ raw snapshot và manifest/checksum cho từng báo cáo.
7. Kiểm tra thủ công ít nhất 5 keyword, 5 sản phẩm và 3 Reddit post.
8. Quay video bằng chế độ Ollama thật.
9. Trong video mở ít nhất hai URL để chứng minh dữ liệu.
10. Không dùng báo cáo legacy đang chứa fallback để nộp.

## 6. Thứ tự ưu tiên

### P0 — Bắt buộc trước demo

1. Xóa runtime mock/fallback.
2. Thêm source status và provenance.
3. Sửa Google Trends không tự gán rising.
4. Sửa Amazon không tự điền metric.
5. Sửa Reddit không tạo post giả.
6. Tắt Fast Mode ngầm trên Web.
7. Đồng bộ ranking Markdown và dashboard.
8. Hiển thị partial/failure minh bạch.

### P1 — Cần để báo cáo có giá trị

1. Ranking service có công thức rõ.
2. Grounded JSON output cho Ollama.
3. Dynamic input và niche tabs.
4. Integration test live.
5. Evidence appendix và quality gate.

### P2 — Hoàn thiện sản phẩm

1. Progress realtime.
2. Parallel collection có rate limiting.
3. Cache, snapshot và manifest.
4. Coverage report và dọn dependency.

## 7. File dự kiến thay đổi

```text
src/config.py
src/models/schemas.py
src/collectors/base.py
src/collectors/google_trends.py
src/collectors/amazon.py
src/collectors/reddit.py
src/processors/data_processor.py
src/processors/ranking.py               # mới
src/analyzers/llm_analyzer.py
src/analyzers/output_validator.py       # mới
src/reporters/report_generator.py
src/pipeline.py
src/web/server.py
src/web/index.html
src/web/static/js/api.js
src/web/static/js/app.js
src/web/static/js/ui.js
tests/test_collectors.py
tests/test_data_processor.py
tests/test_ranking.py                    # mới
tests/test_pipeline.py                   # mới
tests/test_live_sources.py               # mới
README.md
requirements.txt
```

## 8. Definition of Done

- [x] Runtime không còn mock/fallback market data.
- [x] Mọi record có nguồn, URL và thời điểm thu thập, liên kết được tới HTTP request thành công.
- [x] Source lỗi được ghi failed/partial, không thay bằng dữ liệu giả.
- [x] Không còn price/rating/review/upvote/trend score mặc định.
- [ ] Mọi claim định lượng có evidence hoặc công thức rõ ràng.
- [x] Google Suggest không bị gọi là Trends growth.
- [x] Amazon Search không bị gọi là Best Sellers/Movers.
- [x] Mode và model trong metadata phản ánh đúng thực tế.
- [ ] Markdown, JSON và Web dùng cùng ranking.
- [ ] Ranking có breakdown và confidence.
- [ ] Web hỗ trợ 3–5 niche động.
- [ ] Failure-path tests và integration live tests pass.
- [ ] 2–3 báo cáo nộp được tạo từ live data và kiểm tra link thủ công.
- [ ] README không còn tuyên bố chưa được chứng minh.
- [ ] Video demo chạy pipeline thật và mở link bằng chứng.

## 9. Kết quả mong đợi

Nếu các nguồn hoạt động, tool tạo báo cáo đầy đủ với ranking và product ideas có bằng chứng. Nếu một nguồn lỗi, tool tạo báo cáo partial và ghi rõ giới hạn. Nếu dữ liệu không đạt quality gate, tool phải trả kết quả “không đủ dữ liệu để khuyến nghị” thay vì tạo một báo cáo đẹp nhưng không đúng sự thật.
