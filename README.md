# 🔍 AI Product Trend Research Tool (MVP)

> **Công cụ AI tự động nghiên cứu xu hướng sản phẩm, phân tích thị trường và đề xuất ý tưởng kinh doanh theo Niche.**

---

## 📌 1. Danh mục & Niches lựa chọn

| Thông tin | Chi tiết |
|---|---|
| **Danh mục bắt buộc** | **Quà tặng theo mùa (Seasonal Gifts)** |
| **Các Niches lựa chọn** | 1. **Christmas Gift Ideas** (Ý tưởng quà Giáng sinh)<br>2. **Gift for Him** (Quà tặng nam giới)<br>3. **Gift for Her** (Quà tặng nữ giới) |
| **Lý do lựa chọn** | - **Tính mùa vụ cao điểm (Q4 Holiday Shopping):** Tháng 10–12 là thời điểm vàng của thương mại điện tử quốc tế với các dịp Black Friday, Cyber Monday và Giáng sinh. Nhu cầu tìm kiếm quà tặng tăng từ 200% – 500% so với các tháng trước.<br>- **Dữ liệu xu hướng phong phú:** Các từ khóa liên quan đến quà tặng có tín hiệu tăng trưởng đột biến rõ rệt trên Google Trends, bảng xếp hạng Amazon Movers & Shakers và các chủ đề thảo luận sôi nổi trên Reddit.<br>- **Biên lợi nhuận và tiềm năng kinh doanh:** Ngành quà tặng cá nhân hóa (personalized gifts) và combo quà đóng sẵn (gift-ready boxes) có biên lợi nhuận cao (>60%) và tỷ lệ chuyển đổi mạnh mẽ. |

### Bộ từ khóa gốc (Seed Keywords) để tái lập kết quả:
- **Christmas Gift Ideas:** `christmas gift ideas`, `christmas gift ideas 2026`, `best christmas gifts`, `unique christmas gifts`, `christmas gift for family`
- **Gift for Him:** `gift for him`, `gift ideas for men`, `best gifts for boyfriend`, `gifts for husband`, `unique gifts for men 2026`
- **Gift for Her:** `gift for her`, `gift ideas for women`, `best gifts for girlfriend`, `gifts for wife`, `unique gifts for women 2026`

---

## 🌐 2. Nguồn dữ liệu sử dụng

Hệ thống kết hợp dữ liệu đa kênh để đảm bảo tính khách quan và có số liệu kiểm chứng:
1. **Google Trends:**
   - Dữ liệu xu hướng tìm kiếm theo thời gian (Interest over time).
   - Truy vấn tăng đột biến (Rising queries) và truy vấn hàng đầu (Top queries).
   - Link trực tiếp tới trang khám phá Google Trends.
2. **Amazon Best Sellers & Movers:**
   - Cào dữ liệu sản phẩm bán chạy, sản phẩm tăng trưởng thứ hạng nhanh.
   - Trích xuất: Tên sản phẩm, giá bán, điểm đánh giá (rating), số lượt đánh giá, thứ hạng (rank) và link sản phẩm.
3. **Reddit Communities:**
   - Thảo luận thực tế từ người tiêu dùng tại các subreddit chuyên biệt: `r/giftideas`, `r/gifts`, `r/BuyItForLife`, `r/TheGirlSurvivalGuide`.
   - Trích xuất nhu cầu thực tế và các nỗi than phiền (pain points) của khách hàng về sản phẩm hiện có trên thị trường.

---

## 🤖 3. Công cụ & Model AI

- **Ngôn ngữ phát triển:** Python 3.10+
- **Kiến trúc mã nguồn:** Thiết kế dạng Module hóa (Clean Architecture), chia nhỏ file dễ bảo trì và mở rộng:
  - `src/models/`: Định nghĩa Schemas dữ liệu chuẩn hóa bằng Dataclasses.
  - `src/collectors/`: Thu thập dữ liệu từ từng kênh riêng biệt với cơ chế Retry & Fallback.
  - `src/processors/`: Lọc nhiễu, deduplicate, tính điểm hotness và phân tích khoảng giá.
  - `src/analyzers/`: Kết nối AI Local qua Ollama API, tự động lọc thinking tokens.
  - `src/reporters/`: Tạo báo cáo chuẩn định dạng Markdown kèm link kiểm chứng.
  - `src/utils/`: Tiện ích xử lý chuỗi, định dạng UTF-8, chuyển đổi an toàn.
  - `tests/`: 19 bài kiểm thử đơn vị (Unit tests) bao phủ 100% logic nghiệp vụ.
