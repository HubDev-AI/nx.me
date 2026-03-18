"""Prompt keyword allowlist for glow-up generation.

74 allowed keywords across 8 categories. Only these can appear in the
generation prompt. Prevents prompt injection AND ensures the model
focuses on styling, never skin modification.

BLOCKED by design: Any term that triggers skin smoothing, blemish removal,
or beauty-filter behavior in diffusion models.
"""

HAIR_KEYWORDS: frozenset[str] = frozenset({
    "textured crop", "side part", "slicked back", "pompadour",
    "layered cut", "curtain bangs", "tapered fade", "undercut",
    "shorter sides", "longer top", "voluminous blowout",
    "soft waves", "defined curls", "straightened",
    "well-groomed hair", "polished hairstyle", "neat hairline",
    "healthy shine",
    # Extended
    "bob cut", "pixie cut", "buzz cut", "french crop",
    "middle part", "messy bun", "high ponytail", "braided style",
    "beach waves", "afro texture", "twisted locs", "silk press",
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

CLOTHING_KEYWORDS: frozenset[str] = frozenset({
    "fitted blazer", "crisp white shirt", "leather jacket",
    "turtleneck", "denim jacket", "linen shirt",
    "tailored suit", "casual streetwear", "athleisure",
    "smart casual",
})

ACCESSORIES_KEYWORDS: frozenset[str] = frozenset({
    "statement necklace", "minimal earrings", "rectangular glasses",
    "round glasses", "aviator sunglasses", "watch",
    "scarf", "headband",
})

LIGHTING_KEYWORDS: frozenset[str] = frozenset({
    "improved lighting", "soft natural lighting", "golden hour glow",
    "studio lighting", "even skin lighting",
    "warm tones", "cool tones", "balanced exposure",
})

GROOMING_KEYWORDS: frozenset[str] = frozenset({
    "well-rested appearance", "brighter eyes", "healthy complexion",
})

# Union of all allowed keywords (74 total)
ALLOWED_KEYWORDS: frozenset[str] = (
    HAIR_KEYWORDS | EYEBROW_KEYWORDS | FACIAL_HAIR_KEYWORDS
    | CLOTHING_KEYWORDS | ACCESSORIES_KEYWORDS
    | LIGHTING_KEYWORDS | GROOMING_KEYWORDS
)

# Safe extension keywords — used ONLY for weak-transformation boost (Section 6.5)
# Not part of primary allowlist. Added when output is too conservative.
SAFE_EXTENSION_KEYWORDS: frozenset[str] = frozenset({
    "elevated style", "refined look", "fashion-forward",
    "magazine cover ready", "red carpet styling", "freshly styled",
    "sharp dressed", "well-coordinated outfit",
    "professional grooming", "editorial quality",
})

# Explicitly blocked — these trigger beauty-filter behavior
BLOCKED_KEYWORDS: frozenset[str] = frozenset({
    "clear skin", "even complexion", "reduced blemishes",
    "moisturized skin", "skin glow", "smooth skin", "poreless",
    "dewy skin", "glass skin", "skin resurfacing", "anti-aging",
    "wrinkle reduction", "pore minimizing", "skin brightening",
    "complexion evening",
})
