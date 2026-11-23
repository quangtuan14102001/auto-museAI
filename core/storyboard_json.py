"""Conservative JSON recovery: preserve complete shots, never invent fields."""
import json


class InvalidStoryboardJSON(ValueError):
    def __init__(self):
        super().__init__("AI trả kịch bản chưa đúng định dạng. Các bản nháp đã lưu vẫn được giữ; hãy thử tạo/viết tiếp lại.")


def remove_trailing_commas(text):
    result = []
    quoted = escaped = False
    for i, char in enumerate(text):
        if quoted:
            result.append(char)
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                quoted = False
        else:
            if char == '"':
                quoted = True
            if char == ",":
                next_position = i + 1
                while next_position < len(text) and text[next_position].isspace():
                    next_position += 1
                if text[next_position:next_position+1] in ("}", "]"):
                    continue
            result.append(char)
    return "".join(result)


def complete_prefix(text):
    decoder = json.JSONDecoder()
    result = {}
    position = 1
    required = {"action", "sequence", "continuation", "character_ids", "location_id", "start_state", "end_state"}
    if not text.startswith("{"):
        return None
    try:
        while position < len(text):
            while position < len(text) and text[position].isspace():
                position += 1
            key, position = decoder.raw_decode(text, position)
            if not isinstance(key, str):
                break
            while position < len(text) and text[position].isspace():
                position += 1
            if text[position:position+1] != ":":
                break
            position += 1
            while position < len(text) and text[position].isspace():
                position += 1
            if key == "shots" and text[position:position+1] == "[":
                position += 1
                result["shots"] = []
                while position < len(text):
                    while position < len(text) and text[position].isspace():
                        position += 1
                    if text[position:position+1] == "]":
                        position += 1
                        break
                    item, end = decoder.raw_decode(text, position)
                    if not isinstance(item, dict) or not required.issubset(item):
                        break
                    result["shots"].append(item)
                    position = end
                    while position < len(text) and text[position].isspace():
                        position += 1
                    if text[position:position+1] == ",":
                        position += 1
                    elif text[position:position+1] != "]":
                        break
                else:
                    break
            else:
                result[key], position = decoder.raw_decode(text, position)
            while position < len(text) and text[position].isspace():
                position += 1
            if text[position:position+1] != ",":
                break
            position += 1
    except json.JSONDecodeError:
        pass
    if (isinstance(result.get("characters"), list) and isinstance(result.get("locations"), list)
            and isinstance(result.get("shots"), list) and result["shots"]):
        return result
    return None


def decode_storyboard_json(text):
    clean = text.strip().lstrip("\ufeff")
    if clean.startswith("```"):
        clean = clean.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
    try:
        return json.loads(clean)
    except json.JSONDecodeError:
        clean = remove_trailing_commas(clean)
    try:
        return json.loads(clean)
    except json.JSONDecodeError:
        recovered = complete_prefix(clean)
        if recovered:
            return recovered
        raise InvalidStoryboardJSON() from None
