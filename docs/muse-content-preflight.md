# Rà nội dung trước khi tạo phim — v1.2.6

Đối chiếu ngày 09/11/2026, đúng dịch vụ tại https://muse.ai. Không dùng chính
sách của các trang cùng tên như museai.fans hoặc musevideo.ai.

## Nguồn và phạm vi

- [Muse](https://muse.ai/) xác nhận đây là agent của Meta. Trang
  [điều khoản](https://muse.ai/terms) yêu cầu đăng nhập khi truy cập công khai.
  Chưa xác minh được danh sách prompt bị cấm dành riêng cho Muse Video.
- [Runway Usage Policy](https://runway.com/safety/usage-policy), cập nhật
  06/03/2026: hạn chế bạo lực trực diện với người/động vật, nội dung tình dục,
  khai thác trẻ em, tự hại, thù ghét, giả mạo và xâm phạm quyền người khác.
  Đây là chính sách Runway, không phải bằng chứng mọi tác vụ Muse dùng Runway.
- [Runway generation errors](https://help.runwayml.com/hc/en-us/articles/32880432736659-Why-am-I-receiving-errors-when-trying-to-generate):
  lỗi có thể do prompt, ảnh/video đầu vào, đầu ra hoặc nhà cung cấp; thông báo
  từ bên thứ ba không luôn nêu nguyên nhân. Prompt mâu thuẫn ảnh, định dạng hoặc
  tỷ lệ không phù hợp cũng có thể gây lỗi. Không lặp tự động yêu cầu đã bị chặn.

Hai phản hồi Muse do người dùng gửi chỉ nói chưa tạo được theo mô tả và đề nghị
cảnh thay thế. Thương tích trực diện là suy luận có căn cứ từ hành động cắn/cào
và phương án né tránh mà Muse đề xuất, không phải mã lỗi kiểm duyệt chính thức.

## Thực hiện trong app

1. Hướng dẫn AI viết nội dung phù hợp ngay từ đầu cho mọi thể loại; dùng dàn
   cảnh hồi hộp, ánh sáng, phản ứng và né tránh thay cho thương tích trực diện.
2. Rà hành động, trạng thái đầu/cuối, quy tắc và mô tả tham chiếu bằng các mẫu
   văn bản cục bộ. Có xử lý phủ định trong cùng mệnh đề. Không cấm riêng từ
   “kinh dị” và không đổi tên từ khóa để giấu nội dung cũ.
3. Storyboard mới có dấu hiệu rủi ro được yêu cầu AI chỉnh một lượt. Xác minh
   lại số clip, ID/tên tham chiếu, cách nối/gán nhân vật và trạng thái nối cảnh.
   Không hợp lệ thì giữ checkpoint cũ và báo rõ; không thử tạo video để kiểm tra.
4. Trước khi chạy dự án đã lưu, UI chỉ đúng clip/mục cần sửa. Worker cũng kiểm
   tra trước khi mở trình duyệt hoặc tạo ảnh chuẩn. Không sửa hay gửi lại các
   clip đã hoàn tất; file và lịch sử cũ được giữ.
5. Muse từ chối/đề nghị phương án khác thì lưu WAITING, hiện thông báo cần xử lý;
   không tự gửi câu trả lời đồng ý, không tự tạo lại video.

## Giới hạn

Kiểm tra cục bộ không phải API kiểm duyệt của Muse: có thể bỏ sót, cảnh báo nhầm,
không kiểm tra pixel ảnh tham chiếu, quyền sử dụng hay toàn bộ ngữ cảnh. Không
cam kết mọi nội dung qua rà sẽ được tạo. Kịch bản cũ không bị âm thầm viết lại;
người dùng sửa các mục được chỉ ra hoặc tạo lại storyboard bằng quy tắc mới.
