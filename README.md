# AI Product Trend Research Tool

Danh mục: **Quà tặng theo mùa (Seasonal Gifts)**.

Các niche: **Christmas Gift Ideas**, **Gift for Him**, **Gift for Her**. Chọn nhóm này để nghiên cứu nhu cầu mua quà cuối năm và so sánh các đối tượng nhận quà. Mức tăng trưởng và khả năng sinh lời phải được chứng minh từ dữ liệu mỗi lần chạy; không được mặc định rằng mọi niche đều đang tăng.

## Trạng thái nâng cấp

Đã triển khai mã và công cụ giai đoạn 0–12 trong [plan.md](plan.md): dữ liệu thật/provenance, quality gate, ranking, grounded analysis, canonical output, Web jobs, collection/cache/snapshot và audit đối chiếu nguồn. **Acceptance live giai đoạn 12 chưa đạt**: Reddit public JSON trả HTTP 403 ở một request thật ngày 22/10/2026, chưa có OAuth và chưa xác minh một run Ollama đủ evidence end-to-end. Không dùng fixture/archive thay cho nguồn live hoặc hạ quality gate. Giai đoạn 13 chưa triển khai.

- Collector chỉ trả dữ liệu đã đọc từ nguồn thật. Nguồn lỗi hoặc không có record được ghi nhận rõ.
- Giá, rating, review, điểm tìm kiếm, score/comment Reddit bị thiếu được giữ là null.
- Không còn sản phẩm, bài Reddit, ý tưởng, phần trăm tăng trưởng hoặc bảng xếp hạng viết sẵn.
- Google Trends lỗi không được thay bằng điểm số từ Google Suggest.
- Amazon phân biệt **Search**, **Best Sellers**, **Movers & Shakers**; không suy ra bestseller rank từ vị trí tìm kiếm.
- Chế độ tổng hợp chỉ render quan sát và phép tính từ dữ liệu đã thu thập.
- Báo cáo, cache và UI hiển thị trạng thái nguồn và chế độ thực tế.
- Mỗi bản ghi có evidence ID, query, thời điểm và liên kết tới các HTTP request thành công đã tạo ra nó.
- HTTP dùng chung chính sách timeout/retry; từng lần thử được lưu và thông tin xác thực được che khỏi nhật ký.
- Google Trends lưu toàn bộ time series, metric có công thức, cache ngắn hạn và Google Suggest tách riêng.
- Reddit ưu tiên OAuth khi có credential, quét subreddit/seed theo thứ tự xác định trong ngân sách, khử trùng post ID và giữ selftext/created_utc/permalink gốc.

Ranking là heuristic ưu tiên nghiên cứu, chưa kiểm định bằng kết quả kinh doanh. AI chỉ chọn fact khớp metric nguồn, trích dẫn nguyên văn và đề xuất có basis/evidence hợp lệ; không chấp nhận Markdown phân tích tự do. Summary chọn tối đa ba đề xuất thử nghiệm từ niche có ranking, không tuyên bố đó là sản phẩm bán tốt nhất. Thiếu evidence thì giữ dữ liệu quan sát, không tạo idea thay thế. Citation hợp lệ không chứng minh market fit, nguyên nhân hay đối tượng khách hàng.

## Input và nguồn dữ liệu

Cấu hình trong src/config.py:

| Niche | Seed keywords |
|---|---|
| Christmas Gift Ideas | christmas gift ideas; christmas gift ideas 2026; best christmas gifts; unique christmas gifts; christmas gift for family |
| Gift for Him | gift for him; gift ideas for men; best gifts for boyfriend; gifts for husband; unique gifts for men 2026 |
| Gift for Her | gift for her; gift ideas for women; best gifts for girlfriend; gifts for wife; unique gifts for women 2026 |

Nguồn đang triển khai:

| Nguồn | Dữ liệu thực sự sử dụng | Khi không khả dụng |
|---|---|---|
| Google Trends qua provider pytrends | Time series có timestamp, cửa sổ so sánh, growth/slope/volatility; query liên quan và Google Suggest riêng biệt | Không tạo điểm/gợi ý thay thế; hết retry 429 thì failed nếu chưa có record, hoặc partial nếu batch trước có dữ liệu |
| Amazon HTML qua requests/BeautifulSoup | Search mặc định; Best Sellers/Movers khi cấu hình URL phù hợp. ASIN, URL, title, currency/giá, rating/review và vị trí/hạng nếu có trong card | Giữ phần hợp lệ; failed/partial có cảnh báo khi bị chặn, trang sai loại hoặc không có card |
| Reddit OAuth / public JSON | Tất cả subreddit × seed đã cấu hình trong giới hạn; post ID, title, selftext gốc, created_utc, permalink, score/comment thật | Không chuyển OAuth lỗi sang public JSON; dừng khi bị chặn/hết quota, giữ partial hoặc failed, không tạo bài thay thế |

Cần internet để thu thập. Ollama là thành phần local; điều đó không có nghĩa toàn bộ nghiên cứu chạy offline.

## Cài đặt và chạy

Python 3.10+:

    python -m venv .venv
    .venv\Scripts\python -m pip install -r requirements.txt

Chế độ AI cần Ollama đang hoạt động và một model đã cài trên máy. Model mặc định trong cấu hình là local-bench-qwen35-2b-q4km:latest; đây là tên local, không bảo đảm có sẵn trên máy khác. Dùng model của bạn qua tham số --model.

### Web

    .venv\Scripts\python app.py

Mở http://127.0.0.1:5000. Form lấy cấu hình truy vấn mặc định từ server, không phải dữ liệu nghiên cứu mẫu. Chỉnh danh mục, 3–5 niche, seed keywords, geo và timeframe. Mặc định yêu cầu **Ollama**; chọn **Deterministic without LLM** nếu chỉ muốn thu thập live và tổng hợp dữ kiện, không gọi model. Subreddit tùy chọn nhập bằng tên cộng đồng, không phải URL; bỏ trống sẽ ghi Reddit chưa được cấu hình.

Nguồn lỗi sẽ được hiển thị trong khung trạng thái. UI vẫn cho đọc/tải báo cáo chẩn đoán khi kết quả partial hoặc failed.

