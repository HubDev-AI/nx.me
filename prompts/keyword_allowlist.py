"""Prompt keyword allowlist for glow-up generation.

Only these keywords can appear in the interpolated generation prompt.
This prevents prompt injection via malicious recommendation text.

Categories map to face analysis recommendation categories.
"""

HAIR_KEYWORDS: frozenset[str] = frozenset({
    "textured crop", "side part", "slicked back", "pompadour",
    "layered cut", "curtain bangs", "tapered fade", "undercut",
    "shorter sides", "longer top", "voluminous blowout",
    "soft waves", "defined curls", "straightened",
    "well-groomed hair", "polished hairstyle", "neat hairline",
    "healthy shine", "reduced frizz",
})

EYEBROW_KEYWORDS: frozenset[str] = frozenset({
    "refined eyebrow arch", "groomed eyebrows", "natural brow shape",
    "defined brows", "trimmed brows", "filled brows",
    "soft brow arch", "structured brows",
})

FACIAL_HAIR_KEYWORDS: frozenset[str] = frozenset({
    "clean shaven", "neat stubble", "trimmed beard",
    "defined beard line", "groomed mustache", "shaped goatee",
    "well-maintained facial hair",
})

LIGHTING_STYLE_KEYWORDS: frozenset[str] = frozenset({
    "improved lighting", "soft natural lighting", "golden hour glow",
    "studio lighting", "even skin lighting", "reduced harsh shadows",
    "warm tones", "cool tones", "balanced exposure",
})

GROOMING_KEYWORDS: frozenset[str] = frozenset({
    "clear skin", "even complexion", "reduced blemishes",
    "healthy skin glow", "moisturized skin appearance",
    "well-rested appearance", "brighter eyes",
})

# Union of all allowed keywords
ALLOWED_KEYWORDS: frozenset[str] = (
    HAIR_KEYWORDS | EYEBROW_KEYWORDS | FACIAL_HAIR_KEYWORDS
    | LIGHTING_STYLE_KEYWORDS | GROOMING_KEYWORDS
)
