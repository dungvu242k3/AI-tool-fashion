# Kiểm chứng giai đoạn 5 — Reddit

Đây là diagnostics của request mạng thật, không phải báo cáo xu hướng hay fixture kiểm thử.

- Thời điểm UTC: 21/10/2026 04:04:19–04:04:27.
- Phạm vi: một subreddit và seed có sẵn trong config: r/giftideas × christmas gift ideas; một trang, tối đa 5 post. Không chạy lại Trends/Amazon hoặc toàn pipeline.
- Adapter: public_json; môi trường chưa có REDDIT_CLIENT_ID/REDDIT_CLIENT_SECRET. Không giả credential, không dùng dữ liệu unit test.
- Kết quả: failed, 0 post. Hai HTTP attempt đều lỗi connection_error, chưa nhận được HTTP status/JSON. Không đủ căn cứ kết luận Reddit trả 403 hay tài khoản không được cấp quyền.
- Không chuyển host, proxy hoặc tạo bài thay thế. Chưa có permalink để mở; chưa xác minh score/comment hoặc OAuth trên mạng thật.
- Nhật ký: [9f35f55a6a3445f993abbd279e797a47.json](diagnostics/9f35f55a6a3445f993abbd279e797a47.json).

Unit/contract tests riêng đã pass: 145 test Python mới + 3 test Reddit bị ảnh hưởng và 2 test UI mới. Các response giả lập chỉ tồn tại trong tests/, HTTP ngoài bị chặn khi chạy unit tests; không được đưa các fixture vào thư mục này.

Để hoàn tất acceptance live cần quyền truy cập/credential hợp lệ và kết nối tới Reddit. Khi nguồn chưa truy cập được, pipeline chỉ được xuất failed/partial với dữ liệu thật của nguồn khác, không trình bày nguồn Reddit như đã thành công.
