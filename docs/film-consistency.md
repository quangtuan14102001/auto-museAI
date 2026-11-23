# Giữ nhất quán nhân vật và bối cảnh — v1.2.0

## Bổ sung v1.2.4: thử lại sau khi khôi phục phiên Muse

Ảnh chuẩn thất bại/gián đoạn trước khi có bản ghi gửi prompt có thể thử lại bằng
phiên hiện tại. App không phát lại lỗi disconnected cũ mà chưa truy cập trang.
Nếu đã ghi nhận gửi prompt hoặc đã có ảnh, app vẫn giữ cơ chế tránh tạo trùng và
không tự gửi lại ảnh chuẩn. Việc đăng nhập ở Chrome riêng không tự chia sẻ phiên
với thư mục profile do app quản lý; trạng thái dịch vụ phải kiểm tra trên đúng phiên.

## Bổ sung v1.2.3: phản hồi JSON bị lỗi

Gemini được yêu cầu trả JSON theo schema storyboard. Bộ đọc có thể xử lý dấu
phẩy thừa ngoài chuỗi văn bản, đồng thời giữ nguyên nội dung lời thoại. Nếu phản
hồi bị cắt hoặc hỏng ở một clip, app chỉ giữ tiền tố gồm các clip hoàn chỉnh cùng
định nghĩa nhân vật/bối cảnh đọc được; không bịa thêm trường hay bỏ qua một clip
hỏng ở giữa để nối các clip phía sau. Phần còn thiếu đi qua cơ chế bổ sung v1.2.1.

Nếu không lấy được phần hợp lệ, app yêu cầu AI sửa cú pháp tối đa một lần cho mỗi
lượt gọi. Lỗi mạng/quota không bị lặp lại theo cơ chế sửa JSON. Phản hồi hỏng có
thể lưu cạnh checkpoint với đuôi `.invalid.txt` để chẩn đoán tại máy; không nằm
trong bộ cài. Các bản nháp đã lưu không bị xóa khi sửa thất bại. Không dùng eval
hay thực thi nội dung do AI trả về.

## Bổ sung v1.2.2: chọn thể loại phim

Tab Kịch bản có mục Thể loại phim: chọn từ danh sách hoặc nhập thể loại riêng.
Tự động (theo ý tưởng) giữ hành vi cũ. Thể loại được gửi vào yêu cầu viết kịch bản,
yêu cầu viết tiếp clip thiếu và prompt tạo clip, đồng thời lưu cùng dự án.
Bản nháp của các thể loại khác nhau được tách riêng; không nối nhầm 48 clip của
một thể loại vào phim có thể loại khác. Nếu đổi thể loại sau khi lập storyboard,
cần tạo lại kịch bản trước khi lưu. Thể loại không thay thế ảnh chuẩn hay mô tả
nhân vật. Phong cách hình ảnh như hoạt hình 3D có thể khai báo riêng ở phần quy tắc.

## Bổ sung v1.2.1: storyboard trả thiếu clip

Nếu AI trả một storyboard hợp lệ nhưng chưa đủ clip (ví dụ 48/60), app giữ nguyên
phần đã có, lưu bản nháp trong `output/film_drafts` (theo thư mục output đã cấu hình)
và yêu cầu bổ sung phần còn thiếu. Mỗi phần bổ sung phải qua kiểm tra ID, hành động
trùng, trạng thái nối và số clip trước khi được ghép vào bản nháp. Mô tả tham chiếu
đã có không bị phần bổ sung ghi đè. Không nhân bản clip hoặc âm thầm cắt clip dư.

Mỗi lần bấm tạo/viết tiếp có tối đa ba lượt bổ sung. Lỗi kết nối/quota dừng ngay,
không tự gọi lại liên tục. Nếu vẫn thiếu, nút đổi thành Viết tiếp và phần hợp lệ
được giữ. Khi mở lại app, nhập cùng ý tưởng/thời lượng/quy tắc để tiếp tục từ bản
nháp đã lưu. Bản nháp chỉ được tạo từ phiên bản này; không khôi phục được phản hồi
AI mà bản cũ đã bỏ sau khi báo lỗi.

