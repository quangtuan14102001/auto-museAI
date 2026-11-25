"""Credential input and safe Gemini diagnostics; never expose provider bodies."""
import re


def normalize_gemini_key(value):
    if value is None:
        return ''
    if not isinstance(value, str):
        raise ValueError('API key Gemini phải là văn bản.')
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
        value = value[1:-1].strip()
    if value and (len(value) > 512 or re.search(r'\s|[\x00-\x1f\x7f]', value) or '://' in value):
        raise ValueError('Chỉ dán giá trị API key Gemini, không dán đường dẫn, đoạn code hoặc khoảng trắng bên trong.')
    return value


def gemini_error(response):
    reason = ''
    try:
        details = response.json().get('error', {}).get('details', [])
        reason = next((d.get('reason', '') for d in details if isinstance(d, dict) and d.get('reason')), '')
    except (ValueError, AttributeError, TypeError):
        pass
    if reason in ('API_KEY_INVALID', 'API_KEY_EXPIRED'):
        return 'API key Gemini không hợp lệ hoặc đã hết hiệu lực. Kiểm tra lại key trong Google AI Studio.'
    if reason in ('API_KEY_SERVICE_BLOCKED', 'API_KEY_HTTP_REFERRER_BLOCKED', 'API_KEY_IP_ADDRESS_BLOCKED'):
        return 'API key đang bị giới hạn dịch vụ hoặc nguồn truy cập. Kiểm tra quyền gọi Gemini API của key.'
    messages = {
        400: 'Gemini từ chối yêu cầu (HTTP 400). Kiểm tra API key, model và tham số; chưa thể kết luận key sai.',
        401: 'API key Gemini không hợp lệ hoặc chưa được xác thực.',
        402: 'Gemini yêu cầu kiểm tra thanh toán hoặc hạn mức của dự án.',
        403: 'API key/dự án chưa được phép gọi Gemini. Kiểm tra quyền truy cập và trạng thái dự án trong Google AI Studio.',
        404: 'Gemini chưa cung cấp model tạo văn bản khả dụng cho API key này.',
        429: 'Gemini đã hết hạn mức hoặc đang giới hạn lượt gọi. Kiểm tra quota trong Google AI Studio; lỗi này không có nghĩa là key sai.',
        500: 'Gemini đang gặp lỗi dịch vụ (HTTP 500). Thử lại sau.',
        503: 'Gemini tạm thời chưa sẵn sàng (HTTP 503). Thử lại sau; không cần thay key chỉ vì lỗi này.',
    }
    return messages.get(response.status_code, f'Gemini chưa xử lý được yêu cầu (HTTP {response.status_code}). Thử lại sau.')
