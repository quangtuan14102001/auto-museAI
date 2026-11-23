# Làm phim dài trong AutoMuseAI 1.1.0

Mở **Phim dài** trên thanh công cụ. Chức năng này lưu dự án riêng, không sửa hàng đợi ảnh/video hiện có.

## 1. Lập kế hoạch

- Chọn thời lượng phim, clip 5 hoặc 10 giây, tỷ lệ khung hình và một tài khoản đã đăng nhập.
- Nhập quy tắc xuyên suốt: nhân vật, trang phục, ánh sáng, hướng đi và phong cách.
- Có thể chọn ảnh mở đầu phim và các ảnh khóa nhận dạng. App sao chép ảnh vào dự án để không phụ thuộc file gốc.
- Mỗi đoạn văn cách nhau một dòng trống là một **cảnh lớn**. App chia đều số clip vào các cảnh lớn. Ví dụ 10 phút, clip 10 giây, 12 đoạn kịch bản → 60 clip, mỗi cảnh lớn gồm 5 clip.
- Trong một cảnh lớn, clip sau dùng khung hình cuối của clip trước làm ảnh tham chiếu đầu tiên. Sang cảnh lớn mới, app tạo ảnh mở đầu mới theo nội dung và các ảnh khóa nhận dạng.
- Nếu chọn 60 đoạn kịch bản cho 60 clip thì mỗi clip là một cảnh mới, không phải một chuỗi 60 clip cùng cú máy.
- Quy tắc chung và thời lượng được khóa sau khi lập kế hoạch; có thể sửa hành động của từng clip trong bước duyệt.

## 2. Tạo và duyệt

Mặc định app chỉ tạo một clip rồi dừng. Bấm **Mở clip**, đối chiếu **khung cuối clip trước / khung đầu clip đang chọn**, sau đó **Duyệt & tiếp tục**.

Clip phụ thuộc phải chạy tuần tự. Các clip đã chấp nhận được tái sử dụng khi mở lại dự án.

Có thể bỏ chọn “Dừng để tôi duyệt” để tự chấp nhận file đã được kiểm tra và chạy tiếp. Đây không phải đánh giá chất lượng hình ảnh tự động; vẫn cần xem lại nhân vật, chuyển động và các mối nối trước khi xuất.

**Tạo lại clip** hoặc sửa prompt sẽ đặt lại clip đó và các clip tiếp nối phụ thuộc, dừng ở cảnh lớn mới kế tiếp. File/take cũ vẫn được giữ trong thư mục dự án.

Nếu app dừng sau khi đã gửi yêu cầu, clip chuyển sang “Cần kiểm tra tác vụ cũ”. App không tự gửi lại. Kiểm tra Muse, rồi dùng **Nhập clip có sẵn**, hoặc chủ động chọn **Tạo lại clip**. Clip đã tải nhưng chưa xử lý xong có thể tiếp tục xử lý cục bộ.

## 3. Xuất phim

- Mỗi clip được chuẩn hóa H.264, 24 FPS, cùng kích thước và âm thanh AAC stereo 48 kHz. File không có tiếng được bổ sung luồng âm thanh im lặng tương thích.
- Khung hình nối được trích **sau khi cắt đúng độ dài dùng trong phim**, tránh dùng nhầm cuối file gốc dài hơn.
- Clip quá ngắn bị từ chối. App không lặp hình, kéo chậm hoặc đứng hình để bù thời lượng.
- Có thể thêm nhạc nền xuyên suốt (lặp vừa đủ phim, mức nền 15%), lời thoại riêng (không lặp), và giữ/tắt tiếng từ các clip.
- Chỉ xuất khi mọi clip đã được chấp nhận. App kiểm tra toàn bộ luồng hình và thời lượng trước khi công bố file cuối. Mỗi lần xuất tạo file mới trong `exports`, giữ lại các bản trước.
- Mở lại bằng file `project.film.json`. Nên di chuyển/sao lưu cả thư mục dự án, không chỉ file JSON.

## Cơ sở và giới hạn

Hướng dẫn chính thức của Runway mô tả cách tạo chuỗi dài bằng khung hình cuối của lần tạo trước, cùng việc xem và chỉnh điểm nối:

- [Image to Video Prompting Guide](https://help.runwayml.com/hc/en-us/articles/48324313115155-Image-to-Video-Prompting-Guide)
- [Utility Nodes: First Frame, Last Frame, Stitch, Trim](https://help.runwayml.com/hc/en-us/articles/47184761711379-Using-Utility-Nodes-in-Workflows)

App truyền yêu cầu và ảnh qua giao diện Muse hiện có; không điều khiển trực tiếp tham số khung hình đầu của mô hình phía sau Muse. Cơ chế này hỗ trợ giữ liên tục, không bảo đảm nhân vật và chuyển động luôn đúng. Bước duyệt giúp phát hiện sai lệch trước khi lỗi truyền sang clip sau.

Kiểm thử có ghép file thực tế dài 600 giây bằng các clip mẫu, chạy chuỗi tuần tự, kiểm tra đầu vào khung hình, duyệt/tiếp tục, phục hồi gián đoạn và trộn âm thanh. Điều này kiểm chứng cơ chế phần mềm, không chứng minh một bộ phim AI 10 phút đã giữ hoàn hảo nhân vật. Dự án demo đi kèm dùng video người dùng đã có, không gửi thêm yêu cầu tạo video.
