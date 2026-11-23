"""
Centralized selector definitions for Muse AI web automation.
Includes robust fallback selectors for different layout versions.
"""

from dataclasses import dataclass, field
from typing import Dict, List


@dataclass
class MuseSelectors:
    # URL endpoints
    base_url: str = "https://muse.ai"
    studio_url: str = "https://muse.ai"
    login_url: str = "https://muse.ai/login"

    # New chat button / link
    new_chat_button: List[str] = field(default_factory=lambda: [
        "button[aria-label*='new chat' i]",
        "button[aria-label*='new side chat' i]",
        "a[aria-label*='new chat' i]",
        "button:has-text('New chat')",
        "button:has-text('New Chat')",
        "a:has-text('New chat')",
        "[data-testid*='new-chat']",
        "[data-testid*='create-new']",
        "aside button:has-text('+')",
        "nav button:has-text('+')"
    ])

    # Composer input
    composer_textarea: List[str] = field(default_factory=lambda: [
        "textarea[placeholder*='Message' i]",
        "textarea[aria-label*='Message' i]",
        "textarea.text-text-primary",
        "textarea[placeholder*='prompt' i]",
        "textarea[placeholder*='describe' i]",
        "div[contenteditable='true'][role='textbox']",
        "#prompt-input"
    ])

    # Upload reference file input
    file_input: List[str] = field(default_factory=lambda: [
        "input[type='file']",
        "input[accept*='image']",
        "input[accept*='video']",
        "[data-testid='file-upload-input']"
    ])

    # Upload trigger button (if file input is hidden or triggered via button)
    upload_button: List[str] = field(default_factory=lambda: [
        "button[aria-label*='Attach' i]",
        "button[aria-label*='upload' i]",
        "button:has-text('Upload')",
        "button:has-text('Attach')",
        "[data-testid='upload-ref-btn']"
    ])

    # Submit / Generate button
    submit_button: List[str] = field(default_factory=lambda: [
        "button[aria-label*='Send' i]",
        "button[type='submit']",
        "button:has-text('Send')",
        "button:has-text('Generate')",
        "button:has-text('Create')",
        ".generate-btn",
        "#btn-generate"
    ])

    # Aspect ratio selectors
    aspect_ratio_button: List[str] = field(default_factory=lambda: [
        "button:has-text('Ratio')",
        "button:has-text('Aspect')",
        "button[aria-label*='ratio' i]",
        "[data-testid='aspect-ratio-selector']"
    ])

    # Mode selectors (Image / Video)
    mode_tab_image: List[str] = field(default_factory=lambda: [
        "button:has-text('Image')",
        "[role='tab']:has-text('Image')",
        "[data-tab='image']"
    ])
    mode_tab_video: List[str] = field(default_factory=lambda: [
        "button:has-text('Video')",
        "[role='tab']:has-text('Video')",
        "[data-tab='video']"
    ])

    # Loading / Progress states
    progress_indicators: List[str] = field(default_factory=lambda: [
        ".generating",
        ".loading",
        "[data-state='loading']",
        "[aria-busy='true']",
        ".progress-bar",
        ".spinner",
        "[class*='loader' i]",
        "[class*='generating' i]",
        "[class*='loading' i]",
        "[aria-label*='generating' i]",
        "[aria-label*='loading' i]"
    ])

    # Download buttons & actions on completed media
    download_button: List[str] = field(default_factory=lambda: [
        "a[download]",
        "button[aria-label*='download' i]",
        "button:has-text('Download')",
        "[data-testid*='download']",
        "button[title*='Download' i]",
        "a[href*='.mp4']"
    ])

    # Completed media elements
    completed_media: List[str] = field(default_factory=lambda: [
        "[data-testid*='result-media']",
        ".result-card img",
        ".result-card video",
        "video[controls]",
        "a[download]"
    ])

    # Quota / Error notices
    quota_warning: List[str] = field(default_factory=lambda: [
        "text='Quota exceeded'",
        "text='Out of credits'",
        "text='Rate limit reached'",
        "text='Upgrade plan'",
        "text='Insufficient credits'"
    ])

    @classmethod
    def from_dict(cls, data: dict) -> "MuseSelectors":
        selectors = cls()
        if not data:
            return selectors
        for k, v in data.items():
            if hasattr(selectors, k):
                if isinstance(v, str):
                    setattr(selectors, k, [v])
                elif isinstance(v, list):
                    setattr(selectors, k, v)
        return selectors
