# Cập nhật ứng dụng

Người dùng bấm **Cập nhật** trên thanh công cụ. App chỉ kết nối nguồn phát hành
khi người dùng bấm nút, không gửi API key hoặc dữ liệu tài khoản Muse.
Nếu có phiên bản mới, app tải bộ cài qua HTTPS, kiểm tra kích thước và SHA-256,
lưu cấu hình, đóng app, cài đè đúng thư mục và mở lại. Tác vụ tạo phim, tạo
kịch bản, hàng đợi hoặc đăng nhập đang chạy phải kết thúc trước khi cập nhật.

Các bản đến v1.1.1 chưa có nút này. Người dùng cũ cần tải/cài đè bản hỗ trợ
cập nhật một lần. Không cần gỡ app; bộ cài không thay cấu hình, profile hay phim.

## Chuẩn bị nguồn GitHub Releases

Repo phát hành phải công khai để người dùng tải không cần token. Repo có thể chỉ
chứa các bản phát hành; không cần đưa mã nguồn hoặc dữ liệu cá nhân lên repo.

Đặt `UPDATE_MANIFEST_URL` trong `core/update_source.py` thành:

`https://github.com/OWNER/REPO/releases/latest/download/latest.json`

Nguồn này được tích hợp trong EXE. Cấu hình cũ không có URL vẫn dùng nguồn mặc
định của nhà phát hành. URL riêng trong Cài đặt chỉ dùng để ghi đè khi cần.

## Mỗi lần phát hành

Build Windows dùng PATH cô lập (Python + Windows) và kiểm tra bundle để chặn
`ucrtbase.dll` lấy nhầm từ môi trường công cụ. Trước khi phát hành, phải mở EXE
thật, xác nhận cửa sổ chính và màn hình Phim dài hoạt động; chỉ đọc nội dung
archive hoặc chạy test bằng Python chưa đủ phát hiện lỗi DLL lúc khởi động.

Nguồn đang dùng: `quangtuan14102001/auto-museAI` (GitHub Releases công khai).
Sau khi tạo bộ cài và metadata, chạy `python tools/publish_update.py` trên máy
phát hành đã đăng nhập GitHub. Công cụ tải đủ hai file lên bản nháp rồi mới
công bố; không ghi token vào ứng dụng và không ghi đè bản ổn định đã phát hành.

1. Tăng phiên bản trong `core/version.py` và `installer.iss`.
2. Chạy `tools/build_windows.ps1`, rồi biên dịch `installer.iss` bằng Inno Setup.
   Bộ cài lấy trực tiếp EXE mới từ `dist/fixed`, tránh lấy nhầm EXE cũ đang mở.
3. Chạy `.venv/Scripts/python.exe tools/prepare_update.py --repo OWNER/REPO`.
4. Tạo release nháp với tag `vX.Y.Z`. Đính kèm
   `dist/AutoMuseAI_Setup_vX.Y.Z.exe` và `dist/update/latest.json`.
5. Kiểm tra đủ hai file rồi công bố bản ổn định. App dùng endpoint latest của
   GitHub, không theo bản nháp hoặc prerelease.

Metadata gồm `version`, `installer_url`, `size`, `sha256`. Không sửa bộ cài sau
khi tạo metadata. Nếu cần sửa bộ cài, tạo lại metadata và phát hành phiên bản mới.

Nếu nguồn chưa cấu hình hoặc tải/kiểm tra thất bại, app thông báo và tiếp tục
giữ bản hiện tại. Không có bộ cài nào được chạy khi kiểm tra file không đạt.
