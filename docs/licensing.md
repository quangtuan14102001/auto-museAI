# Bản quyền AutoMuseAI

Hệ thống gồm EXE khách hàng và dịch vụ quản trị riêng. Chưa cấu hình URL dịch vụ
thì bản mới khóa tại màn hình kích hoạt; không tự cấp key hoặc mở miễn phí.
Các EXE v1.2.14 trở về trước đã phát hành không có cơ chế key, không thể khóa
từ xa bằng tính năng mới. Không công bố bản thương mại trước khi dịch vụ sẵn sàng.

## Máy chủ

Linux VPS + domain HTTPS. Cài Python và `license_server/requirements.txt`.
Hoặc dùng Docker: `docker compose -f license_server/compose.yaml up -d --build`
với `LICENSE_ADMIN_TOKEN` đã đặt trong môi trường shell. Compose chỉ đưa cổng ra
loopback và giữ DB trong volume `license-data`; không dùng `down -v` khi nâng cấp.
Khi chạy Docker, cấu hình bộ giới hạn theo IP ở reverse proxy (dịch vụ mặc định
coi proxy là một IP); không bật tin cậy header cho nguồn mạng không kiểm soát.
Đặt `LICENSE_DB=/var/lib/automuse/licenses.sqlite3` trên ổ đĩa bền vững, chỉ
tài khoản dịch vụ được đọc; sao lưu DB thường xuyên. Không lưu DB vào GitHub.
Đặt `LICENSE_ADMIN_TOKEN` là chuỗi ngẫu nhiên ít nhất 32 ký tự trong secret/env
của máy chủ, không đưa vào EXE, Git, URL hoặc log.

Chạy từ thư mục dự án:

```
gunicorn 'license_server.app:production_app()' --workers 1 --threads 4 --bind 127.0.0.1:8088
```

Đặt reverse proxy HTTPS phía trước, chuyển `/` đến dịch vụ này. Giữ nguyên
Authorization header; không log request body/header Authorization. Với bộ giới
hạn tích hợp, một địa chỉ proxy tối đa 60 request/phút; cấu hình giới hạn theo IP
tại reverse proxy nếu có nhiều khách sau proxy. Đặt `LICENSE_TRUST_PROXY=1` và
cấu hình proxy ghi đè `X-Real-IP` bằng IP kết nối thực (`$remote_addr` trên nginx)
để bộ giới hạn phân biệt từng khách; chỉ tin header này khi kết nối từ loopback.
Không tin X-Forwarded-For trực tiếp.
Không mở cổng 8088 ra Internet. Truy cập `/admin` qua HTTPS để tạo key, xem danh
sách, gia hạn, khóa/mở khóa, đặt lại máy. Mật khẩu quản trị chỉ nằm trong ô nhập
của tab hiện tại, không lưu localStorage. Key khách chỉ hiện một lần khi tạo;
DB chỉ lưu SHA-256 của key ngẫu nhiên 256 bit. Ghi lại key khi gửi cho khách.

Hạn 30/365 ngày tính từ lúc tạo key; vĩnh viễn không có ngày hết hạn. Gia hạn
cộng từ thời điểm hiện tại nếu đã hết hạn, từ hạn cũ nếu vẫn còn hạn. Khóa key
có hiệu lực với app đang mở ở lần kiểm tra tiếp theo (thường tối đa 60 giây;
lease tối đa 300 giây). Thu hồi key cũ và cấp key mới nếu cần chặn máy cũ hoàn
toàn; chỉ đặt lại máy không ngăn máy cũ dùng key để đăng ký lại.

## Ứng dụng

Gắn domain vào `core/license_source.py` rồi build EXE và bộ cài mới. Chỉ URL
công khai được đóng gói; không có secret quản trị trong bản khách.
App kiểm tra online trước khi mở, định kỳ mỗi 60 giây khi chạy. Không hỗ trợ
offline: lỗi mạng/khóa/hết hạn thì dừng worker an toàn, khóa UI và yêu cầu kiểm
tra lại. Key lưu riêng bằng Windows DPAPI theo tài khoản Windows; không ghi vào
project phim, cấu hình/API key hoặc log. Mã máy là SHA-256 của Windows MachineGuid,
không gửi MachineGuid gốc. Không thu cookie Muse hay prompt lên máy chủ bản quyền.

Khách nhập key một lần, những lần sau app kiểm tra key đã lưu. Cập nhật giữ key
và profile. Giới hạn máy được nhận/chốt trong transaction SQLite để chống hai
máy đồng thời giành cùng một chỗ. Người quản trị nên bảo vệ `/admin` bằng HTTPS
và giới hạn truy cập tại reverse proxy. Giữ domain/API ổn định qua các lần build.

Không có DRM phía máy khách nào chống được mọi sửa đổi EXE. Bản cũ không có
key vẫn chạy; cần quản lý việc phân phối các bản đó khi chuyển sang bán thương mại.
