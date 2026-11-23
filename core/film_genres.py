DEFAULT_GENRE = "Tự động (theo ý tưởng)"
FILM_GENRES = [DEFAULT_GENRE, "Phiêu lưu", "Hành động", "Hài", "Tình cảm", "Tâm lý",
               "Kinh dị", "Trinh thám", "Khoa học viễn tưởng", "Kỳ ảo", "Gia đình", "Tài liệu"]

FILM_CONTENT_GUIDANCE = (
    "Dàn cảnh không mô tả thương tích trực diện: không máu me, vết rách sâu, cắn/cào gây thương tích "
    "hoặc cận cảnh đau đớn. Với kinh dị/hành động, tạo căng thẳng bằng ánh sáng, âm thanh, "
    "rượt đuổi, né tránh, bóng đổ và phản ứng nhân vật. Áp dụng cho cả action, start_state, "
    "end_state và mô tả nhân vật; giữ trạng thái nối cảnh nhất quán. "
    "Nếu ý tưởng có hành động gây thương tích, chuyển thành tình huống đe dọa và thoát hiểm "
    "không gây thương tích, không chỉ đổi từ ngữ để giữ nguyên cảnh bạo lực. "
    "Không tạo nội dung tình dục/khỏa thân, khai thác trẻ em, tự hại, cổ súy khủng bố/thù ghét, "
    "giả mạo người thật để lừa dối hoặc nội dung thân mật không đồng thuận. "
    "Dùng nhân vật hư cấu nguyên bản và tài sản có quyền sử dụng; không tự thêm người nổi tiếng, "
    "nhân vật có bản quyền hoặc giả định đã có sự đồng ý của người trong ảnh. "
)


def genre_instruction(genre):
    if not genre or genre == DEFAULT_GENRE:
        return ""
    return (f"Thể loại phim: {genre}. Giữ cấu trúc câu chuyện, nhịp kể, không khí và cách dàn cảnh "
            "phù hợp thể loại này; vẫn giữ nguyên nhận dạng nhân vật và các quy tắc tham chiếu.")