Nút chạy tạo một job, trả ngay job ID rồi theo dõi callback pipeline thật. Không dùng phần trăm/timer giả. Mất kết nối không đồng nghĩa job thất bại; nút **Theo dõi lại job** tiếp tục job cũ, không gửi lượt thu thập mới. Tải lại trang tiếp tục theo dõi job đang chạy nếu còn trong cùng tiến trình server. Chi tiết và giới hạn ở [Web input và jobs](#web-input-và-jobs--giai-đoạn-10).

### CLI

Thu thập live và tổng hợp số liệu, không gọi AI:

    .venv\Scripts\python src/main.py --fast

Thu thập live và yêu cầu AI phân tích:

    .venv\Scripts\python src/main.py --model TEN_MODEL_DA_CAI

Tùy chọn niche và thư mục xuất:

    .venv\Scripts\python src/main.py --fast --niches "Christmas Gift Ideas,Gift for Him,Gift for Her" --output reports

Tên trùng với cấu hình giữ bộ keyword/subreddit tương ứng. Tên mới chỉ có seed keyword bằng tên đó; cần bổ sung subreddit trong cấu hình để dùng Reddit.

CLI trả exit code 1 khi kết quả thiếu dữ liệu hoặc phân tích AI thất bại. Báo cáo chẩn đoán vẫn được lưu và đường dẫn được in ra.

## Output và ý nghĩa trạng thái

Mỗi lần chạy lưu:

- report_trend_RUN_ID.md: dữ liệu/quan sát, cảnh báo, bảng trạng thái nguồn, chế độ thực tế và phụ lục evidence.
- latest_data.json: cùng ResearchResult phục vụ UI, có data_policy = live-only-v9 và schema_version = research-result-v1.
- diagnostics/RUN_ID.json: nhật ký request và ánh xạ evidence → request; lưu ngay sau thu thập, trước xử lý/AI.
- snapshots/RUN_ID/manifest.json và INDEX_SOURCE.json: snapshot tại biên collector sau validation, trước xử lý/AI; giữ series/listings/post, metadata và thống kê validation. Không chứa HTTP/HTML nguyên xi, cookie, credential hoặc body OAuth.
- source_statuses theo từng niche và source_health toàn run; metric thiếu không được điền giá trị thay thế.

CollectionResult[T] chứa records, status, warnings có cấu trúc và request_metadata:

- success: có record hợp lệ, không còn cảnh báo thu thập; request đã hồi phục sau retry vẫn giữ lịch sử lỗi.
- partial: có record nhưng còn cảnh báo hoặc một phần thao tác thất bại.
- failed: không có record phù hợp hoặc request lỗi.
- not_configured: chưa cấu hình nguồn, không gửi request.

Mỗi HTTP attempt có request_id riêng; các lần retry/redirect cùng operation_id. Nhật ký lưu method, URL/query đã che token/credential, status code hoặc mã lỗi mạng, thời điểm, thời lượng và thời gian retry. Không lưu cookie, Authorization header hay response body. Record không liên kết được tới request 2xx hợp lệ sẽ bị loại. Đây là provenance, chưa phải raw snapshot hoặc cơ chế kiểm định claim AI.

### Google Trends: dữ liệu và công thức

`TrendsProvider` tách collector khỏi pytrends; mỗi batch tối đa 5 keyword, giữ thứ tự và ghi `comparison_keywords`, `geo`, `timeframe`. `KeywordSignal.time_series` giữ từng timestamp UTC, value và is_partial. Giá trị thiếu/ngoài 0–100 là null, không nội suy. Cờ isPartial bị lược bỏ được đọc là false theo decoder pytrends 4.9.2; null/sai kiểu được giữ unknown và loại khỏi phép tính. Điểm partial được giữ trong series nhưng không dùng tính metric.

- Cần ít nhất 4 điểm hợp lệ đã hoàn tất. Đặt `w = min(window_points, số điểm hợp lệ // 2)`, lấy 2w điểm gần nhất thành hai cửa sổ bằng nhau, không chồng lấn.
- previous_mean và recent_mean: trung bình từng cửa sổ. growth_percent = (recent_mean − previous_mean) / previous_mean × 100.
- Hai kỳ đều 0: growth 0, stable. Kỳ trước 0 và kỳ sau dương: growth null, unavailable, không tạo phần trăm vô hạn.
- rising nếu growth ≥ ngưỡng tăng; declining nếu growth ≤ ngưỡng giảm; còn lại stable. Mặc định +15%/−15%, không cộng điểm cho rising.
- slope: hồi quy tuyến tính trên 2w điểm theo số ngày thực đã trôi qua, đơn vị điểm interest/ngày. volatility: độ lệch chuẩn tổng thể của 2w giá trị, đơn vị điểm interest.
- metrics lưu phương pháp v1, ngưỡng, số điểm dùng/loại và khoảng thời gian hai cửa sổ. score giữ điểm interest cuối kỳ hoàn tất. JSON giữ series đầy đủ; prompt AI chỉ nhận metrics và số điểm để tránh phình context.

Đây là thay đổi của **chỉ số interest tương đối**, không phải tăng trưởng doanh số hay lượng tìm kiếm tuyệt đối. Các batch được chuẩn hóa độc lập, không so sánh trực tiếp score giữa batch. Xem [cách Google chuẩn hóa dữ liệu](https://support.google.com/trends/answer/4365533?hl=en).

Google Suggest lấy gợi ý Autocomplete thật qua endpoint cố định, lưu trong suggestions. Nó không thay thế time series và không tham gia tính growth/classification. related_queries vẫn là truy vấn liên quan từ Trends. UI/Markdown ghi rõ sự khác biệt và escape văn bản bên ngoài.

### Cấu hình và cache Google Trends

| Biến môi trường | Mặc định |
|---|---|
| TREND_GOOGLE_GEO | Rỗng = toàn cầu |
| TREND_GOOGLE_TIMEFRAME | today 3-m |
| TREND_GOOGLE_WINDOW_POINTS | 7 |
| TREND_GOOGLE_RISING_THRESHOLD_PERCENT | 15 |
| TREND_GOOGLE_DECLINING_THRESHOLD_PERCENT | -15 |
| TREND_GOOGLE_CACHE_TTL_SECONDS | 300; 0 để tắt, tối đa 3600 |
| TREND_GOOGLE_BATCH_DELAY_SECONDS | 2 |
| TREND_GOOGLE_SUGGESTIONS_ENABLED | true; chỉ nhận true/false |

Niche có thể ghi đè geo/timeframe. Input giới hạn 1–50 keyword, tối đa 200 ký tự/keyword, từ chối control character và geo/timeframe sai định dạng. Endpoint HTTPS cố định, không nhận URL từ input. Parser giới hạn 10.000 mốc/batch và 2 triệu ký tự JSON sau khi nhận response; không phải giới hạn tải mạng toàn HTTP client.

Khi dùng GoogleTrendsCollector trực tiếp, cache batch RAM có TTL/LRU, tối đa 64 entry/8 MiB JSON, có khóa và sao chép chống mutate chéo. Key gồm provider, batch đúng thứ tự và policy; chỉ lưu batch đầy đủ không cảnh báo, không fallback stale/failure/partial. Không lưu body, cookie hoặc token. Cache batch không phải distributed/single-flight. **Pipeline giai đoạn 11 tắt cache batch này** và dùng cache toàn CollectionResult sau validation, với TTL `TREND_PERF_GOOGLE_TRENDS_CACHE_TTL` bên dưới; không cộng dồn hai lớp TTL.

Bản ghi cache có provenance.from_cache=true, giữ evidence ID, retrieved_at và request ID gốc. Trace lịch sử có cache_reused=true; request_count/retry_count chỉ đếm request mới, cached_record_count đếm bản ghi dùng lại. Publication hiện dùng v9 như phần canonical output; không tự nâng cache lịch sử thiếu contract.

pytrends 4.9.2 là adapter ban đầu, không phải API Google chính thức. [Repository upstream đã archive](https://github.com/GeneralMills/pytrends); interface cho phép thay provider khi endpoint thay đổi. Việc nguồn chặn/giới hạn truy cập vẫn được báo rõ, không có cơ chế vượt captcha hoặc dữ liệu thay thế.

### Amazon: nguồn, định danh và bảo toàn dữ kiện

Mặc định dùng amazon_search_terms trong config (hoặc tên niche). Có thể thay bằng amazon_sources, mỗi phần tử là một trong các cấu hình sau:

```json
[
  {"type": "search", "query": "christmas gifts"},
  {"type": "best_sellers", "url": "https://www.amazon.com/gp/bestsellers/toys-and-games"},
  {"type": "movers_shakers", "url": "https://www.amazon.com/gp/movers-and-shakers/toys-and-games"}
]
```

Đây là ví dụ cấu hình truy vấn, không phải market data. URL ranking cần đúng danh mục người dùng muốn khảo sát, không có query/fragment/tracking suffix. Không tự chọn danh mục, không tự lấy dữ liệu Best Sellers tổng làm bằng chứng cho niche cụ thể. Collector chỉ truy cập các route Amazon.com HTTPS được phép; URL cuối cùng và tiêu đề trang ranking phải xác nhận đúng loại nguồn.

- [ASIN là định danh sản phẩm 10 ký tự của Amazon](https://sell.amazon.com/blog/what-is-an-asin). Collector lấy từ data-asin hoặc URL sản phẩm, từ chối định danh xung đột và tạo URL canonical /dp/ASIN; không follow link sản phẩm/tracking để scraping thêm.
- Deduplicate bằng ASIN, không bằng title. Các ASIN khác nhau dù cùng title vẫn được giữ. Giữ snapshot title/price/rating/review đầu tiên cùng provenance gốc; không ghép số liệu từ request sau vào snapshot đó.
- listings giữ từng lần xuất hiện: loại nguồn, URL trang, vị trí trong HTML, search_position hoặc listing_rank, is_sponsored và provenance riêng. Diagnostics liên kết được cả các listing phụ tới request gốc.
- Search position là thứ tự card trong response, không phải bestseller rank. rank chỉ có nếu badge hạng được đọc từ Best Sellers; Movers dùng listing_rank riêng. Nếu trang hub/card không công bố hạng thì null, không lấy thứ tự DOM thay thế.
- Nhận diện marker Sponsored trên cả ba loại nguồn; mặc định loại bỏ. Khi bật include_sponsored, giữ cờ và hiển thị rõ. Cờ false trên Search chỉ có nghĩa không thấy marker quảng cáo, không chứng nhận sản phẩm organic.
- Parse các trường độc lập: thiếu/không đọc được là null. Rating 0–5, review/ratings là số đếm không âm chính xác, không đổi 1.2K thành một số được đoán; số vượt precision integer của JSON/JavaScript bị để unknown.
- Giá chỉ được nhận nếu có currency/ký hiệu và số đọc được rõ ràng. price giữ display gốc; price_amount là chuỗi Decimal; price_currency giữ code/ký hiệu quan sát được. Không tự biến $ thành USD, không quy đổi VND/USD hoặc dùng tỷ giá cố định. Dấu phẩy thập phân chỉ hỗ trợ EUR/€; định dạng mơ hồ bị từ chối.
- Pipeline/report nhóm khoảng giá theo từng currency, không cộng/trung bình chéo currency. Hàm extract_price_range USD cũ chỉ còn cho tương thích; luồng runtime dùng extract_price_ranges/format_price_ranges.
- HTML sai content type/quá lớn, captcha, sai loại trang hoặc không có card đều có warning gắn request ID. Gặp captcha/403 hoặc hết retry 429 thì dừng các trang còn lại, không dùng proxy, vượt captcha hay lấy dữ liệu mẫu thay thế.

| Biến môi trường | Mặc định | Giới hạn |
|---|---|---|
| TREND_AMAZON_MAX_REQUESTS | 4 | 1–8, kiểm tra trước I/O |
| TREND_AMAZON_MAX_PRODUCTS | 20 | 1–100 ASIN duy nhất |
| TREND_AMAZON_MAX_CARDS_PER_PAGE | 100 | 1–200 card/trang |
| TREND_AMAZON_MAX_HTML_CHARS | 2000000 | Tối đa 5000000 ký tự sau khi tải, không phải trần dung lượng tải mạng |
| TREND_AMAZON_INCLUDE_SPONSORED | false | true/false |

Input từ chối URL ngoài Amazon.com, IP, userinfo, HTTP, port lạ, path traversal và control character. Parser không chạy JavaScript hay tải tài nguyên HTML. Nội dung title/nguồn được escape trong Markdown/UI. Đây là hardening phần Amazon, không phải tuyên bố đã security-audit toàn ứng dụng.

### Reddit: OAuth, giới hạn và evidence cộng đồng

`TREND_REDDIT_MODE=auto` (mặc định) chọn OAuth nếu có đủ `REDDIT_CLIENT_ID` và `REDDIT_CLIENT_SECRET`; không có cả hai thì dùng adapter public JSON live. Credential thiếu một phần/sai cấu hình làm riêng nguồn Reddit failed, không làm mất dữ liệu các nguồn khác. `oauth` bắt buộc credential; `public_json` là lựa chọn tường minh và không đọc credential; `disabled` không gửi request.

OAuth dùng [Application-only client_credentials của Reddit](https://github.com/reddit-archive/reddit/wiki/OAuth2#application-only-oauth): Basic Auth chỉ gửi tới endpoint access_token, Bearer chỉ tới oauth.reddit.com. Token chỉ ở RAM trong vòng đời collector, dùng lại đến gần expiry; HTTP 401 được gia hạn tối đa một lần. Token POST không tự retry. Không log/lưu client ID, secret, token, header xác thực hay body grant vào report/diagnostics. Redirect của token/search bị từ chối; không nạp xác thực .netrc hoặc Session.auth ngoài ý muốn. Không có password grant hoặc thao tác ghi lên Reddit.

Đặt credential và `REDDIT_USER_AGENT` trong môi trường backend, không đưa vào frontend/Git/log. User-Agent nên chứa định danh ứng dụng/phiên bản và liên hệ thật của người vận hành, không dùng tài khoản liên hệ giả. Có credential không tự chứng minh quyền khai thác dữ liệu: [Reddit yêu cầu phê duyệt truy cập và quyền dùng thương mại theo mục đích](https://support.reddithelp.com/hc/en-us/articles/14945211791892-Developer-Platform-Accessing-Reddit-Data). Public JSON không phải cách bỏ qua quyền truy cập, điều khoản hoặc rate limit.

- Giữ thứ tự subreddit rồi keyword, loại seed/subreddit trùng; không random. Vượt ngân sách bị từ chối trước I/O, không âm thầm cắt danh sách query. Mặc định 4 subreddit × 5 seed/niche là 20 query hợp lệ. Mỗi query lấy một trang, không crawl/paginate vô hạn; không tuyên bố đã lấy toàn bộ bài trong Reddit.
- Giữ tối đa max_posts post duy nhất, snapshot đầu tiên theo post ID; title giống nhau không bị gộp. Khi đạt trần vẫn xử lý các query đã cấu hình trong ngân sách, báo record_limit/partial nếu còn post bị bỏ. Thứ tự này không phải ranking hay chứng nhận đại diện thống kê; query journal giữ cả lượt tìm trùng, record dẫn tới snapshot gốc.
- Lọc lại created_utc ở backend, không chỉ tin tham số t của API. Cửa sổ đóng tại lúc bắt đầu collect: hour/day/week = 1 giờ/24 giờ/7 ngày; month = 30 ngày, year = 365 ngày cuốn chiếu, all không giới hạn quá khứ. Thiếu/sai ngày hoặc post sau mốc chốt bị loại; biên đầu/cuối được tính. Đây không phải tháng/năm lịch.
- ID, subreddit, permalink và t3 fullname (nếu có) phải khớp. Chỉ tạo link HTTPS www.reddit.com tới chính post đó; không follow URL trong selftext, không cho path traversal, query, fragment hoặc link tới comment giả làm post.
- score giữ nguyên số nguyên API trả (có thể âm; không phải tổng upvote thô), num_comments không âm. Thiếu/sai kiểu/ngoài precision JSON-safe để null, không ép chuỗi/số rút gọn. created_utc và selftext giữ nguyên; thiếu body là null, body rỗng là chuỗi rỗng, không tự tạo summary. content_summary chỉ là trích đoạn để hiển thị, không phải pain point AI.
- Không thu thập username/comment body/private message; bỏ nội dung đã marked deleted/removed khi fetch. Đây chưa phải dịch vụ đồng bộ xóa dữ liệu hoặc chính sách retention toàn hệ thống (các giai đoạn sau).
- Với AI, riêng pain point dùng JSON trích dẫn ứng viên `{quote, evidence_ids}`: 1–5 ID Reddit đã có, quote 8–500 ký tự phải xuất hiện nguyên văn trong mọi post dẫn. Không chấp nhận diễn giải tự do trong object này. Nếu không đủ bằng chứng trả danh sách rỗng; ID/quote sai hoặc thiếu block thì từ chối output AI và chỉ render dữ kiện. Section Phân tích chỉ render quan sát xác định và trích dẫn hợp lệ, không xuất phân tích cộng đồng tự do (kể cả khi Reddit không có dữ liệu). Ý tưởng AI vẫn là suy luận cần kiểm chứng; không coi đây là validator tất cả claim của giai đoạn 8.
- X-Ratelimit-Remaining/Reset được tôn trọng khi quota còn dưới một request; giữ cooldown trong provider và không ngủ vô hạn. Retry-After theo transport chung. Hết retry/lỗi kết nối, 401/403/429, 5xx cuối cùng, trang chặn hoặc redirect thì dừng query còn lại; không dùng proxy, captcha bypass, đổi host hay mock. Trước đó có post thì partial; không có thì failed. Nguồn khác vẫn tiếp tục.

| Biến môi trường | Mặc định | Giới hạn |
|---|---|---|
| TREND_REDDIT_MODE | auto | auto / oauth / public_json / disabled |
| REDDIT_CLIENT_ID / REDDIT_CLIENT_SECRET | Không có | Chỉ backend; cần đủ cặp cho OAuth |
| REDDIT_USER_AGENT | python:ai-tool-fashion:v1.0 (read-only community evidence) | ASCII in được, tối đa 256 ký tự; không CR/LF |
| TREND_REDDIT_TIME_FILTER | month | hour / day / week / month / year / all |
| TREND_REDDIT_SORT | top | top / new / relevance / comments |
| TREND_REDDIT_MAX_QUERIES | 32 | 1–64 query logic; retry/auth được ghi riêng, không giấu request |
| TREND_REDDIT_MAX_SUBREDDITS / MAX_KEYWORDS | 8 / 8 | Mỗi giá trị 1–16; tích query vẫn phải trong max_queries |
| TREND_REDDIT_MAX_POSTS | 15 | 1–100 post duy nhất/niche |
| TREND_REDDIT_PAGE_SIZE | 25 | 1–100 child/query, một trang |
| TREND_REDDIT_MAX_JSON_CHARS | 2000000 | 1–5000000 ký tự sau khi tải; không phải trần byte tải mạng |

Selftext tối đa 40000 ký tự, giữ nguyên trong dữ liệu gốc; context AI v8 mặc định chỉ gửi prefix 800 ký tự/post đã chọn, có cờ body_truncated. Quote phải xuất hiện trong đúng phần đã gửi, không chỉ tình cờ có trong body đầy đủ. Title, excerpt và quote được escape trong Markdown/UI. Contract v5 của collector vẫn giữ; output AI đã chuyển sang schema chung v8 ở phần dưới, không còn chấp nhận block Markdown Reddit như runtime trước đây. Đây không phải audit bảo mật toàn ứng dụng.

### Chính sách HTTP của collector

| Biến môi trường | Mặc định | Ý nghĩa |
|---|---|---|
| TREND_HTTP_CONNECT_TIMEOUT | 5 | Giây chờ kết nối |
| TREND_HTTP_READ_TIMEOUT | 20 | Giây chờ đọc |
| TREND_HTTP_MAX_ATTEMPTS | 3 | Tổng lần thử mỗi URL, bao gồm lần đầu; tối đa 10 |
| TREND_HTTP_BACKOFF_BASE | 0.75 | Giây backoff ban đầu |
| TREND_HTTP_BACKOFF_CAP | 8 | Trần backoff trước khi xét Retry-After |
| TREND_HTTP_RETRY_WAIT_BUDGET | 30 | Tổng giây chờ retry/cooldown mỗi thao tác |
| TREND_HTTP_MAX_REDIRECTS | 3 | Số redirect tối đa; chỉ cùng origin |
| TREND_HTTP_MAX_RESPONSE_BYTES | 4194304 | Giới hạn body streaming sau giải nén, 1024–16777216 byte; vượt giới hạn không parse/retry |

Retry cho 429/500/502/503/504 và lỗi kết nối/timeout tạm thời; không retry lỗi parse, SSL hoặc 4xx còn lại. Backoff tăng theo cấp số nhân, jitter trong nửa trên của khoảng backoff. GET/HEAD được retry; POST chỉ khi adapter xác nhận là thao tác đọc an toàn (Trends explore). Retry-After hỗ trợ số giây và HTTP-date; nếu vượt ngân sách thì dừng và giữ cooldown, không gọi lại sớm. Session do collector tạo được tái sử dụng và đóng cuối lượt chạy; không dùng chung giữa worker.

Connect/read timeout không phải giới hạn tổng thời gian toàn request; xem [Requests timeouts](https://requests.readthedocs.io/en/latest/user/advanced/#timeouts). Cách diễn giải Retry-After theo [RFC 9110](https://www.rfc-editor.org/rfc/rfc9110.html#section-10.2.3). pytrends được cố định ở 4.9.2 vì adapter thay các network hook nội bộ để không bỏ sót request.

### Validation và quality gate — giai đoạn 6

Validation chạy ngay sau mỗi collector, trước processor/AI/report. Không sửa record lỗi cho có vẻ hợp lệ: loại record, giữ warning/statistics và tiếp tục nguồn khác. Mỗi record phải đúng model, có URL canonical, retrieved_at có timezone và liên kết tới request 2xx thành công cùng nguồn. Timestamp request không được đảo thứ tự, thiếu timezone hoặc vượt đồng hồ validation quá 60 giây; thời gian cache vẫn giữ nguyên. Đây không phải cơ chế chứng thực mật mã hoặc xác nhận nội dung nguồn là đúng.

- Journal chỉ chấp nhận HTTPS origin của provider, không userinfo, fragment, control character hoặc credential chưa che trong URL/query. JSON metadata giới hạn depth 8, 2048 node và 100000 ký tự chuỗi cộng dồn; URL/chuỗi metadata tối đa 32768 ký tự. Contract quá lớn/sai bị từ chối trước persistence; không ghi raw body vào lỗi validation.
- Giới hạn biên: 1000 candidate/source, 5000 request trace, 10000 warning, 200 dependency/provenance và 200 listing/ASIN; time series tối đa 10000 điểm/keyword. Cấu hình collector thực tế có trần thấp hơn. Đây là giới hạn xử lý sau collector, không phải trần byte tải mạng hay quota nhà cung cấp.
- Trends: bắt buộc tối thiểu 4 điểm hoàn tất để tính hai cửa sổ, timestamp có timezone tăng chặt/không trùng/không sau request; value null hoặc 0–100, partial là bool/null. Giữ điểm unknown/partial nhưng không nội suy hoặc lấy làm score cuối. Metric và nhãn được tính lại theo method/window/threshold đã khai báo rồi đối chiếu; signal_summary không rỗng phải khớp formatter từ metric, không nhận claim tự do thay số đo. Related queries/Suggest không được nhận chỉ từ trace interest: cần dependency riêng đúng keyword.
- ASIN/post ID phải hợp lệ theo contract nguồn; mọi listing Amazon cũng có provenance. Rating, review, rank/position và score/comment không nhận bool, số không hữu hạn hoặc số đếm vượt precision JSON-safe. Không nạp record cũ thiếu schema theo đường legacy.
- Dedup dùng một module identity chung: keyword.strip().casefold() + geo + timeframe; ASIN; post ID. Giữ snapshot đầu tiên, không chọn score cao nhất và không ghép giá/rating từ request sau. Amazon giữ thêm listing/evidence khi ASIN lặp. Evidence ID bị dùng lại là lỗi provenance, không phải duplicate trung tính.
- Processor giữ nguyên giá trị/kiểu số đo và thứ tự nguồn, không boost/sort score; copy sâu để không chia sẻ list/query với collector. Không fallback theo title khi thiếu ASIN/post ID. Helper nhận dictionary cũ không tự đánh dấu dữ liệu đó đã được validation.
- JSON mỗi record có raw_metric (số đo nguồn) và derived_metric (phép tính có method/threshold). Với keyword, raw_metric.score là điểm gốc; derived_metric chứa TrendMetrics. time_series đầy đủ vẫn ở trường riêng. Product/Reddit chưa có điểm suy diễn nên derived_metric rỗng. Các trường phẳng score/metrics/price… được giữ để tương thích và có cùng giá trị, không phải phép tính khác. UI ưu tiên raw_metric kể cả null/0, không lấy alias cũ thay giá trị thiếu.

Một niche chỉ qua gate khi đồng thời:

1. Có ít nhất hai keyword khác nhau đã validation với series/metric hợp lệ trong cùng geo/timeframe. Hai bản ghi của cùng keyword ở hai geo không được tính thành hai keyword.
2. Có ít nhất một evidence Amazon Search/ranking có danh mục cụ thể hoặc post Reddit đã validation. Hub Best Sellers/Movers tổng chỉ là quan sát chung, không đủ evidence bổ sung cho niche. Danh mục/query tường minh không tự chứng minh liên quan ngữ nghĩa; vẫn cần người nghiên cứu đối chiếu.
3. Snapshot sau processor khớp kết quả validation và mọi record đã qua kiểm tra URL/timestamp/provenance. Thiếu context/assessment không mở gate; client flag không thay thế validation. Digest gắn assessment với snapshot, phát hiện dữ liệu bị thay đổi sau đánh giá; không phải chữ ký chống giả mạo nguồn.

QualityAssessment được dùng chung ở metadata, từng niche, diagnostics, Markdown và UI. Quy tắc minh bạch, không có confidence/ranking score giả hoặc tự reweight:

| Trường | Định nghĩa |
|---|---|
| candidate_count | Số record collector trả tới biên validation; không phải toàn bộ record trên website hoặc card đã bị parser loại trước đó |
| valid_count / rejected_count | Candidate hợp lệ / bị loại; tổng bằng candidate_count |
| duplicate_count / retained_count | Candidate hợp lệ bị gộp / snapshot giữ lại; tổng bằng valid_count |
| valid_ratio | valid_count / candidate_count, tính trên candidate đã biết; mẫu rỗng hoặc thiếu thống kê nguồn trả null, không mặc định 100% |
| source_coverage | Số nguồn có evidence hợp lệ / số nguồn được cấu hình; nguồn failed vẫn trong mẫu số, not_configured được loại; mẫu số 0 trả null |
| insufficient | Chưa qua gate: không gọi LLM, không tạo idea và chỉ xuất dưới mục Dữ liệu chưa đủ |
| partial | Qua gate nhưng có nguồn chưa hoàn tất, record bị loại, thống kê chưa đầy đủ hoặc điểm Trends bị unknown |
| sufficient | Qua gate, mọi nguồn cấu hình hoàn tất và candidate hợp lệ; không phải chứng nhận cơ hội kinh doanh hay mọi ý tưởng AI đúng |

Duplicate hợp lệ không làm giảm valid_ratio; không tăng số keyword/source để vượt gate. Lưu diagnostics hai bước nguyên tử: ngay sau collection, rồi thêm quyết định gate trước AI. Nếu bước phân tích hỏng, journal và gate đã tính vẫn còn. Cache trước v6 bị từ chối thay vì coi score/URL cũ là đã qua gate mới.

success toàn run chỉ đúng khi mọi niche sufficient, mọi nguồn được cấu hình hoàn thành và chế độ phân tích được yêu cầu hoàn thành. Nguồn optional not_configured không giả làm failed/success có dữ liệu. Trường này không chứng nhận market fit, ranking đủ năm nhóm hoặc việc đã đáp ứng toàn bộ đề bài. ranking_status và top_ideas_status riêng phản ánh các điều kiện tương ứng; AI có thể trả JSON hợp lệ nhưng không đề xuất sản phẩm.

## Ranking có breakdown — giai đoạn 7

`RankingService` là nơi duy nhất tính và sắp hạng. Không gọi HTTP/LLM; chỉ nhận `NicheData` đã qua gate và khớp digest. Policy bất biến, có method `fixed_weight_observed_evidence_v1` và `policy_id` từ SHA-256 của toàn bộ cấu hình. Các ngưỡng và trọng số dưới đây là tham số heuristic được công khai, không phải số liệu thị trường hoặc hệ số đã học từ doanh số.

### Công thức và mẫu số

Mỗi component có thang 0–100; median được dùng để hạn chế ảnh hưởng outlier, không giả định mẫu đại diện. `p`, `r` là previous_mean/recent_mean đã tính từ series hoàn tất. `R=100`, `E=100` là hằng tham chiếu mặc định có thể cấu hình, không phải số review/comment quan sát được.

| Component | Trọng số | Score từ số đo thật | Mẫu tối thiểu mặc định |
|---|---|---|---|
| momentum | 30% | median(100 × r / (p+r)); p+r=0 loại khỏi mẫu tính | 2 keyword có mẫu số dương |
| recent_interest | 20% | median(r); chỉ dùng chung một request/thang chuẩn hóa | 2 keyword |
| commerce | 20% | median(20 × rating × reviews_count / (reviews_count+R)) | 3 ASIN có cả rating và review count |
| community | 20% | median(100 × min(log1p(max(score,0)+comments)/log1p(E),1)) | 3 post có cả score và comment count |
| competition | 10% | 100 × R / (median(reviews_count)+R); cao hơn nghĩa là rào cản review trong mẫu thấp hơn | 5 ASIN organic Search có review count |

Giới hạn và ý nghĩa:

- Momentum tăng từ baseline 0 dùng tỷ số đối xứng hữu hạn, không tạo growth_percent giả: growth_percent gốc vẫn null. Cả hai kỳ bằng 0 thì momentum unavailable, còn recent_interest bằng 0 vẫn là số đo quan sát được.
- Các keyword trong một niche và các niche tham gia so sánh phải cùng geo, timeframe, cửa sổ thời gian thực tế và method/window_points. Nhiều context không tương thích thì không chọn một context thuận lợi để xếp hạng.
- Interest 0–100 không phải search volume tuyệt đối. Website Trends chuẩn hóa lại mỗi request; chỉ coi cùng primary request ID và comparison_keywords là cùng thang đo. Nhiều request/batch, kể cả query giống nhau, làm recent_interest unavailable cho toàn bộ nhóm niche đủ gate trong run; giữ mean gốc trong inputs, không scale lại và không thu thập thêm để tự lấp chỗ thiếu. Momentum từ tỷ số trong từng series vẫn có thể dùng khi các cửa sổ phù hợp. Xem [Google về chuẩn hóa Trends](https://support.google.com/trends/answer/4365533?hl=en) và [phạm vi scale từng request của website](https://developers.google.com/search/blog/2025/07/trends-api).
- Commerce chỉ là proxy rating có hỗ trợ lịch sử review, không phải sales/current demand. Chỉ dùng scalar của snapshot chính có scope Search hoặc danh mục ranking cụ thể; Sponsored và hub tổng bị loại. Không lấy rating từ hub rồi gắn sang Search listing xuất hiện sau. Không dùng giá, title, search position hay Suggest để boost score.
- Competition chỉ là rào cản review của mẫu organic Search, không phải tổng đối thủ hoặc cạnh tranh toàn thị trường. ASIN ranking danh mục không biến thành Search; không suy số lượng cạnh tranh từ giới hạn 20 sản phẩm. Commerce/competition cùng sử dụng review count, có tương quan; không coi là hai kiểm chứng độc lập về sức mua.
- Community là tương tác tích lũy trên post trong mẫu, không phải tốc độ tăng thảo luận hoặc số upvote thô. Điểm Reddit âm giữ nguyên trong inputs, chỉ phần transform clip về 0. Post thiếu score/comment không được bù 0. Khác sort/time_filter/độ dài cửa sổ giữa các niche thì component community unavailable, kể cả cửa sổ all có start=null. Nguồn/subreddit, query, độ tuổi bài và giới hạn mẫu vẫn cần người nghiên cứu đối chiếu.
- Ngưỡng thiếu mẫu để score/contribution null, không bổ sung giá trị giả. Component có đủ ngưỡng nhưng còn thiếu input được gắn partial, lưu sample_size/candidate_count. Trạng thái nguồn/độ liên quan ngữ nghĩa/mức đại diện mẫu không được chứng nhận chỉ bằng score.

### Thiếu dữ liệu và phân hạng

- `contribution_i = weight_i × score_i`, làm tròn 6 chữ số thập phân. `observed_score` là tổng contribution **đã có** trên thang cố định 100, không chia lại cho tổng trọng số còn lại. `total_score` chỉ có khi cả năm component có score; không lấy observed_score làm tổng đầy đủ.
- `component_coverage = Σ weight_i` của các nhóm có score. Khoảng bất định theo quy ước score 0–100: `[observed_score, observed_score + 100 × (1-coverage)]`, tối đa 100; không phải confidence interval thống kê. Unknown vẫn null, không phải quan sát 0. Ranking ưu tiên cận đóng góp quan sát; khi khoảng chồng lấp, explanation nêu rõ chưa thể kết luận niche trước có tiềm năng kinh doanh cao hơn.
- `confidence = 100 × valid_ratio × Σ(weight_i × sample_size_i/candidate_count_i)` trên các nhóm có score. Trường này chỉ là độ đầy đủ input/validation, **không** phải xác suất thành công, độ chính xác của mô hình, mức đại diện hoặc tỷ lệ request hoàn thành. Thiếu valid_ratio thì confidence null; candidate của component rỗng không chia 0. Duplicate hợp lệ không làm giảm valid_ratio; record bị loại có ảnh hưởng qua mẫu số candidate. Nguồn optional chưa cấu hình vẫn không được phân bổ trọng số của nó cho nguồn khác.
- Muốn xếp hạng cần gate còn hợp lệ, context Trends phù hợp, ít nhất một component Trends và một component Amazon/Reddit có số đo đủ mẫu. Không đủ thì nằm trong unranked, không gắn hạng giả. Niche không qua gate không ảnh hưởng thang so sánh của các niche đủ điều kiện.
- Sắp theo observed_score giảm dần, sau đó metric thật: symmetric momentum, recent_mean khi so sánh được, median rating Amazon, median comments Reddit, median review Search thấp hơn. Metric thiếu được gắn cờ thiếu, không giả thành 0. Các khóa số đo bằng nhau dùng đồng hạng 1,1,3; tên chỉ ổn định hiển thị, không chọn người thắng. Không dùng vị trí config, thứ tự collector hoặc nội dung LLM làm tie-break.

### Một kết quả cho mọi output

Pipeline gọi service đúng một lần sau gate, lưu `ranking_assessment` vào diagnostics **trước AI**. Kết quả JSON run hiện tại chứa:

- `ranking_assessment`: method/policy/status, danh sách ranking và unranked, warnings, component/inputs/formula/contribution/trace cho mọi niche.
- `ranking`: alias tương thích của đúng danh sách `ranking_assessment.ranking`, không phải bảng tính riêng.
- `metadata.ranking_status`: available nếu mọi niche xếp được và đủ năm nhóm; partial nếu đã xếp được nhưng thiếu nhóm hoặc có niche unranked; unavailable nếu chưa xếp được niche nào.

Markdown và UI đọc `ranking_assessment`, không parse summary AI hoặc tự tính lại/sắp lại. UI giữ nguyên số 0/null và chặn rank mâu thuẫn quality gate; escape text/link, giới hạn hiển thị evidence và chỉ tới JSON đầy đủ khi còn mẫu. Tổng `ResearchResult` vẫn là dict; schema typed toàn run thuộc giai đoạn 9, chưa triển khai. Từ v8, Top 3 do summary riêng chọn từ đề xuất đã kiểm tra evidence, không tự chứng nhận ý tưởng chỉ từ niche rank.

### Cấu hình, giới hạn và kiểm chứng

Policy nằm trong `src/ranking/policy.py`, có thể truyền `RankingService(RankingPolicy(...))` qua `execute_pipeline(..., ranking_service=...)`. Trọng số dương, tối đa 6 chữ số thập phân, tổng đúng 1; cấu hình sai bị từ chối, không tự normalize. Reference constants 1–1.000.000; threshold có giới hạn; tối đa 100 niche và 1.000 record/nguồn/niche tại service. Không dùng eval, không tải URL của record, không giữ state giữa run. Schema frozen và JSON view độc lập; serialization không copy lặp toàn bộ cây component. Cache lên live-only-v7, không nhận v6 như kết quả đã có scoring mới.

Audit chỉ ranking trên snapshot thật đã qua validation, không fetch lại nguồn đã kiểm tra:

    .venv\Scripts\python -B -m scripts.audit_ranking_phase07

Kết quả lưu tại [verification_phase07](reports/verification_phase07/README.md): 2 Trends, 20 ASIN, Reddit 0; gate insufficient do hub tổng/thiếu supporting evidence, ranking unavailable, không có khuyến nghị/idea. Đây không phải cache market run mới hay xác minh live cả ranking; timestamp/request ID gốc được giữ nguyên, không thay bằng fixture.

## Grounded AI analysis — giai đoạn 8

Runtime mới dùng schema `grounded-analysis-v1`; đã xóa parser ba phần Markdown và đường chấp nhận ý tưởng tự do. Cài lại requirements khi nâng cấp: bổ sung `jsonschema==4.26.0` (Python 3.10+). Schema đóng được biên dịch một lần, cùng một định nghĩa dùng cho kiểm tra local và trường `format` của Ollama; không tải JSON Schema từ URL của model. Tham khảo [structured outputs](https://docs.ollama.com/capabilities/structured-outputs), [Generate API](https://docs.ollama.com/api/generate) và [jsonschema validator](https://python-jsonschema.readthedocs.io/en/stable/validate/).

### Contract đầu ra và điều kiện kiểm tra

| Nhóm | Trường model được trả | Điều kiện chấp nhận |
|---|---|---|
| facts | fact_id, kind=fact, metric, value, evidence_ids | Metric trong whitelist; đúng nguồn; value bằng số đo/chuỗi gốc ở **mọi** evidence dẫn |
| quotes | quote_id, quote, evidence_ids | Chỉ Reddit; 8–500 ký tự nguyên văn trong quote_context đã gửi của mọi post dẫn |
| ideas | kind=proposal, name, what_to_sell, target_audience, basis_fact_ids, basis_quote_ids, evidence_ids | Basis tồn tại, evidence đúng hợp các basis; có fact Trends và nguồn bổ sung Amazon/Reddit |
| limitations | Danh sách mã giới hạn đã định nghĩa | Không có diễn giải factual mới, URL hay trường tùy ý |

Các trường khác bị từ chối, kể cả `analysis_text`, `why_now`, `profit_margin`, `sales`, `rank`, URL hay schema từ model. facts không có trường văn xuôi để model đổi ý nghĩa một con số có thật thành claim khác. Nội dung fact, đơn vị, nhãn và scope được chương trình dựng từ metric whitelist: index/growth/slope/volatility/nhãn Trends; title/giá/rating/review/Best Sellers rank thật/Search position phân biệt; title/score/comment Reddit. Source title hoặc trích dẫn chỉ chứng minh nguồn ghi như vậy, không chứng minh phát biểu bên trong là đúng ngoài đời.

- Fact phải dẫn đúng catalog của niche đang xử lý; metric thiếu/unknown không được nhận như 0. Không fuzzy-match, không parse lại số trong prose, không đổi currency hoặc suy margin/sales từ giá/review. Source numeric type/value được giữ, không lấy value của model thay nguồn sau đối chiếu.
- Text của ý tưởng chỉ mô tả thiết kế và đối tượng **giả định**. Kiểm tra bảo thủ với số Unicode/số viết bằng chữ thường gặp, currency, URL, markup, ký tự ẩn và từ vựng claim kinh doanh; chỉ cho chữ Latin (tiếng Việt/Anh) trong các trường tự do. Có thể từ chối nhầm tên/thiết kế hợp lệ; không coi filter này là bộ chứng minh ngữ nghĩa đa ngôn ngữ.
- `why_now` do server dựng từ fact được dẫn, ghi rõ không chứng minh nên bán ngay. Model không được chèn nguyên nhân mùa vụ, dự báo doanh số hoặc tỷ lệ tăng mới vào trường này. Customer profile/market fit vẫn chưa xác minh; trích quote không được nâng thành nhu cầu toàn thị trường.
- Có thể trả `ideas=[]` khi không đủ cơ sở; nếu đề xuất thì 2–3 ý tưởng khác nhau. Không chèn ý tưởng mặc định cho đủ quota. ID ý tưởng do server tạo từ nội dung/basis, không phải điểm hay thứ hạng chất lượng.
- `GroundedAnalysis`, fact/quote/idea là dataclass frozen. `NicheReportSection` còn giữ cấu trúc tương thích; kiểu `ProductIdea` cũ không còn đường acceptance trong analyzer runtime. Validator kiểm tra snapshot digest trước context, trước từng lượt gọi và sau generation; dữ liệu đổi giữa chừng thì hủy output.

### Context hữu hạn, không làm mất dữ liệu gốc

Chỉ tạo catalog sau gate series/provenance. Product từ hub tổng, Sponsored hoặc scalar snapshot chính không có scope phù hợp bị loại; Search xuất hiện sau không hợp thức hóa scalar từ hub. Catalog bất biến lưu primary evidence ID/URL/request ID/retrieved_at/cache flag, metric đo được và phần text có giới hạn. Không gửi cookie, token, HTTP body nguồn hay full time series vào AI; toàn bộ dữ liệu đã thu thập vẫn giữ trong output gốc.

`AnalysisPolicy` trong `src/analyzers/analysis_policy.py` điều khiển:

| Ngân sách mặc định | Giá trị |
|---|---|
| Tổng system + prompt UTF-8 | 24.000 byte |
| Output JSON model | 65.536 byte |
| Tổng số evidence được chọn tối đa | 100 |
| Cap context theo nguồn | 5 keyword, 6 ASIN, 4 post |
| Prefix selftext/post | 800 ký tự |
| Context/generation | num_ctx=32768, num_predict=4096, temperature=0 |
| JSON trước schema | depth ≤12, node ≤1500, số finite trong miền JSON-safe |
| Số lượng trong schema | ≤16 fact, ≤5 quote, ≤3 idea |

Context chọn theo identity keyword/ASIN và created_utc gần đây/post ID, không chọn bằng lời hứa hiệu quả kinh doanh. `ai_validation.context`/prompt ghi selected_evidence_ids, selected/available scoped counts, omitted_for_context và số hub/ad bị loại. Không coi phần không gửi là đã được AI phân tích; không nhận citation tới record không nằm trong catalog đã gửi, dù record tồn tại trong báo cáo. Ranking vẫn dùng toàn bộ evidence đủ điều kiện, không lấy mẫu context AI để đổi score/trọng số.

Quá global count/byte budget còn lại thì `context_rejected`, không gọi model và không tự tiếp tục cắt ngầm cho vừa. Khi cần tăng context hoặc đổi cap, truyền `AnalysisPolicy` vào analyzer và cấu hình `context_tokens` tương ứng. Byte budget là giới hạn bảo thủ, không phải phép đo token chính xác; bộ nhớ/tốc độ còn phụ thuộc model và máy, chưa benchmark.

### Retry, transport và bảo mật

Mỗi niche gọi tối đa hai lượt generation: lần đầu và **một** lượt sửa khi output/schema/grounding không hợp lệ, gồm JSON rỗng hoặc output bị cắt. Lượt sửa có error code/path an toàn, cùng evidence/schema; không đưa raw output sai vào prompt mới. Tiếp tục sai thì `invalid_output`, chỉ `EvidenceRenderer` với dữ kiện thật, không có idea/quote AI được chấp nhận. Lỗi kết nối/HTTP không retry vô hạn hay chuyển sang model/nhà cung cấp khác; trả data-only với `failed`.

- Client chỉ POST đến `/api/generate` trên literal loopback; localhost được đổi thành 127.0.0.1 để không dựa vào DNS. Từ chối host ngoài, 0.0.0.0, credential/path/query/fragment/URL mơ hồ; không follow redirect.
- Session riêng tắt ambient environment; kể cả session được inject vẫn vô hiệu hóa proxy/auth/.netrc/cookie cho request này. Session sở hữu được đóng bằng context manager, dependency mượn không bị đóng.
- Response được đọc theo chunk với giới hạn byte/elapsed time và đóng cả khi lỗi; không tải body vô hạn rồi mới kiểm tra. API yêu cầu JSON hoàn tất, không dùng thinking/free Markdown, không tự bóc code fence hay “sửa” JSON trước validation. Duplicate key, NaN/Infinity, unsafe number/Unicode và trường ngoài schema đều bị từ chối.
- Không log/persist prompt, output sai, header, credential hoặc body lỗi. Diagnostics chỉ ghi attempt/status/error code/path/HTTP status an toàn và output đã được kiểm tra. Chưa gọi model do preflight/gate/context sai thì không ghi model_attempted như đã có request.
- Tên model chỉ chấp nhận dạng local name hoặc namespace/name:tag và chặn `:cloud`/`-cloud`; không tự tải model, cài model hoặc gọi API cloud. **Endpoint loopback không chứng minh daemon/model alias không forward ra ngoài**: khi cần local-only, quản trị viên phải tắt cloud trong daemon (ví dụ `OLLAMA_NO_CLOUD=1`, khởi động lại Ollama theo [FAQ chính thức](https://docs.ollama.com/faq#how-do-i-disable-ollamas-cloud-features)). Tool không tự thay cấu hình Ollama của người dùng.

### Summary và output dùng chung

`GroundedSummaryService` nhận dữ liệu/metrics, canonical ranking breakdown và các idea đầy đủ đã qua validator. Không gọi thêm LLM, không đổi ranking và không dựng idea score. Chỉ xét section thành công có digest/mode/outcome phù hợp và niche có rank còn khớp snapshot.

Chính sách selection `grounded_research_slots_round_robin_v1`: đi theo thứ tự niche từ ranking và phân bổ theo vòng, mỗi vòng lấy một đề xuất/niche; trong niche dùng content ID để ổn định thứ tự, không gọi đó là ưu thế chất lượng. Chọn tối đa ba slot; chỉ có hai thì trả hai, không tự tạo slot còn thiếu. Nhãn là đề xuất thử nghiệm chưa kiểm chứng, không phải “ba sản phẩm bán tốt nhất”. Ý tưởng đầy đủ, metric facts và canonical ranking reference vẫn nằm trong summary/chi tiết; không rút gọn thành tên ý tưởng trống basis.

- `niches[name].grounded_analysis`: facts/quotes/ideas/limitations đã chấp nhận; null nếu data-only.
- `ai_validation` từng niche và metadata/diagnostics: policy/context, tối đa hai attempt, outcome và lỗi an toàn; không có raw phản hồi bị từ chối.
- `analysis_summary`: context fact/quote/idea đầy đủ, policy selection, ranking reference, warnings và danh sách slot.
- `top_ideas`: alias đúng `analysis_summary.top_ideas`; `metadata.top_ideas_status` = available khi có ba, partial khi một/hai, unavailable_no_grounded_ranked_ideas khi không có.
- Markdown và UI chỉ hiển thị cùng dữ liệu; UI không đánh lại slot/ranking, không hiển thị free-form ideas cũ, không lấy URL/financials do model cung cấp. Link được dựng lại từ evidence gốc, kiểm tra marker/digest/citation trước khi hiển thị và escape text.

Diagnostics collection + quality/ranking được lưu trước AI như cũ, sau phân tích mới thêm audit và kết quả grounded. Tại mốc giai đoạn 8, policy là `live-only-v8`; cache v7 không được coi là đã qua validator mới. Canonical `ResearchResult` được triển khai ở giai đoạn 9, Web input/tab/jobs ở giai đoạn 10 và concurrency nguồn ở giai đoạn 11.

Audit offline nhánh thiếu dữ liệu, không kiểm tra lại nguồn đã pass:

    .venv\Scripts\python -B -m scripts.audit_grounded_phase08

[Audit thật giai đoạn 8](reports/verification_phase08/README.md): giữ 2 Trends + 20 ASIN, Reddit 0; insufficient_data, deterministic, 0 generation, 0 idea/Top 3. Đây không phải live run đủ điều kiện để chứng nhận model thực tế làm đúng schema/grounding; cần nguồn niche-support phù hợp trước khi có acceptance đó.

Các báo cáo ngày 20/10/2026 đã được đánh dấu **LEGACY / DEMO**. Cache cũ bị API từ chối, báo cáo cũ nằm trong legacy_reports. Xem [reports/README.md](reports/README.md); không dùng chúng làm báo cáo mẫu để nộp.

## Canonical ResearchResult — giai đoạn 9

Luồng xuất duy nhất: `build_research_result(...)` → một `ResearchResult` → `ReportRepository.publish(result)` → Markdown, JSON/cache và HTTP API. Builder không có I/O, gọi model hay scoring; ranking vẫn chỉ được tính một lần ở `RankingService`. Reporter không có collector, đồng hồ, model hoặc logic tính lại điểm.

- `RunContext` ghi ngữ cảnh thực thi; builder tập hợp metadata/niche section và tính khoảng giá một lần theo từng currency. `ResearchResult` sở hữu bản sao độc lập, đóng băng đệ quy cả map/list/record/provenance; sửa input hoặc bản JSON trả về không thay đổi snapshot này.
- `research-result-v1` giữ các field API cũ; `ranking`, `top_ideas`, `source_health` chỉ là alias do serializer cấp, không phải nguồn tính toán thứ hai. Pipeline vẫn trả dict cho CLI/Web tương thích; đọc cache dựng một snapshot được kiểm tra mới tại biên đọc, không chạy lại research.
- Validator đối chiếu mode/model thực dùng và đã thử, status/quality, số lượng, source health, digest của record sau gate, raw/derived metric aliases, request/timestamp gốc, ranking digest, nội dung idea và link trong summary. Không coi `False` là số đo `0`. Đây là kiểm tra nhất quán, không chạy lại công thức scoring hay xác minh ngữ nghĩa thị trường.
- Header Markdown và Web lấy đúng metadata đã lưu: run ID, thời gian, requested/actual mode, model dùng/đã thử và nguồn. `partial`/`failed` có cảnh báo nổi bật. Phụ lục giữ tất cả evidence của record/listing được xuất, URL, retrieved_at, request/dependency IDs và dấu cache; cùng evidence dùng ở nhiều niche vẫn giữ từng liên kết niche.
- `ReportGenerator.render(ResearchResult)` thay API kwargs `generate(...)` cũ. Dùng `ReportRepository.publish(result)` để lưu; không tự dựng một dict đầu ra hoặc sửa Markdown riêng. `save_latest(dict)` chỉ còn là writer tương thích mức thấp; cache ghi qua nó vẫn bị validator ở biên đọc kiểm tra, không được tự tin cậy.

Cache `live-only-v9` phải có đầy đủ contract/envelope: nội dung JSON, alias, Markdown render lại và checksum SHA-256 khớp nhau. Cache thiếu field, sai alias/path/digest, Markdown lệch JSON, duplicate key, NaN/Infinity/float overflow, Unicode lỗi, cây vượt ngân sách hoặc dữ liệu cũ bị từ chối; không tạo metadata/kết quả thay thế. Không tự nâng cache v8 trở xuống lên v9. Tại giai đoạn 9, `/api/run` trả publication đồng bộ; từ giai đoạn 10, `/api/run` trả job và `/api/jobs/ID/result` trả nguyên publication đó. `/api/latest` vẫn chỉ đọc cache thật; JSON HTTP có `Cache-Control: no-store`.

Giới hạn xuất/đọc cache 32 MiB; snapshot tối đa 2.000.000 JSON nodes, depth 48, số hữu hạn trong miền số an toàn của JavaScript. Vượt giới hạn thì fail rõ ràng, không cắt record/evidence ngầm. Ngân sách AI riêng của giai đoạn 8 không thay đổi. Markdown và latest JSON được ghi qua file tạm + flush/fsync + replace, chỉ thay latest sau khi Markdown đã ghi thành công; không đọc file Markdown ngược để dựng kết quả. Đây là atomic **từng file**, không phải transaction hai file: lỗi thay latest có thể để lại report riêng lẻ, nhưng giữ cache trước đó. Tên file theo full run ID; danh sách báo cáo sắp theo thời điểm sửa file thay vì thứ tự UUID.

File Markdown được ghi UTF-8/LF trên cả Windows để bytes khớp nội dung/checksum canonical, không chỉ giống nhau sau chuẩn hóa xuống dòng.

Checksum không phải chữ ký/xác thực: người có quyền ghi thư mục output có thể sửa và băm lại toàn bộ dữ liệu. Cần bảo vệ quyền filesystem khi triển khai; cơ chế này không chứng minh dữ liệu provider đúng, không thay validator giai đoạn 6/8, cũng không biến Web loopback thành dịch vụ production public có authentication.

Audit offline dữ liệu thật, không gọi lại nguồn hoặc AI:

    .venv\Scripts\python -B -m scripts.audit_publication_phase09

[Kết quả audit giai đoạn 9](reports/verification_phase09/README.md): 2 Trends + 20 ASIN từ snapshot thật, Reddit 0, 22 evidence; Markdown/JSON/cache đồng nhất, `partial / insufficient / deterministic`. `execution_kind=offline_publication_audit` và cảnh báo phân biệt request lịch sử với request mới; timestamp/request nguồn được giữ nguyên. Không ghi đè cache nghiên cứu chính tại reports/, không đưa fixture vào audit, không xác minh positive live Ollama end-to-end.

## Web input và jobs — giai đoạn 10

`ResearchRequest`/`NicheInput` bất biến là intent có giới hạn, tách biệt record/evidence. Web không nhận endpoint, credential, model override, collector, output path hoặc flag `fast_mode`. CLI `--fast` hiện có không đổi. API cũ gửi `{fast_mode: ...}` phải chuyển sang contract mới, không được tự đoán/nâng payload.

Giới hạn Web: body UTF-8 JSON 32 KiB; category/tên niche tối đa 200 ký tự, 3–5 niche duy nhất; 1–8 seed/niche, mỗi seed tối đa 200 ký tự và không trùng; tối đa 4 subreddit/niche, tên 2–21 ký tự chữ/số/underscore. Không tự tạo subreddit cho niche mới. Geo dùng định dạng Trends (`US`, `VN`, `US-CA`, rỗng = toàn cầu); timeframe dùng whitelist/cặp ngày hợp lệ của `TrendsSettings`. Unknown field, duplicate JSON key, control/surrogate, kiểu sai, NaN/Infinity/overflow và input vượt giới hạn bị từ chối trước worker.

Geo/timeframe chỉ áp dụng cho Trends. Amazon Web query theo tối đa hai seed đầu tiên trên marketplace US; không âm thầm dùng hub tổng làm niche-support. Reddit dùng subreddit × seed và cửa sổ thời gian riêng theo cấu hình server. Provider budgets/timeout/retry vẫn giữ nguyên; cấu hình provider chặt hơn input có thể gây cảnh báo/failure nguồn, không được bỏ qua guard hoặc tạo record thay thế.

Kiểm tra geo/timeframe là kiểm tra định dạng/whitelist, không bảo đảm provider có dữ liệu cho mọi mã vùng/khoảng thời gian. Trường hợp nguồn không hỗ trợ hoặc không trả mẫu được giữ thành warning/partial/failed thực tế.

Pipeline nhận request đã kiểm tra, truyền đúng tham số xuống collector, lưu `metadata.research_input` cùng kết quả và đưa input vào Markdown dưới nhãn **yêu cầu truy vấn**, không phải dữ kiện thị trường. Validator đối chiếu danh mục/mode/thứ tự niche và geo/timeframe/seed của keyword thực nhận. Cache canonical v9 cũ không có intent vẫn đọc được nếu qua contract giai đoạn 9, không tự thêm input vào lịch sử.

API cùng origin, chỉ loopback:

| Endpoint | Hành vi |
|---|---|
| `GET /api/config` | Defaults truy vấn, giới hạn, model cấu hình, CSRF token và chu kỳ polling; không có metric thị trường |
| `POST /api/run` | JSON gồm category, niches `{name, seed_keywords, subreddits?}`, geo, timeframe, mode tùy chọn (mặc định ollama). Cần `X-CSRF-Token` và `Idempotency-Key` 16–64 ký tự chữ/số/gạch nối; trả 202 + job ID |
| `GET /api/jobs/active` | Job đang chạy hoặc null; phục hồi theo dõi khi tải lại trang |
| `GET /api/jobs/ID` | queued/running/completed/failed, thời điểm thực thi, callback tiến trình thật và sequence; không kèm lại toàn bộ report ở mỗi poll |
| `GET /api/jobs/ID/result` | Publication nguyên vẹn của đúng job, không phải latest của job khác; 202 nếu chưa xong, 500 khi thực thi lỗi, 404 khi không tồn tại/hết hạn |
| `GET /api/latest` | Cache thật đã kiểm tra; legacy/invalid/no_report đều success=false, không parse Markdown làm fallback |

Một worker research tại một thời điểm trong mỗi server process; từ giai đoạn 11, bên trong job có tối đa ba worker nguồn độc lập (chi tiết bên dưới). Key giống nhau + input chuẩn hóa giống nhau trả lại job cũ trong thời hạn lưu; key giống/input khác trả 409, job khác đang chạy trả 429. Frontend không tự retry POST; poll đọc có tối đa 3 lần phục hồi lỗi kết nối liên tiếp, chỉ hiển thị bước server đã báo. Job completed nghĩa worker đã hoàn tất, không đồng nghĩa research success: publication vẫn có thể partial/failed.

Job store giữ tối đa 8 job, TTL 1 giờ tính từ hoàn tất; job đang chạy không bị TTL xóa. Mỗi result tối đa 32 MiB, tổng result bytes trong RAM tối đa 64 MiB; kết quả cũ bị loại trước khi vượt ngân sách. Kết quả lưu dưới dạng JSON bytes độc lập, không chấm điểm/serialize lại mỗi poll. Đây là giới hạn payload bytes, không phải cam kết tổng RAM process. Job/progress/idempotency là bộ nhớ nội bộ, không bền qua restart và không chia sẻ giữa nhiều process. Publication/diagnostics vẫn được lưu như giai đoạn 9. Chưa có cancel/hard-kill job; đóng tab không dừng thu thập, tắt server/process không được coi là job đã hoàn tất.

Server từ chối bind public host, Host không thuộc loopback/port hiện tại, Origin khác hoặc Fetch-Metadata cross-site/same-site, CSRF sai/thiếu, header framing mơ hồ, non-JSON/charset/body encoding không hỗ trợ. Không bật CORS. Có CSP (không inline script/handler), frame deny, nosniff, no-referrer, no-store; asset theo allowlist và đường dẫn thực nằm trong Web root. Font ngoài được bỏ, dashboard không tự gọi dịch vụ khác khi mở trang. Traceback/private diagnostics giữ trong log server kèm job ID, không phản chiếu chi tiết cho client.

CSRF/loopback không thay thế authentication hoặc phân quyền nhiều người dùng; không triển khai app này public/reverse proxy/multi-worker bằng cách nới Host/CORS. Distributed queue, durable jobs, multi-tenant auth và concurrency provider nằm ngoài giai đoạn 10.

Tab/niche/pane sinh từ tên và dữ liệu canonical (không còn 3 tên hardcode), ID dùng chỉ số an toàn; hỗ trợ keyboard/ARIA. Badge phân biệt Live, Partial, Failed, Cached, Not configured và Snapshot lịch sử, không gắn Live mới cho dữ liệu cache/audit. Confidence/breakdown vẫn đọc từ ranking service, không tính lại trên trình duyệt. Metrics chưa có báo cáo là unknown, không lấy số niche trong form làm số niche đã nghiên cứu.

Kiểm chứng giai đoạn 10: **110 Python mới + 5 ca cũ đổi contract; 25 UI mới + 2 ca bị ảnh hưởng pass**. Không full suite hoặc chạy lại nguồn/provider đã pass. Chạy theo ca mới/ảnh hưởng; khi sửa lỗi chọn từng ca, có thêm một ca liền kề được chạy lại khi xử lý lỗi fixture do ID test quá dài, không lặp cả nhóm pass. Fixture/response cách ly trong tests/tmp, không phải dữ liệu nghiên cứu. UI tests dùng DOM/transport doubles, chưa phải xác nhận layout/browser end-to-end thực tế.

Audit thật chỉ đọc qua HTTP loopback:

    .venv\Scripts\python -B -m scripts.audit_web_phase10

[Manifest giai đoạn 10](reports/verification_phase10/README.md): API trả nguyên publication giai đoạn 9 từ snapshot thật (2 Trends, 20 ASIN, 0 Reddit, gate insufficient), ba GET loopback, không tạo job, không gọi provider/AI hoặc thay timestamp/cache nguồn. Không dùng nó để chứng nhận một live job mới đủ nguồn hoặc positive Ollama end-to-end.

## Hiệu năng và snapshot — giai đoạn 11

Pipeline tách collection khỏi processing/AI/publication: chỉ submit **ba task nguồn**, không tạo task cho mọi niche. Mỗi worker tạo, tái sử dụng tuần tự và đóng HTTP session/provider riêng; mỗi nguồn đi qua các niche đúng thứ tự input. Kết quả, warning và scoring input được lắp lại theo thứ tự input/source cố định, không theo thứ tự hoàn tất. Progress callback được tuần tự hóa. Không parallel hóa AI hoặc tính lại ranking.

Concurrency provider là giới hạn **trong một process**, áp dụng qua nhiều lượt gọi pipeline; mặc định một lượt collect/provider, tối đa bốn nếu cấu hình chủ động. Cùng instance HTTP/collector luôn single-threaded; từ chối dùng chung state giữa các source. Collector inject vào pipeline được mượn, không bị đóng hoặc đưa vào cache chung. Gate có thời gian chờ và tối đa 256 người dùng/chờ mỗi lease; hết hạn trả `provider_busy` không gửi request cho thao tác đó. Lease dọn sau khi hết người dùng; cache key single-flight ngăn stampede khi hai run trùng truy vấn. Không phải quota/rate limiter phân tán và không bảo đảm provider không trả 429.

Policy ở `src/collectors/performance_settings.py`; tất cả biến dưới có prefix `TREND_PERF_` và được validate trước collection:

| Phần tên biến | Mặc định | Giới hạn/ý nghĩa |
|---|---:|---|
| MAX_WORKERS | 3 | 1–3; đặt 1 để chạy tuần tự |
| GOOGLE_TRENDS_CONCURRENCY / AMAZON_CONCURRENCY / REDDIT_CONCURRENCY | 1 mỗi nguồn | 1–4; mỗi run vẫn chỉ một worker mỗi nguồn |
| SLOT_WAIT_SECONDS | 30 | 0.01–300 giây cho mỗi lease, không phải deadline toàn job |
| GOOGLE_TRENDS_CACHE_TTL | 300 | 0–3600 giây; 0 tắt cache nguồn |
| AMAZON_CACHE_TTL | 300 | 0–3600 giây |
| REDDIT_CACHE_TTL | 120 | 0–3600 giây |
| CACHE_MAX_ENTRIES | 64 | 1–512, cache RAM dùng chung |
| CACHE_MAX_BYTES | 33554432 | 1024–134217728 byte JSON tương đương, không phải tổng RAM/RSS |
| SNAPSHOT_MAX_BYTES | 8388608 | 1024–33554432 byte mỗi file, không vượt run limit |
| SNAPSHOT_RUN_MAX_BYTES | 67108864 | 1024–268435456 byte payload snapshot mỗi run; manifest riêng tối đa 512 KiB |

Cache key SHA-256 gồm source, toàn input niche (bao gồm tên/keyword/geo/timeframe/subreddit, giữ thứ tự query), provider/parser namespace, settings đã resolve, transport policy, TTL và data policy. OAuth có scope HMAC process-local theo credential, không lưu credential/token vào key/snapshot. Cache chỉ nhận collection success đã qua validation, không warning/rejected/duplicate, không cache lại snapshot cũ. Giữ bản sao riêng, đánh dấu cache cho cả primary và mọi listing provenance/trace; giữ ID/timestamp gốc, không ghi thêm HTTP attempt giả.

TTL tính theo tuổi evidence cũ nhất, không chỉ thời điểm insert; hit không gia hạn. Kiểm tra cả monotonic và UTC, kể cả sau khi copy; archive quá hạn không trở thành dữ liệu mới. LRU bounded; expired/missing dẫn tới fetch thật, fetch lỗi giữ failed/partial, không dùng stale fallback. Cache không tồn tại sau restart; đổi ngân sách cache chung cần restart để không tạo nhiều cache RAM cùng lúc. Đây không phải `latest_data.json` hay browser cache.

Snapshot `validated-collector-input-v1` giữ toàn bộ record **được chấp nhận tại biên collector**: series/metric gốc, listings, post và provenance/trace đã che secret, warning/statistics. Không giữ record bị loại hoặc HTTP/HTML nguyên xi; không phục vụ replay parser từ wire bytes. Tên file dùng vị trí + source allowlist trong `snapshots/RUN_ID/`; run ID 32 hex, không lấy tên/URL người dùng làm path, từ chối collision và path escape. Mỗi file ghi tạm + flush/fsync + replace; manifest commit cuối chứa byte count/SHA-256. Reader chỉ đọc JSON hữu hạn, kiểm tra schema/identity/đủ nguồn/checksum/path; không tự thực thi hay coi snapshot là lần thu thập mới.

Lỗi lưu snapshot hoặc vượt ngân sách làm run thất bại **trước xử lý/AI/publication**, không cắt evidence ngầm; có thể giữ thư mục partial không manifest để chẩn đoán. Diagnostics có `snapshot_manifest`, `collection_policy`, `transport_policy`. Atomic latest và tên Markdown full run ID kế thừa giai đoạn 9, không đổi schema publication. Checksum không phải chữ ký; giới hạn quyền thư mục output và quản lý retention/backup/dung lượng đĩa bên ngoài, không tự xóa dữ liệu thật. Không expose snapshot qua static Web allowlist.

HTTP timeout/retry ở `HTTPPolicy` và `TREND_HTTP_*`: connect tối đa 120 giây, read tối đa 300, tổng wait retry tối đa 300; streaming body mặc định 4 MiB, lỗi vượt size không retry và response luôn được đóng. Owned session tắt ambient proxy/`.netrc` (`trust_env=False`), vẫn hỗ trợ auth được provider truyền tường minh; không thay đổi session mượn. Read timeout là thời gian chờ socket, **không phải hard deadline toàn response/job**, không có cưỡng chế kill thread hay cam kết chống mọi slow-stream/giới hạn tổng RSS. Môi trường cần proxy phải thiết kế cấu hình tường minh trước khi triển khai, không tự dùng credential môi trường.

Loại `httpx`/`praw` không còn import khỏi requirements; giữ `requests`, `pytrends` (vẫn dùng adapter/parser/widget) và dependency thực dùng. Không uninstall hay sửa môi trường đã cài.

Kiểm chứng: **79 ca Python mới + 6 ca cũ bị ảnh hưởng pass**, không lặp ca đã pass, không full suite/coverage hoặc re-fetch provider. Fixture chỉ trong tests/tmp. Hai file test mới kiểm tra overlap/giới hạn provider, single-flight, TTL/LRU/copy, giữ series/provenance, strict JSON/path/checksum/atomic failure/byte caps, đóng tài nguyên, progress/thứ tự và lỗi lưu trước AI. Có ca hai lượt pipeline fixture liên tiếp xác nhận cache hit vẫn xuất JSON/Markdown/snapshot đồng nhất, không tạo request/ID/thời điểm mới. Không đổi UI nên không chạy lại UI tests cũ.

[Audit snapshot thật](reports/verification_phase11/README.md) giữ 2 Trends + 20 ASIN hub tổng + 0 Reddit, ID/timestamp gốc, roundtrip đúng; **0 network / 0 AI**, không publish lại latest hoặc chèn archive vào cache fresh. Không đo tốc độ mạng thực, không chứng nhận positive live research/OAuth/Ollama hay accuracy production. Công cụ audit giai đoạn 12 được mô tả bên dưới; giai đoạn 13 chưa triển khai.

## Kiểm chứng và audit dữ liệu — giai đoạn 12

[Manifest kết quả](reports/verification_phase12/manifest.json) phân biệt kiểm thử fixture, audit archive thật và request provider thật. **67 ca mới pass**, không chạy lại test cũ/nhóm đã pass. Ba ca ban đầu fail được sửa rồi chạy lại đúng node ID: hai lỗi bọc exception của codec và một assertion symlink phụ thuộc cách resolve path. Không chạy full suite/UI/nguồn Trends hoặc Amazon đã kiểm tra trước đó. Kết quả pass không đồng nghĩa toàn dự án đã được kiểm thử lại trên phiên bản hiện tại.

`src/verification/` là lớp kiểm chứng **offline, chỉ đọc**, không nằm trên đường publish/cache read thông thường và không sửa publication để làm audit pass:

- Codec đóng khôi phục kiểu record/series/listing/provenance/request/validation từ snapshot JSON, giới hạn byte/node/depth/container; không pickle, dynamic import, eval hoặc tự thực thi nội dung nguồn. Chạy lại validator retained evidence và metric Trends; candidate bị loại không có raw record để parse lại, chỉ đối chiếu thống kê.
- Đối chiếu chính xác snapshot với record và request journal publication, giữ nguyên kiểu số/null/zero, nguồn/ID/query/time/cache flag. Recompute quality, source health, khoảng giá tách currency và ranking theo policy đã lưu; policy không có field tự do và không tự reweight.
- Dựng lại các section từ record. Với AI: khôi phục policy/context, đối chiếu lại fact/quote/proposal/basis với catalog nguồn và so toàn bộ grounded output, không gọi model thêm lần nữa. So summary, aliases, checksum, Markdown embedded **và file Markdown thực**. Không chỉ tin checksum hoặc so báo cáo với chính số đã bị sửa trong JSON.
- Kê **mọi ký tự số Unicode** trong Markdown, giữ token/line/column và section reference; kê cả structured numeric fields bằng JSON Pointer. Bản kê bao gồm URL/ID/ngày/thông số/template/source text; không coi chúng đều là số đo thị trường. Text phần dữ kiện phải tái dựng khớp nguồn; không dùng danh sách các số xuất hiện đâu đó để hợp thức hóa claim mới. Ví dụ chèn `60/100`, `9999%`, số full-width/phân số hay claim bằng chữ vào phần phân tích đều bị từ chối, kể cả khi tự tính lại checksum/Markdown.

Audit một publication đã có snapshot giai đoạn 11:

    .venv\Scripts\python -B -m scripts.audit_publication_phase12 --publication reports/latest_data.json --snapshots reports --snapshot-run-id RUN_ID --output reports/verification_phase12

Không truyền tham số thì công cụ chọn rõ publication archive thật giai đoạn 9 và snapshot collector giai đoạn 11, **không lấy archive làm lần thu thập mới**. Run live phải khớp run ID snapshot; offline publication audit được đối chiếu archive khác run ID nhưng toàn evidence/trace phải trùng. Exit 0 chỉ khi `consistent_with_collector_snapshots`; sai/mất/hỏng artifact exit 1 và diagnostics lỗi chỉ chứa code/path, không có exception/body/credential. Audit artifact tối đa 32 MiB, numeric occurrences/field/block-match cũng có cap, vượt giới hạn fail rõ không cắt ngầm. Mỗi audit có ID riêng; không ghi latest/Markdown nghiên cứu mới.

[Audit thật đã lưu](reports/verification_phase12/diagnostics/5e6305a72429435f8b8e7086fe418d9d.json): **1.219 numeric occurrences + 625 structured numeric fields**, đối chiếu 2 Trends + 20 ASIN hub tổng + 0 Reddit, kết quả vẫn partial/insufficient, ranking/ideas rỗng. 0 network/0 AI, giữ timestamp/ID gốc. Đây là kiểm tra consistency archive, không chứng minh authenticity/provider truth, accuracy thời điểm hiện tại hoặc market fit. Calculator audit tái dùng hàm thuần production nên không độc lập phát hiện mọi lỗi công thức chung; unit tests riêng có oracle cho công thức/giá trị. Số trong metadata/input/warning và source quote chỉ được phân loại, không tự chứng nhận ý nghĩa thị trường của văn bản đó. Chi tiết ở [phạm vi audit](reports/verification_phase12/README.md).

### Live integration bật tường minh

`tests/live/` có test riêng cho ba provider thật. Mặc định skip, không tự dùng cache/fixture để thay HTTP. Chỉ fixture chặn HTTP của **thư mục live** được thay thế khi source có `--live-provider`; unit tests ngoài thư mục vẫn chặn outbound. Probe lấy query config, không cho chọn URL tùy ý; giới hạn một attempt/operation, connect 3s/read 8s, redirects tối đa 2, body 2 MiB, tắt cache/Suggest, Amazon một query, Reddit một subreddit × seed; không gọi AI. Không phải hard deadline toàn job hay phép kiểm tra toàn bộ accuracy của provider. Probe observed nghĩa có record thật qua validation, không bảo đảm đủ nguồn/đại diện thị trường; partial giữ warning.

Ví dụ chọn riêng Reddit khi cần kiểm tra lại sau thay đổi quyền truy cập/cấu hình:

    .venv\Scripts\python -B -m pytest -q tests/live/test_providers_live.py --live-provider=reddit --live-output=reports/verification_phase12/live

Có thể chọn `google_trends`/`amazon` hoặc lặp option để chọn nhiều nguồn; không chạy lại nguồn đã pass nếu không có thay đổi cần xác minh. Khi không có mạng, bị chặn hoặc trả zero record: test được chọn **fail**, còn nguồn không chọn skip; diagnostics thật giữ status/trace, không gọi mock/fallback. OAuth dùng credential môi trường có sẵn; không có credential thì auto public JSON và không tự downgrade OAuth lỗi.

Lượt Reddit thật ngày 22/10/2026: **HTTP 403, 1 request, 0 record**, public JSON vì chưa có credential. [Diagnostics](reports/verification_phase12/live/diagnostics/c1d491b84ed44a42adc846128b22b202.json). Test live fail có chủ đích giữ đúng thực trạng, không retry vòng lặp/bypass chặn nguồn. Trends/Amazon không được chọn lại; thành công/partial lịch sử vẫn nằm ở giai đoạn 3–4, không gán cho code/mạng hiện tại. OAuth/permalink và positive live Ollama đủ evidence vẫn cần xác minh; acceptance live chưa đóng.

### Coverage có phạm vi đo rõ ràng

Tooling phát triển (không cần cho runtime):

    .venv\Scripts\python -m pip install -r requirements-dev.txt

[Báo cáo coverage JSON](reports/verification_phase12/coverage/coverage.json) bằng **coverage.py 7.16.2**, branch/thread enabled và `source=src`: **line 65.66% (3096/4715), branch 43.80% (671/1532), combined 60.30%**. Chỉ đo **7 ca mới cuối trên mã đã chốt + retry đúng ca symlink fail**, không phải coverage từ full suite hoặc toàn bộ 67 ca. Không chạy lại ca đã pass chỉ để tăng tỷ lệ. Dữ liệu coverage gộp trong lúc mã thay đổi (`.coverage-audit`) chỉ giữ lịch sử, **không dùng cho tỷ lệ công bố**. Manifest có scope, source hashes, hash report và kết quả JUnit từng đợt kể cả fail/skip; chưa đặt coverage gate/claim production-ready.

Đọc lại số đo đã có mà không chạy test:

    .venv\Scripts\python -B -m coverage report --data-file=reports/verification_phase12/coverage/.coverage-current

Nếu sau này cần đo suite đầy đủ, phải chạy trong lượt kiểm chứng riêng được chấp thuận; không lấy các tỷ lệ này làm tỷ lệ full-suite. Giai đoạn 12 không tạo báo cáo mẫu/video giai đoạn 13.

## Cấu trúc mã nguồn

- src/models: domain records và CollectionResult.
- src/collectors: adapter live; http_policy/http quản lý timeout/retry; context giữ nhật ký mỗi lần collect; validation kiểm tra provenance.
- src/collectors/performance_settings.py, collection_runtime.py, concurrency.py, collection_cache.py: policy hữu hạn, worker theo provider, lease process-wide và cache collection sau validation.
- src/collectors/trends_provider.py, trends_settings.py, trends_cache.py: interface/provider, giới hạn cấu hình và cache Google Trends.
- src/collectors/amazon_settings.py, amazon_parser.py, amazon_validation.py: giới hạn request/URL, parser thuần và kiểm tra dữ kiện/listing provenance.
- src/collectors/reddit_settings.py, reddit_provider.py, reddit_parser.py, reddit_validation.py: input có giới hạn, adapter OAuth/public, đọc post thật và kiểm tra contract v5.
- src/models/community.py, src/analyzers/reddit_evidence.py: trích dẫn ứng viên pain point có evidence ID, không tạo claim thị trường giả.
- src/collectors/evidence_validation.py, trends_validation.py: primitives có giới hạn và đối chiếu series/metric với nguồn; validation.py là biên schema/dedup/statistics chung.
- src/models/quality.py, identities.py, src/processors/data_quality.py: thống kê bất biến, khóa định danh ổn định và một quyết định gate cho mỗi niche.
- src/processors: chuẩn hóa, tính khoảng giá mẫu, điều kiện dữ liệu tối thiểu.
- src/models/commerce.py, src/processors/amazon_values.py: định danh/listing, price Decimal và parser từng giá trị Amazon.
- src/processors/trend_metrics.py và src/models/trends.py: tính toán thuần và schema series/metrics.
- src/ranking/policy.py, signals.py, service.py, src/models/ranking.py: policy có version, công thức thuần, service duy nhất và kết quả scoring bất biến.
- src/analyzers/analysis_policy.py, evidence_catalog.py, grounded_schema.py, strict_json.py, grounded_validator.py: ngân sách, catalog bất biến, schema dùng chung và đối chiếu dữ kiện.
- src/analyzers/ollama_client.py, llm_analyzer.py: transport local hữu hạn, một lượt repair và fallback dữ kiện.
- src/models/analysis.py, src/analyzers/grounded_summary.py: kết quả nguồn-đối-chiếu bất biến và summary/slot không tạo metric giả.
- src/reporters/grounded_renderer.py: template factual từ metric và nhãn đề xuất chưa kiểm chứng.
- src/reporters/evidence_renderer.py: render dữ kiện khi không dùng được AI.
- src/reporters/report_generator.py: render Markdown.
- src/models/research_result.py, research_integrity.py, research_views.py: snapshot publication bất biến, đối chiếu record và các view.
- src/processors/research_result_builder.py: điểm tập hợp kết quả duy nhất và RunContext.
- src/reporters/result_codec.py: wire envelope có version/checksum, đọc JSON hữu hạn và kiểm tra đồng bộ Markdown/cache.
- src/reporters/ranking_renderer.py: chỉ hiển thị canonical ranking/breakdown, không tính điểm.
- src/reporters/report_repository.py: ghi cache/diagnostics nguyên tử, từ chối cache chính sách cũ.
- src/reporters/collection_snapshots.py: snapshot collector theo run ID, manifest-last, giới hạn byte và reader checksum/path strict.
- src/verification: codec snapshot đóng, audit publication/section/numeric ledger chỉ đọc và probe provider thật opt-in; không thay luồng research runtime.
- src/pipeline.py: điều phối; nhận collector dependencies để kiểm thử từng nhánh.
- src/web: API và dashboard.
- src/models/research_request.py: intent Web bất biến và validation trước I/O.
- src/web/jobs.py: single-flight job store, idempotency, retention và tiến trình từ callback thật.
- src/web/static/js/form.js, app.js, api.js: editor intent, theo dõi job và transport cùng origin; không bổ sung dữ kiện thị trường.

## Kiểm thử

    .venv\Scripts\python -m pytest -q

Kiểm tra trình bày trạng thái và giá trị thiếu trên giao diện (Node.js, không cần npm package):

    node --test tests/test_ui.cjs

Unit test chặn HTTP ngoài hệ thống. Test parser sử dụng fixture cách ly trong tests/; chúng không phải dữ liệu nghiên cứu và không được đưa vào runtime.

Bộ kiểm thử bao gồm lỗi nguồn, metric thiếu, score bằng 0, chế độ không AI, Ollama lỗi, quality gate, pipeline partial/failed, cache legacy, HTTP API local, timeout/retry, Retry-After, redirect, redaction và provenance. Integration HTTP dùng server loopback thực, không truy cập provider bên ngoài. Test pass không chứng minh mọi nguồn live đang hoạt động. Các lần chạy live được ghi riêng trong plan.md và reports/verification_phase01/, reports/verification_phase02/.

Giai đoạn 3: 45 test mới và 8 test Trends bị thay đổi đã pass; 1 test UI mới pass. Không chạy lại toàn bộ test cũ. Lần kiểm tra Google Trends thật lưu tại reports/verification_phase03/: 2 keyword, mỗi keyword 93 điểm đo (1 partial bị loại khỏi tính toán), 6 HTTP attempt, thành công sau một lần retry 429; Google Suggest được tắt trong lần kiểm tra này để giảm request. Đây là kiểm tra riêng nguồn Trends, không chứng nhận toàn pipeline hay AI.

Giai đoạn 4: 76 test Python mới và 1 test UI mới pass, chỉ chạy test mới/test chưa pass; fixture cũ được cập nhật theo contract Amazon v4. Chạy riêng Amazon thật: 3 response 200, 20 ASIN từ trang Best Sellers tổng, status partial vì Search/Movers không có card hợp lệ. Chẩn đoán tiếp: Search 503 sau retry, Movers chỉ có trang hub không có listing; một URL sản phẩm mở được và khớp ASIN/title. Xem reports/verification_phase04/. Không dùng các sản phẩm từ hub tổng này để khuyến nghị niche Christmas; chưa xác minh thủ công toàn bộ 20 URL, không chạy lại Trends/Reddit hoặc toàn pipeline.

Baseline trước thay đổi: 19 test pass. 12 trường hợp hồi quy mới đã được chạy và đều fail trên code cũ trước khi sửa. Các giai đoạn trước 12 chưa đo coverage; số đo chọn lọc của giai đoạn 12 và giới hạn ở phần trên, chưa có full-suite coverage.

Giai đoạn 5: 145 test Python mới + 3 test Reddit vừa đổi contract và 2 test UI mới đã pass. Chỉ chạy phần mới/bị ảnh hưởng; ba ca AI thiếu điều kiện fixture được sửa và chỉ chạy lại đúng ba ca fail. Test bao phủ OAuth, expiry/refresh hữu hạn, không downgrade/redirect/ambient .netrc, redaction, giới hạn input/query/body, ID dedup, cửa sổ thời gian, unknown/zero, contract provenance, pain-point quotes và pipeline partial. Không chạy lại toàn bộ test cũ hoặc Trends/Amazon live.

Kiểm tra Reddit thật ngày 21/10/2026: một subreddit/seed từ config (r/giftideas, christmas gift ideas), public JSON vì chưa có credential; 2 HTTP attempt lỗi connection_error, status failed, 0 post, không fallback. Diagnostics: reports/verification_phase05/diagnostics/9f35f55a6a3445f993abbd279e797a47.json. Chưa xác minh OAuth, score/comment hoặc permalink live; không tạo báo cáo thị trường và không tuyên bố acceptance live đã pass.

Giai đoạn 6: 128 test Python mới + 2 ca cũ bị ảnh hưởng trực tiếp và 4 test UI mới đã pass. Một lỗi fixture thiếu URL được sửa; chỉ chạy lại 91 ca chưa pass, không chạy lại 15 ca đã pass hoặc toàn bộ suite. Các ca bổ sung sau đó chỉ kiểm tra hành vi mới về nullable points, state/digest, signal text, giới hạn container, phân biệt bool với số, warning/timestamp cấp collection và credential trong record query. Fixture cũ được cập nhật theo contract series/ID, không có bypass trong runtime; chưa đo coverage toàn dự án.

Audit offline trên snapshot live thật đã lưu: 2 keyword Trends, 20 ASIN Amazon hợp lệ, Reddit 0 post; candidate valid_ratio 22/22 nhưng gate vẫn insufficient vì Amazon là hub tổng và Reddit chưa có evidence. Giữ nguyên timestamp/request ID gốc, không gọi mạng mới và không xuất khuyến nghị. Xem reports/verification_phase06/diagnostics/ba0da4abf898429b9f4816722e73dd0a.json. Đây không phải một lượt live mới hay xác minh lại khả năng truy cập provider; không đưa fixture kiểm thử vào audit.

Giai đoạn 7: 78 test Python mới và 6 test UI mới đã pass. Chạy thành các nhóm mới riêng: 61 + 13 + 4 Python, 5 + 1 UI; một assertion cuối nhầm confidence toàn phần khi chỉ 5/20 primary là Search được sửa và chỉ chạy lại đúng ca fail. Không lặp lại ca đã pass, không full suite hoặc gọi lại provider live. Bao phủ công thức, baseline 0, nullable metrics, fixed weights, confidence, context/batch mismatch, Sponsored/hub/primary scope, tie-break/đồng hạng, thứ tự config, alias/cache/diagnostics/Markdown, input bounds và XSS. Chưa công bố coverage hoặc kiểm định dự báo kinh doanh.

Giai đoạn 8: 210 test Python mới + 9 ca cũ bị ảnh hưởng và 6 test UI mới + 1 ca UI bị đổi nội dung đã pass. Các nhóm mới chạy riêng; một ca summary phát hiện thứ tự metadata ideas chưa ổn định, đã sửa và chỉ chạy lại ca fail, không lặp 58 ca pass cùng nhóm. Không full suite hoặc gọi lại Trends/Amazon/Reddit. Bao phủ schema/metric/citation/quote/basis, JSON không an toàn, sampling minh bạch, snapshot mutation, repair một lần, HTTP/body/deadline, auth/proxy/SSRF/cloud-model preflight, actual mode và đồng bộ output. Fixture và AI response giả chỉ nằm trong tests/thư mục tạm, không phải dữ liệu nghiên cứu. Audit snapshot thật không đủ gate nên không gọi AI; chưa xác minh positive grounded generation end-to-end bằng dữ liệu live đủ nguồn.

Giai đoạn 9: 99 test Python mới + 11 ca bị ảnh hưởng và 3 UI mới pass. Không full suite/re-fetch nguồn. Có một lượt lọc test vô tình khớp tên file và chạy lại nhóm vừa pass; sau đó dùng node ID cụ thể. Fixture chỉ ở tests/tmp. Bao phủ snapshot/cùng object/strict alias, raw digest, metadata/provenance/summary, header/partial warning, cache strict JSON/ngân sách/checksum/path, API no-store/roundtrip, atomic failure, thứ tự report theo thời gian và UTF-8/LF. Audit record thật chỉ xác minh đồng bộ output trên nhánh insufficient, không nâng thành acceptance live đủ nguồn.

## Chi phí

Không gọi API LLM trả phí trong cấu hình hiện tại; Ollama local và các HTTP collector đang dùng có chi phí API trực tiếp $0.00. Chi phí máy, điện và mạng chưa được đo. Thời gian chạy tùy mạng, giới hạn truy cập và model; không cam kết thời gian demo cố định.