App cũng nhận diện riêng trang Muse is disconnected, dừng trước khi gửi và báo
đúng yêu cầu hỗ trợ của Muse. Đóng trình duyệt không còn luôn báo đăng nhập thành công.

## Cơ sở thiết kế

- Runway tách ảnh References khỏi bước tạo video; hỗ trợ lưu tham chiếu có tên
  và khuyến nghị ảnh nhân vật rõ, ánh sáng đều. Không áp giới hạn số ảnh của
  Runway sang Muse vì hai công cụ khác nhau.
  https://help.runwayml.com/hc/en-us/articles/40042718905875-Creating-with-Gen-4-Image-References
- Google Flow phân biệt ingredients/nhân vật với start/end frames; prompt mô tả
  hành động giữa các khung. Đây là cơ sở tách nhận dạng khỏi trạng thái nối cảnh.
  https://support.google.com/flow/answer/16353334?hl=en
- Luma đề xuất một bộ Master Reference Assets làm nguồn chuẩn được dùng lại
  trong các lần tạo. App lưu các ảnh này vào tài sản của từng dự án.
  https://lumalabs.ai/learning-hub/using-master-reference-assets-in-luma-step-by-step-workflow

## Đã triển khai

1. Gemini trả storyboard có cấu trúc: danh sách nhân vật, địa điểm và hành động
   riêng cho từng clip. Mỗi clip có ID tham chiếu, cảnh lớn, cách nối, trạng thái
   đầu/cuối. Không tự lặp nguyên prompt cho đủ thời lượng trong luồng AI.
2. Tab Nhân vật & bối cảnh cho chọn ảnh chuẩn, sửa mô tả, xem ảnh và chủ động
   đặt lại ảnh. Nếu ảnh còn thiếu, Muse tạo một ảnh chuẩn trước khi tạo video.
   Chỉ ảnh của đối tượng thật sự được gán cho clip mới được sử dụng.
3. Ảnh chuẩn có bản sao trong dự án và SHA-256. App chặn file bị sửa bên ngoài.
   Việc sửa tham chiếu đặt lại những clip có sử dụng và các clip nối phụ thuộc;
   các file kết quả cũ vẫn tồn tại.
4. Tách vai trò ảnh: khung bắt đầu, nhân vật, bối cảnh, phong cách. App bổ sung
   tên/vai trò và số thứ tự đúng với ảnh upload trong từng bước. Sửa lỗi pipeline
   trước đây làm mất ảnh chuẩn khi chuyển từ tạo ảnh sang tạo video.
5. Clip tiếp nối phải giữ cùng cảnh/địa điểm và trạng thái đầu khớp nguyên văn
   trạng thái kết thúc trước. Chuyển địa điểm phải dùng cảnh mới. Đây là kiểm tra
   metadata, không chứng minh video thực tế làm đúng.
6. Lưu ảnh đã gửi, prompt và bản ghi tham chiếu theo từng lần tạo. Ảnh chuẩn đang
   dở không được tự gửi lại sau khi mở app; có thể nhập ảnh đã tạo hoặc chủ động
   đặt lại sau khi kiểm tra Muse.
7. Nút Đối chiếu ảnh chuẩn hiển thị ảnh chuẩn, các ảnh đã gửi, khung đầu/cuối và
   trạng thái dự kiến. Có tùy chọn dùng Gemini đối chiếu hai khung hình. Có lỗi,
   có vấn đề hoặc kết quả không rõ thì clip chờ người dùng duyệt. API này dùng
   key Gemini và có thể phát sinh chi phí; mặc định không tự bật.
8. Dự án v1 vẫn đọc được. Lần lưu sang v2 giữ một bản `.v1.backup.json` cạnh
   manifest. Dự án v2 không mở bằng các bản app cũ chỉ hỗ trợ v1.

## Quy trình sử dụng

