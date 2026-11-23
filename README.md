# AUTO MUSE AI STUDIO

## Trạng thái mã nguồn

Bản EXE đã phát hành gần nhất: **v1.2.14**. Mã nguồn mới hơn có thêm hệ thống
key bản quyền; phần này chưa triển khai máy chủ và chưa phát hành bản EXE mới.
Đọc [thiết lập bản quyền](docs/licensing.md) trước khi chạy hoặc build: cần cấu
hình URL HTTPS của dịch vụ, nếu chưa cấu hình app sẽ dừng ở màn hình kích hoạt.
Không có chế độ tự bỏ qua bản quyền trong mã nguồn.

Repo không chứa cookie/profile Muse, API key, cấu hình người dùng, dự án phim,
dữ liệu khách, DB bản quyền hoặc file build. Khi build Windows, cần đặt
`ffmpeg.exe` vào `bin` và cài Chromium bằng Playwright.
Bộ cài cho người dùng nằm ở GitHub Releases; quy trình phát hành ở
[hướng dẫn cập nhật](docs/updates.md).

## Phim dài (bản 1.1.0)

Mở **Phim dài** để lập kế hoạch nhiều clip tiếp nối bằng khung hình cuối, duyệt từng clip,
lưu/tiếp tục dự án và xuất phim với nhạc nền/lời thoại. Xem [hướng dẫn phim dài](docs/long-film.md).

Ứng dụng Desktop tự động hóa tạo ảnh và video hàng loạt trên nền tảng **Muse AI** sử dụng **Python + PyQt6** kết hợp **Playwright Async Engine**. Ứng dụng hỗ trợ quản lý đa tài khoản độc lập, luân chuyển tài khoản (Round-robin), phân tích đa ảnh tham chiếu thông minh (Multi-reference alias injection), chặn bắt luồng mạng để tải asset tự động và tích hợp module hậu kỳ (TTS, ghép video FFmpeg, viết lại kịch bản bằng LLM).

---

## 1. CẤU TRÚC THƯ MỤC DỰ ÁN

```
auto-museAI/
├── main.py                       # Điểm khởi chạy chính của ứng dụng PyQt6
├── requirements.txt              # Danh sách thư viện phụ thuộc
├── config/
│   ├── __init__.py
│   ├── settings.py               # Quản lý cấu hình & lưu/đọc project_config.json
│   └── project_config.json       # Tệp lưu trữ Profiles, Aliases, Tasks & Cài đặt
├── core/
│   ├── __init__.py
│   ├── models.py                 # Dataclasses: ProfileItem, AliasItem, TaskItem
│   ├── prompt_parser.py          # Bộ phân tích trích xuất thẻ @alias và mapping ảnh
│   └── selectors.py              # Bộ cấu hình CSS/XPath Selectors cho Muse AI
├── workers/
│   ├── __init__.py
│   ├── automation_worker.py      # Playwright Async Engine ngầm (Round-robin, upload, download media)
│   ├── login_worker.py           # Khởi chạy Chromium có giao diện (headed=True) để đăng nhập thủ công
│   ├── tts_engine.py             # Trình tạo âm thanh giọng đọc (Edge-TTS / ElevenLabs / FPT.AI)
│   ├── video_merger.py           # Trình ghép nối video hoàn chỉnh bằng FFmpeg
│   └── llm_rewriter.py           # Trình viết lại kịch bản thành phân cảnh prompt (Gemini/OpenAI/Claude)
├── ui/
│   ├── __init__.py
│   ├── main_window.py            # Cửa sổ chính tích hợp Ribbon và 2 cột làm việc
│   ├── ribbon.py                 # Thanh công cụ Ribbon trên cùng (5 modules)
│   ├── left_panel.py             # Cột trái: Quản lý tài khoản, Nút Chạy/Dừng, Live Console
│   ├── right_panel.py            # Cột phải: Cấu hình tham số, Alias Manager, Prompt Queue & Preview
│   ├── dialogs/
│   │   ├── __init__.py
│   │   ├── settings_dialog.py    # Cửa sổ Cài đặt hệ thống
│   │   ├── alias_dialog.py       # Cửa sổ Thêm/Sửa tham chiếu ảnh @alias
│   │   ├── llm_dialog.py         # Cửa sổ Viết lại kịch bản bằng AI
│   │   ├── tts_dialog.py         # Cửa sổ Đọc Audio Nội Dung Cảm Xúc
│   │   └── video_merge_dialog.py # Cửa sổ Ghép video FFmpeg
│   └── styles/
│       ├── __init__.py
│       └── theme.py              # Bộ stylesheet giao diện Obsidian Dark & Cyberpunk
├── utils/
│   ├── __init__.py
│   ├── file_utils.py             # Tiện ích file, thư mục, Explorer, kiểm tra FFmpeg
│   └── logger.py                 # Logger thread-safe phát tín hiệu tới Live Console
├── profiles/                     # Thư mục lưu User Data Profiles Chrome (so1, so2,...)
├── output/                       # Thư mục xuất file ảnh/video theo từng tài khoản
└── assets/                       # Thư mục ảnh mẫu tham chiếu
```

