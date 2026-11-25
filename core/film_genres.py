from dataclasses import dataclass
import re

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


@dataclass(frozen=True)
class GenreProfile:
    story: str
    shot: str
    visual: str
    sound: str
    review: str


# Authoring guides for the film pipeline, not executable Codex skills.
GENRE_PROFILES = {
    "Phiêu lưu": GenreProfile(
        "Mục tiêu hành trình rõ; rời nơi quen thuộc, gặp thử thách tăng dần, lựa chọn then chốt và trở về/thay đổi.",
        "Mỗi cảnh khám phá một điều mới hoặc vượt một trở ngại; xen nhịp nghỉ để người xem hiểu địa hình.",
        "Toàn cảnh định vị hành trình, trung cảnh hành động, chi tiết vật dẫn đường; màu sắc theo địa điểm.",
        "Âm thanh thiên nhiên và chủ đề hành trình, tăng năng lượng ở thử thách.",
        "Mỗi chặng có quan hệ nhân quả và làm thay đổi khoảng cách tới mục tiêu; không chỉ đổi phong cảnh."),
    "Hành động": GenreProfile(
        "Thiết lập mục tiêu và rủi ro, trở ngại tăng dần, đảo chiều và giải quyết bằng hành động dễ hiểu.",
        "Một động tác chủ đạo mỗi clip; xác định ai ở đâu, hướng di chuyển và kết quả; xen phản ứng/hồi sức.",
        "Bố cục rõ không gian, tracking vừa phải; không rung máy hỗn loạn hoặc đổi trục vô cớ.",
        "Nhịp dồn ở cao trào, hiệu ứng chuyển động vừa đủ; tránh âm thanh thương tích.",
        "Hành động có đầu-cuối khả thi trong thời lượng, địa hình liên tục và không gây thương tích trực diện."),
    "Hài": GenreProfile(
        "Dựng kỳ vọng, lặp có biến đổi, hiểu lầm vô hại và cú đảo bất ngờ; kết bằng giải tỏa.",
        "Dành thời gian cho chuẩn bị, bất ngờ và phản ứng; không nhồi nhiều trò đùa vào một clip.",
        "Khung trung/toàn để thấy tương tác, chi tiết đạo cụ và khoảng dừng phản ứng; hình ảnh dễ đọc.",
        "Khoảng lặng đúng lúc và hiệu ứng nhẹ, không lạm dụng tiếng cười thu sẵn.",
        "Có thiết lập để cú hài được hiểu; không lấy làm nhục, bắt nạt hoặc đau đớn làm trò cười."),
    "Tình cảm": GenreProfile(
        "Thiết lập kết nối, khác biệt hoặc hiểu lầm, lựa chọn chân thành và sự thay đổi trong quan hệ.",
        "Thể hiện qua ánh mắt, cử chỉ và hành động quan tâm; xung đột và hòa giải có nguyên nhân.",
        "Cận/trung cảnh phản ứng, ánh sáng mềm theo bối cảnh; tránh thay đổi diện mạo để biểu đạt cảm xúc.",
        "Âm nhạc tiết chế, để khoảng trống cho đối thoại và cảm xúc.",
        "Quan hệ phát triển qua hành động cụ thể, tôn trọng ranh giới và sự đồng thuận; không nội dung tình dục."),
    "Tâm lý": GenreProfile(
        "Mong muốn bên ngoài đối lập nhu cầu bên trong; áp lực tăng dần dẫn tới lựa chọn và hệ quả.",
        "Một thay đổi cảm xúc có thể quan sát mỗi cảnh; dùng hành vi và đạo cụ thay vì giải thích dài.",
        "Cận phản ứng, bố cục/khoảng cách có chủ đích và máy chậm; không lạm dụng biểu tượng mơ hồ.",
        "Âm nền tinh tế và khoảng lặng, không dùng nhạc để thay thế diễn biến.",
        "Động cơ và chuyển biến được chuẩn bị; không kỳ thị sức khỏe tâm thần hoặc lãng mạn hóa tự hại."),
    "Kinh dị": GenreProfile(
        "Dấu hiệu bất thường, dự cảm, đe dọa tăng dần, tìm lối thoát và kết thúc có hệ quả.",
        "Gợi điều chưa thấy bằng bóng đổ, chuyển động ngoài khung và phản ứng; tạo hồi hộp trước khi hé lộ.",
        "Không gian âm, ánh sáng tương phản vẫn đọc được chủ thể, máy chậm; không máu me hoặc hình ảnh gây thương tích.",
        "Âm môi trường và khoảng lặng, điểm nhấn có chuẩn bị; không phụ thuộc jump scare liên tục.",
        "Có xây dựng căng thẳng bằng câu chuyện, không chỉ tối hình hoặc tăng tiếng động; hành động vẫn an toàn."),
    "Trinh thám": GenreProfile(
        "Câu hỏi bí ẩn rõ, manh mối xuất hiện trước kết luận, giả thuyết, kiểm chứng và lời giải có căn cứ.",
        "Mỗi cảnh phát hiện/đối chiếu một manh mối hoặc thay đổi giả thuyết; phân biệt quan sát và suy đoán.",
        "Chi tiết chứng cứ dễ nhìn kết hợp phản ứng người điều tra; giữ nguyên vị trí và đặc điểm đạo cụ.",
        "Không khí tò mò, điểm nhấn lúc phát hiện, tránh báo trước lời giải bằng nhạc quá lộ.",
        "Lời giải dựa trên manh mối đã cho xem; không thêm chứng cứ quyết định từ hư không hoặc cáo buộc người thật."),
    "Khoa học viễn tưởng": GenreProfile(
        "Nêu giả định công nghệ/thế giới, giới hạn vận hành, hệ quả và lựa chọn của nhân vật.",
        "Cho thấy công nghệ tác động tới mục tiêu qua một thao tác cụ thể; công năng nhất quán giữa cảnh.",
        "Thiết kế vật liệu, đạo cụ và giao diện nhất quán; định vị tỷ lệ không gian, không tự thêm hiệu ứng vô cớ.",
        "Âm cơ khí/điện tử theo thiết bị và không gian; tiết chế để vẫn theo dõi được hành động.",
        "Không tự tạo khả năng mới để giải quyết cao trào; phân biệt giả định hư cấu với thông tin khoa học thực."),
    "Kỳ ảo": GenreProfile(
        "Thiết lập thế giới, quy luật và cái giá của phép thuật, thử thách, lựa chọn và sự biến đổi.",
        "Một hiệu ứng phép thuật chính mỗi clip, có nguồn phát và kết quả; giữ giới hạn đã thiết lập.",
        "Họa tiết, bảng màu và vật phẩm thống nhất; hiệu ứng phục vụ hành động, giữ nhận dạng nhân vật.",
        "Chủ đề kỳ ảo và âm tự nhiên của thế giới; mỗi hiệu ứng có âm sắc nhất quán.",
        "Phép thuật không giải quyết mọi vấn đề tùy tiện; vật phẩm và quy luật không thay đổi giữa clip."),
    "Gia đình": GenreProfile(
        "Mục tiêu gần gũi, bất đồng dễ hiểu, hợp tác hoặc thấu hiểu và kết thúc ấm áp có hành động cụ thể.",
        "Nhịp rõ ràng, biểu cảm dễ hiểu, xen khoảnh khắc vui và hỗ trợ nhau; tránh tình huống đe dọa kéo dài.",
        "Bố cục dễ đọc, ánh sáng thân thiện phù hợp địa điểm; không biến mọi cảnh thành màu rực quá mức.",
        "Âm nhạc nhẹ và vui, chuyển sắc theo cảm xúc; không âm thanh đột ngột quá mạnh.",
        "Giải quyết bằng hợp tác, không giảng đạo dài; không làm nhục hoặc đặt trẻ em vào tình huống nguy hiểm."),
    "Tài liệu": GenreProfile(
        "Đặt câu hỏi quan sát, bối cảnh, bằng chứng hoặc quy trình, diễn biến và kết luận đúng mức.",
        "Mỗi cảnh quan sát một hành vi/quá trình có thể quay; không tự thêm suy nghĩ hoặc đối thoại cho động vật.",
        "Góc nhìn quan sát, toàn cảnh định vị và chi tiết hành vi, màu tự nhiên; không hiệu ứng giả chứng cứ.",
        "Ưu tiên âm môi trường; lời dẫn nếu có phân biệt điều quan sát được với diễn giải.",
        "Không bịa số liệu, trích dẫn hay sự kiện; cảnh AI tái hiện không được trình bày là tư liệu thật."),
}


