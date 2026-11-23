import re
from typing import List, Dict, Tuple
from core.models import AliasItem


class PromptParser:
    """
    Handles extraction of multi-reference alias tags (e.g., @anh1, @anhaohong),
    validates existence in Alias dictionary, maps to physical file paths,
    and formats prompts for Muse AI composer.
    """

    TAG_REGEX = re.compile(r"(@[\w\d_-]+)", re.UNICODE)

    @classmethod
    def extract_tags(cls, text: str) -> List[str]:
        """
        Extracts all @tag occurrences from prompt in order of appearance,
        deduplicating while preserving order.
        """
        if not text:
            return []
        matches = cls.TAG_REGEX.findall(text)
        seen = set()
        result = []
        for m in matches:
            tag_clean = m.strip()
            if tag_clean not in seen:
                seen.add(tag_clean)
                result.append(tag_clean)
        return result

    @classmethod
    def resolve_aliases(
        cls,
        text: str,
        alias_dict: Dict[str, AliasItem],
        auto_attach_all_if_none: bool = False
    ) -> Tuple[List[AliasItem], List[str]]:
        """
        Resolves tags found in text to concrete AliasItem objects and file paths.
        Returns: (matched_aliases, missing_tags)
        """
        found_tags = cls.extract_tags(text)
        
        # If auto attach is enabled and prompt has no explicit tags, attach all available aliases
        if not found_tags and auto_attach_all_if_none and alias_dict:
            found_tags = list(alias_dict.keys())

        matched: List[AliasItem] = []
        missing: List[str] = []

        for tag in found_tags:
            tag_normalized = tag.lower()
            # Try case-insensitive lookup
            matched_item = None
            for k, v in alias_dict.items():
                if k.lower() == tag_normalized:
                    matched_item = v
                    break
            
            if matched_item:
                if matched_item not in matched:
                    matched.append(matched_item)
            else:
                missing.append(tag)

        return matched, missing

    @classmethod
    def clean_prompt_for_composer(
        cls,
        text: str,
        strip_tags: bool = False,
        replace_with_names: bool = False,
        alias_dict: Dict[str, AliasItem] = None
    ) -> str:
        """
        Prepares prompt for submission.
        - strip_tags: removes '@tag' tokens
        - replace_with_names: replaces '@tag' with the descriptive name of the reference
        """
        if not text:
            return ""

        cleaned = text.strip()
        if replace_with_names and alias_dict:
            for tag, item in alias_dict.items():
                if item.name:
                    cleaned = re.sub(re.escape(tag), item.name, cleaned, flags=re.IGNORECASE)

        if strip_tags:
            cleaned = cls.TAG_REGEX.sub("", cleaned)
            cleaned = re.sub(r"\s+", " ", cleaned).strip()

        return cleaned

    @classmethod
    def split_raw_prompt_list(cls, raw_text: str) -> List[str]:
        """
        Splits raw prompt block into separate task prompts.
        Supports splitting by double newlines or single newlines if non-empty.
        """
        if not raw_text or not raw_text.strip():
            return []
        
        # Split by two or more newlines first (paragraphs)
        blocks = [b.strip() for b in re.split(r"\n\s*\n", raw_text) if b.strip()]
        if len(blocks) > 1:
            return blocks
        
        # Fallback to line by line if single paragraph with multiple lines
        lines = [line.strip() for line in raw_text.splitlines() if line.strip()]
        return lines