---

## 2. HƯỚNG DẪN CÀI ĐẶT MÔI TRƯỜNG

### Bước 1: Kích hoạt Virtual Environment & Cài đặt thư viện
```powershell
# Kích hoạt môi trường ảo đã có trong workspace
.venv\Scripts\Activate.ps1

# Cài đặt các gói phụ thuộc
pip install -r requirements.txt
```

### Bước 2: Cài đặt trình duyệt Playwright Chromium
```powershell
playwright install chromium
```

### Bước 3: Kiểm tra FFmpeg (Dùng cho module ghép video)
Hệ thống đã có sẵn `ffmpeg.exe` trong PATH hệ thống. Bạn có thể kiểm tra nhanh:
```powershell
ffmpeg -version
```

---

## 3. HƯỚNG DẪN VẬN HÀNH CHI TIẾT

### 3.1. Khởi chạy ứng dụng
```powershell
.venv\Scripts\python main.py
```

### 3.2. Đăng nhập tài khoản lần đầu (Session Persistence)
1. Trên bảng **QUẢN LÝ TÀI KHOẢN** ở cột trái, chọn tài khoản (ví dụ: `so1`).
2. Bấm nút **`Mở/Đăng nhập`**: Trình duyệt Chromium có giao diện (`headed=True`) sẽ mở trang `https://muse.ai/login`.
3. Đăng nhập tài khoản Muse AI của bạn bình thường (Google login, Email/Password,...).
4. Sau khi đăng nhập thành công vào màn hình làm việc của Muse AI, đóng cửa sổ trình duyệt hoặc bấm nút **`Đóng`** trên tool. Toàn bộ Cookies, Session và Cache được lưu giữ trọn vẹn trong thư mục `profiles/so1`.
5. Thực hiện tương tự cho tài khoản `so2`, `so3`,...

### 3.3. Thiết lập Tham Chiếu Ảnh (@Alias Manager)
1. Ở bảng **QUẢN LÝ THAM CHIẾU ĐẶT TÊN** (cột phải), bấm **`+ Thêm ảnh...`**.
2. Nhập Tag (ví dụ: `@anh1`), Tên mô tả (ví dụ: `Nhân vật nữ chính`), và chọn file ảnh từ máy tính.
3. Các chip tag `[@anh1]`, `[@anh3]`, `[@anhaohong]` sẽ xuất hiện trên thanh **DANH SÁCH @THAM CHIẾU**. Bạn có thể nhấp chuột vào chip để chèn trực tiếp thẻ vào prompt tại vị trí con trỏ!