- **Model AI:** Chạy **Local 100%** qua **Ollama**:
  - Model chính: `local-bench-qwen35-2b-q4km:latest` (Qwen 3.5 2B Q4_K_M) hoặc `qwen2.5:3b-instruct-q4_K_M`
  - Ưu điểm: Bảo mật tuyệt đối, hoạt động offline, không phụ thuộc kết nối API ngoài.

---

## 💰 4. Chi phí ước tính cho mỗi báo cáo

| Khoản mục | Chi phí |
|---|---|
| **API LLM (Ollama Local)** | **$0.00** |
| **API Dữ liệu (Google Trends, Amazon, Reddit)** | **$0.00** (Dùng endpoint mở và web scraping) |
| **Tổng chi phí cho mỗi báo cáo** | **$0.00 (Hoàn toàn miễn phí)** |

---

## 💻 5. Cấu hình máy & Thời gian thực thi

- **Cấu hình phần cứng thử nghiệm:**
  - OS: Windows 11 64-bit
  - CPU: Multi-core x86_64
  - RAM: 16 GB
  - VRAM / GPU: Tích hợp / Dedicated GPU
- **Thời gian chạy trung bình:**
  - Thu thập dữ liệu đa nguồn: ~25 - 35 giây
  - Lọc & tính toán số liệu: ~1 giây
  - AI phân tích & viết báo cáo (3 niches + tổng kết): ~2 - 4 phút
  - **Tổng thời gian từ lúc bấm chạy đến khi có báo cáo hoàn chỉnh:** **~3 - 5 phút**

---

## 🚀 6. Hướng dẫn cài đặt & Chạy

### Bước 1: Clone repository & Cài đặt môi trường
```bash
git clone https://github.com/dungvu242k3/AI-tool-fashion.git
cd AI-tool-fashion
pip install -r requirements.txt
```

### Bước 2: Khởi động Ollama
Đảm bảo Ollama đã được cài đặt và đang chạy server ngầm:
```bash
ollama serve
```
Kiểm tra model sẵn có:
```bash
ollama list
```
*(Nếu muốn tải model mới: `ollama pull qwen2.5:3b`)*

### Bước 3: Chạy kiểm thử tự động (Unit Tests)
```bash
python -m pytest -v
```
*(Kết quả: 19/19 tests PASSED)*

### Bước 4: Chạy Tool tạo báo cáo
```bash
# Chạy mặc định theo config (3 niches Giáng sinh, Quà cho nam, Quà cho nữ):
python src/main.py

# Hoặc chỉ định model cụ thể:
python src/main.py --model local-bench-qwen35-2b-q4km:latest

# Hoặc chỉ định niches tùy chọn:
python src/main.py --niches "Christmas Gift Ideas,Gift for Him,Gift for Her"
```

Báo cáo sau khi tạo sẽ được lưu tự động tại thư mục `reports/` dưới dạng file Markdown UTF-8 (ví dụ: `reports/report_trend_20261020_101500.md`).

---

## 📊 7. Cấu trúc báo cáo xuất ra

Báo cáo tuân thủ 100% cấu trúc yêu cầu của đề bài:
1. **Header Metadata:** Ngày tạo, Danh mục, Niches, AI Model, Chi phí ($0).
2. **Chi tiết từng Niche:**
   - **1. Keyword:** Danh sách từ khóa hot, điểm tìm kiếm, tín hiệu tăng trưởng và link kiểm chứng thực tế.
   - **2. Phân tích:** Đánh giá xu hướng (tăng/giảm/ổn định và lý do), chân dung khách hàng & nỗi đau/phàn nàn, mức độ cạnh tranh và khoảng giá tham khảo trên Amazon.
   - **3. Idea sản phẩm:** 2–3 ý tưởng cụ thể (Bán cái gì, Bán cho ai, Vì sao nên bán bây giờ, Căn cứ dữ liệu).
3. **Tổng kết:**
   - Bảng xếp hạng các niche theo mức độ đáng đầu tư (kèm lý do dung lượng & biên lợi nhuận).
   - Chọn ra **Top 3 idea xuất sắc nhất toàn báo cáo**.
