# TASK: Tool AI nghiên cứu xu hướng sản phẩm (MVP)

## Mục tiêu

Làm một bản demo, trong đó **AI tự nghiên cứu và viết báo cáo** về các sản phẩm đang hot, đang được bàn luận hoặc đang bán nhiều, kèm **gợi ý loại sản phẩm công ty nên bán**.

Cách làm, nguồn dữ liệu và công cụ là **do bạn tự chọn**. Chỉ có vài điểm dưới đây là cố định, để mọi người được đánh giá cùng một cách.

---

## Phần cố định

| Mục | Nội dung |
| --- | --- |
| Cách làm | **Mỗi người làm độc lập trên một repo GitHub riêng** |
| Danh mục và niche | **Bắt buộc:** mỗi người chọn **1 danh mục** và **3–5 niche** trong danh mục đó (xem bảng gợi ý bên dưới, hoặc tự đề xuất). Ghi rõ danh mục, các niche và lý do chọn ở đầu `README.md` |
| Hạn nộp | **Thứ 6, 23/10/2026** (demo vào buổi họp cuối tuần) |
| Phạm vi | Chỉ cần chạy được để demo. **Chưa cần deploy, chưa cần chạy tự động theo lịch.** |
| Model AI | Được dùng **model qua API** hoặc **model chạy local** (Ollama, LM Studio…). Ghi rõ model đã dùng trong README |

### Cấu trúc báo cáo (bắt buộc)

Báo cáo **chia rõ theo từng niche**. Mỗi niche có đủ 3 phần sau:

**1. Keyword**
- Các keyword chính và keyword liên quan đang hot / đang tăng trong niche.
- Mỗi keyword kèm tín hiệu cho thấy nó hot (mức tìm kiếm tăng, thứ hạng bán chạy, lượt bàn luận…) và **nguồn (link)**.

**2. Phân tích**
- Niche đang tăng, ổn định hay giảm, và vì sao (mùa vụ, trend mạng xã hội, sự kiện…).
- Khách hàng là ai, họ đang tìm hoặc than phiền điều gì.
- Mức cạnh tranh và khoảng giá tham khảo (nếu lấy được).

**3. Idea sản phẩm**
- 2–3 idea sản phẩm cụ thể trong niche.
- Mỗi idea ghi rõ: **bán cái gì, cho ai, vì sao nên bán bây giờ**, dựa trên keyword và phân tích ở trên.

**Cuối báo cáo:** phần **Tổng kết** xếp hạng các niche theo mức đáng làm, và chọn ra **3 idea tốt nhất** trong toàn bộ báo cáo.

Ngoài cấu trúc trên, bạn muốn thêm gì cũng được (biểu đồ, ví dụ sản phẩm đối thủ, ảnh minh họa…).

### Cần nộp

- [ ] 2–3 báo cáo mẫu do tool tạo ra
- [ ] Video demo 2–3 phút: chạy tool → ra báo cáo
- [ ] Link GitHub kèm `README.md` ngắn, gồm:
  - Dùng những nguồn dữ liệu nào
  - Dùng công cụ / repo / model gì
  - Cách cài đặt và chạy
  - **Chi phí ước tính cho mỗi báo cáo**

---

## Tiêu chí đánh giá chung

| Tiêu chí | Xem gì |
| --- | --- |
| **Chính xác** | Kiểm ngẫu nhiên vài mục, xem có khớp với nguồn không, có bịa số không |
| **Hữu ích** | Gợi ý có đáng để công ty cân nhắc bán không |
| **Tự động hóa** | Từ lúc bấm chạy đến khi ra báo cáo, càng ít thao tác tay càng tốt |
| **Chi phí thấp** | Chi phí mỗi báo cáo (API, tool trả phí) càng rẻ càng tốt |
| **Dễ đọc** | Đọc nhanh, nắm được ý chính |
| **Chạy lại được** | Người khác làm theo README có ra được báo cáo không |

---

## Danh mục và niche gợi ý

Chọn 1 danh mục bên dưới (hoặc tự đề xuất), rồi chọn 3–5 niche trong danh mục đó. Các niche bên dưới là điểm xuất phát, tool nên tự mở rộng ra keyword liên quan.

| Danh mục | Niche gợi ý |
| --- | --- |
| Sách tô màu / hoạt động | coloring book for adults, bold and easy coloring, cozy coloring book, mandala coloring, kids activity book, dot to dot, sticker book |
| Áo thun / quà in hình (POD) | funny teacher shirt, nurse gift, dog mom shirt, retro vintage tee, custom name shirt, matching family shirts, Halloween / Christmas shirt |
| Đồ gia dụng, nhà bếp | kitchen organizer, air fryer accessories, silicone kitchen tools, storage container, mini vacuum sealer, spice rack |
| Decor nhà cửa | wall art printable, LED neon sign, boho decor, minimalist poster, cozy room decor, desk setup |
| Thú cưng | dog toy, cat tree, pet hair remover, pet bandana, personalized pet tag, slow feeder bowl |
| Mẹ và bé | baby milestone cards, montessori toys, busy board, baby bib, nursery decor |
| Văn phòng phẩm, planner | digital planner, printable planner, budget planner, aesthetic stationery, sticker sheet |
| Phụ kiện điện thoại | phone case aesthetic, magsafe accessories, phone grip, phone charm, cable organizer |
| Quà tặng theo mùa | Christmas gift ideas, gift for him, gift for her, personalized gift, Valentine gift, Mother's Day gift |
| Sức khỏe, làm đẹp | skincare tools, gua sha, hair accessories, self care gift box, posture corrector |

**Mẹo chọn niche:**

- **Ưu tiên niche đang tới mùa.** Tháng 10–12 là mùa Halloween, Black Friday, Giáng sinh, nên nhóm quà tặng và đồ trang trí theo mùa sẽ có nhiều tín hiệu xu hướng rõ.
- **Chọn niche hẹp,** ví dụ "cozy coloring book for adults" thay vì "book". Niche hẹp thì báo cáo cụ thể hơn và gợi ý sát hơn.
- **Ghi bộ từ khóa gốc vào README,** để người khác chạy lại được.

## Gợi ý (không bắt buộc)

- **Nguồn dễ lấy:** Google Trends, Amazon Best Sellers / Movers & Shakers, TikTok Creative Center, Etsy, Reddit.
- **Công cụ:** n8n, Python, crawl4ai, Playwright, pytrends, bất kỳ LLM nào. Nên tìm repo có sẵn rồi tùy biến thay vì viết từ đầu.
- **Tiết kiệm chi phí:** dùng model rẻ cho các bước lọc và tóm tắt, chỉ dùng model mạnh ở bước viết báo cáo cuối cùng. Ưu tiên gói miễn phí nếu có.
- **Model local:** chạy bằng Ollama hoặc LM Studio thì chi phí API bằng 0. Gợi ý thử: Qwen, Llama, Gemma, Mistral (bản 7B–14B chạy được trên máy có GPU 8–16GB). Model local thường viết tiếng Việt và tổng hợp kém hơn model lớn qua API, nên có thể kết hợp: model local lo phần lọc và tóm tắt, model API chỉ viết báo cáo cuối. Nếu dùng model local, ghi thêm cấu hình máy và thời gian chạy trong README.

## Lưu ý


- Bị kẹt thì báo sớm, không cần chờ đến ngày nộp.
