from dataclasses import dataclass, field
from typing import Any


@dataclass
class ContentDraft:
    platform: str
    format: str
    hook: str
    caption: str
    visual_direction: str
    cta: str
    hashtags: list[str] = field(default_factory=list)
    claims_used: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    #: scene_direction, lighting, seasonal_elements (list[str]), framing -- what
    #: the design/image agent should do to the reference photo.
    image_edit_brief: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "platform": self.platform,
            "format": self.format,
            "hook": self.hook,
            "caption": self.caption,
            "visual_direction": self.visual_direction,
            "cta": self.cta,
            "hashtags": self.hashtags,
            "claims_used": self.claims_used,
            "metadata": self.metadata,
            "image_edit_brief": self.image_edit_brief,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ContentDraft":
        return cls(
            platform=str(data.get("platform", "Instagram")),
            format=str(data.get("format", "post")),
            hook=str(data.get("hook", "")),
            caption=str(data.get("caption", "")),
            visual_direction=str(data.get("visual_direction", "")),
            cta=str(data.get("cta", "Book a site visit")),
            hashtags=list(data.get("hashtags", [])),
            claims_used=list(data.get("claims_used", [])),
            metadata=dict(data.get("metadata", {})),
            image_edit_brief=dict(data.get("image_edit_brief", {})),
        )