### 3.4. Nạp Prompt & Chạy Batch Round-Robin
1. Nhập danh sách prompt vào **KHUNG 1 - PROMPT LIST GỐC** (phân cách mỗi cảnh bằng một dòng trống). Ví dụ:
   ```text
   Cảnh quay cận cảnh @anh1 đang nở nụ cười tươi trong ánh nắng chiều hoàng hôn 4K

   Góc quay sản phẩm @anh3 trên bàn trang điểm, bên cạnh người mẫu mặc @anhaohong cầm sản phẩm
   ```
2. Bấm **`Phân tích & Nạp vào Hàng Đợi ➔`**: Hệ thống sẽ tự động phân tích và trích xuất TẤT CẢ các thẻ `@alias` có trong từng prompt, hiển thị đầy đủ thumbnail ảnh tham chiếu ở cột **THAM CHIẾU**.
3. Tick chọn các tài khoản bạn muốn chạy ở cột **CHẠY** bên trái.
4. Bấm nút **`▶ CHẠY / LUÂN CHUYỂN`** (Màu xanh lá):
   - Trình duyệt sẽ chạy ngầm không giao diện (`headless=True`).
   - Tự động luân chuyển giữa các tài khoản `so1`, `so2`,... theo cơ chế Round-Robin.
   - Khi tài khoản hết quota hoặc timeout, hệ thống tự động đánh dấu và chuyển sang tài khoản tiếp theo.
   - Bắt các response mạng và tải ảnh/video về `output/[Profile]/Prompt_[Index]_[JobID].[ext]`.
   - Cập nhật trạng thái `OK - [Profile]` và hiển thị thumbnail preview trực tiếp trên hàng đợi!

---

## 4. CẤU HÌNH SELECTORS PLAYWRIGHT (KHI MUSE AI THAY ĐỔI GIAO DIỆN)

Các Selector được tập trung tại [selectors.py](core/selectors.py) và có thể điều chỉnh trực tiếp từ hộp thoại **⚙ Cài đặt -> Muse AI Selectors**:

| Tên Selector | Mục đích | Giá trị mặc định |
| :--- | :--- | :--- |
| `composer_textarea` | Ô nhập prompt | `textarea[placeholder*='prompt' i]`, `div[contenteditable='true']` |
| `file_input` | Input upload ảnh tham chiếu | `input[type='file']`, `input[accept*='image']` |
| `submit_button` | Nút bấm gửi render | `button[type='submit']`, `button:has-text('Generate')` |
| `completed_media` | Phần tử media sau khi render | `img[src*='generated']`, `video[src*='blob:']`, `a[download]` |
| `quota_warning` | Nhận diện hết lượt / rate limit | `text='Quota exceeded'`, `text='Out of credits'` |

---

## 5. CÁC MODULE TIỆN ÍCH TRÊN HEADER RIBBON

1. **📝 Viết lại kịch bản (LLM Studio)**:
   - Hỗ trợ kết nối Gemini, OpenAI, Claude hoặc bộ heuristic cục bộ (không cần key).
   - Tự động chia kịch bản dài thành các phân cảnh điện ảnh kèm chèn thẻ tham chiếu `@alias`, sau đó bấm **Đẩy vào Hàng Đợi**.
2. **🎬 Ghép (FFmpeg Engine)**:
   - Chọn các file video clip đã hoàn thành, sắp xếp thứ tự và ghép nối thành một video dài duy nhất.
3. **🎙 Đọc Audio Nội Dung Cảm Xúc (TTS Studio)**:
   - Sử dụng Edge-TTS (giọng Việt Nam truyền cảm `vi-VN-HoaiMyNeural`, `vi-VN-NamMinhNeural`) hoặc ElevenLabs / FPT.AI.
   - Tự do điều chỉnh tốc độ đọc và xuất file `.mp3`.
4. **⚙ Cài đặt**:
   - Tùy chỉnh thư mục lưu mặc định, API keys, Timeout render (mặc định 210 giây), số tab mở song song và proxy.
5. **🎨 Giao diện**:
   - Chuyển đổi linh hoạt giữa giao diện **Obsidian Studio** và **Cyberpunk Dark**.
