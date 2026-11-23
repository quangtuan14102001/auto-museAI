"""Conservative local text preflight, not a vendor moderation API or guarantee.

Rules flag explicit scene descriptions, not genre names or all violence. They
cannot inspect reference pixels or predict a provider's output moderation.
"""
import re
import unicodedata
from dataclasses import dataclass


@dataclass(frozen=True)
class ContentIssue:
    field: str
    category: str
    excerpt: str
    shot_index: int | None = None


def _plain(text):
    value = unicodedata.normalize("NFD", str(text).casefold()).replace("đ", "d")
    return "".join(c for c in value if unicodedata.category(c) != "Mn")


_RULES = [
    ("Thương tích trực diện", r"\b(?:rach sau|vet (?:cao|can|rach) sau|vet thuong ho|loi noi tang|dut chi|chat dau|xe xac|mau me|dam mau|chay mau|bet mau|mau kho|tra tan|graphic gore|dismemberment|beheading|exposed organs)\b"),
    ("Tấn công gây đau/thương tích", r"\b(?:can (?:manh|sau|xe)|cao (?:manh|trung mat)|cao.{0,55}rach|gam thet dau|bite.{0,25}(?:wound|bleed)|scratch.{0,25}(?:deep|wound))\b"),
    ("Tình dục hoặc khỏa thân", r"\b(?:khieu dam|quan he tinh duc|lam dung tinh duc|khoa than|lo bo phan sinh duc|pornographic|explicit sex|nude|nudity)\b"),
    ("Tự hại", r"\b(?:tu sat|tu cat tay|tu lam hai ban than|self[- ]harm|commit suicide)\b"),
    ("Cổ súy bạo lực hoặc thù ghét", r"\b(?:co suy khung bo|kich dong thu han|kich dong bao luc|promote terrorism|incite violence|racial supremacy)\b"),
    ("Giả mạo gây hại hoặc xâm phạm riêng tư", r"\b(?:deepfake tinh duc|anh nong khong dong thuan|gia mao.{0,35}lua dao|non[- ]consensual intimate|impersonat.{0,35}scam)\b"),
]


def inspect_text(text, field, shot_index=None):
    issues = []
    # Keep negation local: "không máu me, nhưng cào rách sâu" must still flag
    # the second clause. No global removal of keywords or disguised rewrites.
    for clause in re.split(r"[,;.!?\n]|\b(?:nhưng|nhung|but|mà|ma)\b", str(text), flags=re.I):
        plain = _plain(clause)
        for category, pattern in _RULES:
            for match in re.finditer(pattern, plain):
                before = plain[:match.start()]
                if re.search(r"\b(?:khong|khong co|khong hien|khong mo ta|tranh|without|no|avoid)\s+(?:canh\s+)?$", before):
                    continue
                issues.append(ContentIssue(field, category, clause.strip()[:180], shot_index))
                break
    return list(dict.fromkeys(issues))


def inspect_project(project):
    pending = [(i, shot) for i, shot in enumerate(project.shots)
               if shot.status not in ("APPROVED", "REVIEW") and not shot.source_file]
    if not pending:
        return []
    issues = inspect_text(project.continuity_notes, "Quy tắc xuyên suốt")
    used = {key for _, shot in pending for key in [*shot.character_ids, shot.location_id]}
    for ref in project.references:
        if ref.id in used:
            issues.extend(inspect_text(ref.name + ". " + ref.description, f"Tham chiếu {ref.name}"))
    for i, shot in pending:
        for attr, label in (("prompt", "Hành động"), ("start_state", "Trạng thái đầu"), ("end_state", "Trạng thái cuối")):
            issues.extend(inspect_text(getattr(shot, attr), f"Clip {i + 1} · {label}", i))
    return issues


def describe_issues(issues):
    lines = [f"{item.field} — {item.category}: {item.excerpt}" for item in issues[:10]]
    if len(issues) > 10:
        lines.append(f"… còn {len(issues) - 10} mục cần rà.")
    return ("Cần chỉnh mô tả trước khi gửi Muse. Chưa gửi yêu cầu tạo ảnh/video.\n\n"
            + "\n".join(lines) + "\n\nĐổi nội dung cảnh thành phương án phù hợp; sửa cả trạng thái đầu/cuối "
            "để giữ mạch phim. Đây là kiểm tra cục bộ, không phải kết luận vi phạm của Muse.")