def genre_profiles(genre):
    """Support custom combinations without substring collisions or dropping custom text."""
    text = (genre or '').strip()
    if not text or text == DEFAULT_GENRE:
        return []
    return [(name, profile) for name, profile in GENRE_PROFILES.items()
            if re.search(r'(?<!\w)' + re.escape(name) + r'(?!\w)', text, re.IGNORECASE)]


def genre_instruction(genre, stage='storyboard'):
    if stage not in ('storyboard', 'video', 'reference'):
        raise ValueError('Unknown genre instruction stage')
    if not genre or genre == DEFAULT_GENRE:
        return ('Tự chọn thể loại phù hợp ý tưởng; thống nhất nhịp kể, cách dàn cảnh và hình ảnh xuyên suốt. '
                'Không thay đổi nhận dạng nhân vật hoặc quy tắc nối cảnh.')
    parts = [f'Thể loại phim: {genre}.']
    profiles = genre_profiles(genre)
    if len(profiles) > 1:
        parts.append('Phối hợp các thể loại thành một câu chuyện nhất quán; không tạo lại cốt truyện ở mỗi clip.')
    if not profiles:
        parts.append('Tự xây dựng cấu trúc, nhịp kể và hình ảnh phù hợp thể loại riêng này; không tự đổi thể loại.')
    for name, profile in profiles:
        parts.append(f'Hướng dẫn {name}:')
        if stage == 'storyboard':
            parts += ['Cấu trúc: ' + profile.story, 'Nhịp cảnh: ' + profile.shot,
                      'Hình ảnh: ' + profile.visual, 'Âm thanh dự kiến: ' + profile.sound,
                      'Tự rà soát trước khi trả JSON: ' + profile.review]
        elif stage == 'video':
            parts += ['Dàn cảnh: ' + profile.shot, 'Hình ảnh: ' + profile.visual,
                      'Nếu công cụ hỗ trợ âm thanh: ' + profile.sound]
        else:
            parts.append('Định hướng hình ảnh: ' + profile.visual)
    if stage == 'reference':
        parts.append('Đây là ảnh chuẩn nhận dạng/địa điểm, không phải cảnh hành động. '
                     'Ưu tiên thấy rõ nhân vật/bố cục, không áp bóng tối hay hiệu ứng che đặc điểm.')
    elif stage == 'video':
        parts.append('Chỉ thực hiện cảnh hiện tại; không tự thêm đoạn mở/kết hay montage. '
                     'Clip tiếp nối giữ nguyên hướng máy, ánh sáng và trạng thái từ khung trước; '
                     'quy tắc liên tục và ảnh tham chiếu ưu tiên hơn gợi ý phong cách.')
    parts.append('Giữ nguyên nhận dạng nhân vật, quy tắc tham chiếu và yêu cầu an toàn nội dung.')
    return '\n'.join(parts)
