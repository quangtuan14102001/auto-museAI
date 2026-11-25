# Hướng dẫn sản xuất tích hợp trong AutoMuseAI

App sử dụng các adapter tiếng Việt đã rà soát, theo từng giai đoạn, trong
`assets/film_skills/runtime.json`. Đây là dữ liệu đầu vào cho mô hình, không phải
chạy một agent CLI bên ngoài. Bộ hướng dẫn thể loại vẫn áp dụng song song.

## Nguồn và giấy phép

Các bản chốt và SHA-256 tài liệu nằm ở `assets/film_skills/sources.json`.
Thư mục `upstream` lưu 8 SKILL.md nguyên bản và giấy phép để đối chiếu:

- `svenkatreddy/universal-video-skills` (MIT): video-prompt-craft,
  cinematic-direction, character-consistency, story-and-shots.
- `zenstory-ai/drama-skills` (MIT): short-drama-write, short-drama-storyboard.
- `sb-dev/video-production-skills` (Apache-2.0): video-evaluate.
- `g0dam/video-studio-skills` (MIT): video-asset-bible.

Các adapter là phần tích hợp do AutoMuseAI viết lại cho schema JSON và giao diện
hiện có, dựa trên phương pháp của các nguồn trên. Không sửa tài liệu upstream.
Giữ đầy đủ LICENSE khi phân phối, không suy ra rằng các tác giả bảo chứng app.
Không tải hoặc chạy script upstream, cài Node/Replicate hay gọi API ngoài luồng
Muse/Gemini hiện có. Các liên kết tham chiếu trong bản lưu chỉ dùng tra cứu;
thư mục upstream không phải gói độc lập để cài vào agent.

## Cách áp dụng

1. Muse hoặc AI API viết storyboard đều nhận hướng dẫn biên kịch/đạo diễn:
   tiến triển có nguyên nhân, một hành động/máy chính mỗi clip, ID cố định,
   mô tả nhận dạng không đổi, bàn giao trạng thái và tự rà soát trước khi trả JSON.
2. Tạo ảnh chuẩn nhận hướng dẫn riêng: rõ nhận dạng/bố cục, không collage,
   không biến tư thế/ánh sáng nhất thời thành thuộc tính cố định.
3. Prompt video từng clip nhận chỉ dẫn cỡ cảnh, hành động trong thời lượng,
   vai trò từng ảnh, ưu tiên khung cuối trước cho clip tiếp nối; không kể lại
   cả cốt truyện hoặc mở/kết lại ở từng clip.
4. Nếu người dùng bật **Gemini đối chiếu**, một lượt kiểm tra dùng ảnh chuẩn,
   5 khung mẫu của clip và khung bàn giao trước (khi tiếp nối). Báo cáo lưu
   bằng chứng có hash, phiên bản hướng dẫn và đề xuất sửa reference/shot_plan/
   generation/capability/manual. Không tự retry tốn lượt. Lỗi API hoặc phát hiện
   vấn đề thì giữ REVIEW; phải có kết quả pass mới tự duyệt khi chế độ duyệt tay tắt.

Đối chiếu dùng API key Gemini riêng và có chi phí theo dịch vụ; mặc định vẫn
tắt. Một lượt có nhiều ảnh hơn trước. Kiểm tra vài khung không chứng minh được
chuyển động mượt, đồng bộ âm thanh hay chất lượng toàn bộ phim. Không hứa giữ
nhân vật chính xác 100%, không khắc phục được giới hạn khu vực hoặc năng lực model.

Dự án cũ vẫn mở được: trường production_skills mới có giá trị mặc định rỗng.
Nguồn/phiên bản tích hợp được ghi vào dự án khi có yêu cầu gửi mới; các prompt
đang chờ kết quả vẫn dùng checkpoint cũ, không gửi lại vì thay hướng dẫn.
Đổi nguồn hoặc adapter phải rà soát lại rồi kiểm thử và build app; không tự
cập nhật từ nhánh main của các repo bên ngoài lúc chạy app.
