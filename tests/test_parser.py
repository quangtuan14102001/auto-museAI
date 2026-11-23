import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.models import AliasItem
from core.prompt_parser import PromptParser

def test_prompt_parser():
    text = "Cảnh quay cận cảnh @anh1 đang nở nụ cười tươi, bên cạnh sản phẩm @anh3 và áo @anhaohong"
    tags = PromptParser.extract_tags(text)
    assert tags == ["@anh1", "@anh3", "@anhaohong"], f"Expected tags mismatch: {tags}"

    alias_dict = {
        "@anh1": AliasItem(tag="@anh1", name="Nhân vật nữ", file_path="assets/sample_char1.jpg"),
        "@anh3": AliasItem(tag="@anh3", name="Sản phẩm serum", file_path="assets/sample_prod1.jpg"),
        "@anhaohong": AliasItem(tag="@anhaohong", name="Áo hồng", file_path="assets/sample_cloth1.jpg"),
    }

    matched, missing = PromptParser.resolve_aliases(text, alias_dict)
    assert len(matched) == 3, f"Expected 3 matched aliases, got {len(matched)}"
    assert len(missing) == 0, f"Expected 0 missing tags, got {missing}"

    # Test unknown tag
    text_with_unknown = "Người mẫu @anh1 cầm theo @vatchuatontai"
    matched_2, missing_2 = PromptParser.resolve_aliases(text_with_unknown, alias_dict)
    assert len(matched_2) == 1
    assert missing_2 == ["@vatchuatontai"]

    # Test splitting raw prompts
    raw_block = """Prompt cảnh 1: @anh1 đi dạo

Prompt cảnh 2: @anh3 đặt trên bàn

Prompt cảnh 3: @anhaohong rực rỡ"""

    split_prompts = PromptParser.split_raw_prompt_list(raw_block)
    assert len(split_prompts) == 3, f"Expected 3 prompts, got {len(split_prompts)}"

    print("ALL PROMPT PARSER TESTS PASSED PERFECTLY!")

if __name__ == "__main__":
    test_prompt_parser()
