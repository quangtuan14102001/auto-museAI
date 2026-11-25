# Viết kịch bản bằng Muse — v1.2.9

## Xác minh và sửa profile v1.2.10

Ngày 13/11/2026 đã thử thật tài khoản mới trong `dist/profiles/so1`: Muse trả đủ
18 clip/180 giây, 14 clip tiếp nối, 5 tham chiếu; lưu qua giao diện và mở lại
thành công, không yêu cầu tạo media. Lượt thử ban đầu đã mở nhầm profile cũ ở
thư mục gốc vì cấu hình dùng đường dẫn tương đối.

v1.2.10 neo đường dẫn tương đối theo thư mục dữ liệu của file cấu hình, ưu tiên
profile cạnh app. Profile legacy ở thư mục gốc chỉ dùng nếu app chưa có profile
tương ứng. Profile mới lưu đường dẫn tuyệt đối ngay từ lúc tạo; đường dẫn tuyệt
đối có sẵn được giữ. Không chép/xóa/ghép cookie giữa các thư mục tài khoản.

Lượt chạy lại bằng v1.2.10 từ thư mục gốc sau khi sửa cũng PASS: 18 clip,
180 giây, 15 clip tiếp nối, 5 tham chiếu, lưu/mở lại qua giao diện. Báo cáo tại
`build/live-film-idea-20261113T063605Z/muse/result.json`.

Trong Phim dài → Kịch bản & tham chiếu, chọn **AI viết kịch bản: Muse**,
chọn tài khoản, nhập ý tưởng/thể loại/thời lượng và bấm tạo kịch bản.
Không cần API key Gemini. Từ v1.2.16, phần này chỉ có hai nguồn rõ ràng: **Muse**
và **Gemini**. Chọn Gemini thì nhập key ngay bên dưới, bấm **Lưu key** hoặc
**Kiểm tra key**, rồi tạo kịch bản. Gemini luôn dùng key Gemini, không phụ thuộc
nhà cung cấp chung trong Cài đặt. OpenAI/Claude vẫn có ở công cụ Kịch bản chung.

Key được dùng chung với Cài đặt → LLM AI API, lưu trong cấu hình cục bộ (không
đưa vào Git/bộ cài). Nút kiểm tra gửi một yêu cầu tạo văn bản ngắn, có dùng quota
API; chỉ gọi models.list thành công chưa đủ để báo key tạo kịch bản được.
Lưu key không tự gọi API. Key được chuẩn hóa khoảng trắng ngoài và dấu nháy bọc;
app báo lỗi ghi cấu hình thay vì báo thành công khi chưa lưu xuống đĩa.
Lỗi 429/503 được phân biệt với key sai/quyền truy cập; không chuyển sang bộ
phân tách cục bộ rồi báo rằng Gemini đã viết thành công.

Muse nhận yêu cầu chỉ viết JSON bằng văn bản, không tạo ảnh/video. Kết quả
được kiểm tra cùng luồng storyboard hiện có: số clip, ID nhân vật/địa điểm,
liên kết trạng thái và rà mô tả nhạy cảm. Phần thiếu được viết bổ sung có giới
hạn; bản nháp và yêu cầu chưa lấy được câu trả lời được lưu riêng theo profile.

Nút Dừng ngừng theo dõi, không tự hủy tác vụ từ xa. Khi bấm tạo kịch bản lại,
app theo dõi yêu cầu đang dở trong cùng cuộc chat thay vì gửi trùng. Không
đọc câu trả lời từ đoạn chat cũ và không dùng media làm đầu ra của bước viết.
Các file `.muse-request.json` nằm cạnh checkpoint trong `output/film_drafts`,
chứa prompt/câu trả lời/URL cuộc chat, không chứa cookie hoặc API key.

Browser sử dụng profile đã chọn; không chạy đồng thời với đăng nhập hoặc tạo
media của cùng tài khoản. Từ v1.2.14, cả viết kịch bản Muse và tạo phim đều chạy
headless như tác vụ Text → Image/Video, không mở cửa sổ web. Nếu phiên hết hạn,
app báo lỗi trước khi gửi; người dùng chủ động bấm Mở/Đăng nhập, hoàn tất đăng
nhập, đóng cửa sổ rồi thử lại. Trang Muse báo disconnected thì chưa gửi yêu cầu; app không tự gửi
ticket hỗ trợ, không xóa cookie và không tự đăng nhập bằng tài khoản khác.

Kiểm thử: fixture Chromium cho câu trả lời hiện tại, không gửi trùng sau khởi
động lại, timeout giữ journal, giao diện dùng Muse khi không có Gemini key.
Lượt thử profile so1 ngày 10/11/2026 bị chặn trước khi gửi: trang thực tế hiển
thị “Muse is disconnected / Submit a ticket”. Chưa xác minh tạo hoàn chỉnh
storyboard thật trên tài khoản này; không tuyên bố luồng live đã thành công.