Nhập ý tưởng → Gemini lập storyboard → xem Nhân vật & bối cảnh, chọn ảnh nếu có
→ lưu dự án → chọn đối chiếu Gemini nếu cần → Tiếp tục làm phim.
Ở một clip có thể sửa nhân vật, địa điểm, trạng thái đầu/cuối và cách nối.
Nếu đổi kết thúc clip, trạng thái đầu của clip nối trực tiếp được cập nhật và
chuỗi phụ thuộc phải tạo/duyệt lại. Các cảnh độc lập không bị đặt lại.

## Giới hạn thực tế

- v1.2.8: trạng thái đầu của clip AI đánh dấu tiếp nối được lấy từ trạng thái
  kết thúc clip trước, cùng địa điểm/nhóm cảnh, trước khi lưu và kiểm tra.
  Một điểm nối có một nguồn dữ liệu, không bắt AI diễn đạt cùng trạng thái hai
  lần rồi so sánh hai câu. Không thay hành động/trạng thái kết thúc hay cảnh
  mới; không viết lại prefix đã checkpoint. Dự án chỉnh tay/runtime vẫn kiểm
  tra trạng thái nghiêm ngặt. Đây là chuẩn hóa kế hoạch, không chứng minh
  chuyển động của video do model tạo chắc chắn liên tục.

- v1.2.7: chuẩn hóa metadata nối cảnh trong kết quả AI trước khi kiểm tra/lưu:
  đổi địa điểm thì bắt đầu cảnh mới; clip tiếp nối cùng địa điểm kế thừa nhóm
  cảnh trước. Không thay hành động hay trạng thái để che sai liên tục; bản
  checkpoint đã giữ không bị viết lại khi bổ sung clip. Kiểm tra runtime và
  kiểm tra ID/tham chiếu/trạng thái vẫn được giữ nguyên.

- v1.2.5: phản hồi Muse không tạo được và đề nghị phương án khác được lưu WAITING,
  hiện hộp thông báo chọn đúng clip; không tự gửi lại tác vụ. Storyboard mới được
  hướng dẫn dùng hồi hộp/né tránh thay cho thương tích trực diện ở cả hành động
  và trạng thái nối cảnh. Không cam kết Muse chấp nhận mọi prompt; kịch bản cũ
  không bị tự sửa và cần người dùng chỉnh hoặc tạo lại trước khi gửi tiếp.

- Muse hiện được điều khiển bằng trang web và ảnh đính kèm; chưa xác minh có
  tham số keyframe/character-lock chính thức. Mô tả vai trò trong prompt không
  tương đương một khả năng điều khiển cứng của model.
- Không bảo đảm nhận dạng hay địa điểm chính xác tuyệt đối. Không sửa các frame
  do model tạo sai bằng cách đổi trạng thái thành thành công.
- Đối chiếu Gemini chỉ xét khung đầu/cuối, không kiểm tra toàn bộ chuyển động,
  giọng nói hoặc mọi frame giữa clip. Nhận xét AI có thể sai; vẫn có nút xem và
  duyệt thủ công. Kết quả lưu rõ phạm vi đánh giá và hash ảnh đã đánh giá.
- Thay đổi prompt/ảnh chuẩn có thể cần tạo lại một chuỗi clip tiếp nối; app không
  thể giữ nguyên các clip phụ thuộc mà vẫn cam kết nối liền mạch.
- Các mẫu cũ không có hồ sơ nhân vật sẽ không được tự bịa thêm dữ liệu; có thể
  tiếp tục dùng ảnh chung hoặc gán tham chiếu thủ công.

## Xác minh

Kiểm thử metadata, round-trip/migration, chỉ chọn đúng ảnh theo clip, phát hiện
ảnh bị thay đổi, truyền tham chiếu qua cả hai bước, không gửi trùng ảnh chuẩn,
khóa chờ duyệt khi đối chiếu báo lỗi. Có lượt gọi Gemini thật tạo storyboard
4 clip và lượt đối chiếu thật dùng các khung từ clip báo tuyết đã có; đây không
phải kiểm chứng một phim 10 phút mới đã được Muse tạo hoàn chỉnh.
