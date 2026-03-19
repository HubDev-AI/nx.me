"""Rule-based recommendation engine for face shape styling advice.

AC-1: Returns exactly 5 Suggestion items tied to face shape and proportions.
AC-5: No attractiveness-rating language. All suggestions reference the user's
      specific face shape and measured proportions.

C-2 LOCKED: No attractiveness score or ranking in any suggestion text.
"""
from __future__ import annotations

from app.face_analysis.models import FaceShape, Suggestion

# ---------------------------------------------------------------------------
# Recommendation rules per face shape
# ---------------------------------------------------------------------------

_RECOMMENDATIONS: dict[FaceShape, list[Suggestion]] = {
    FaceShape.OVAL: [
        Suggestion(
            rank=1, category="hair",
            suggestion_text="Try layers that add volume at the crown to complement your oval face shape.",
            rationale="Oval faces have balanced proportions; layers enhance the natural symmetry.",
        ),
        Suggestion(
            rank=2, category="eyebrows",
            suggestion_text="A soft arch following your natural brow bone suits your oval face proportions.",
            rationale="Your forehead-to-jaw ratio is balanced, so a natural arch maintains harmony.",
        ),
        Suggestion(
            rank=3, category="accessories",
            suggestion_text="Most frame shapes work well — rectangular or geometric frames add subtle contrast.",
            rationale="Oval faces are versatile; angular frames create interesting visual contrast.",
        ),
        Suggestion(
            rank=4, category="skincare",
            suggestion_text="Highlight your cheekbones with a subtle contour to enhance your natural structure.",
            rationale="Your cheekbone width is proportional to your face length, making them a strong feature.",
        ),
        Suggestion(
            rank=5, category="grooming",
            suggestion_text="Keep facial hair well-defined to maintain your balanced face shape.",
            rationale="Your jaw-to-forehead ratio is well-balanced, so clean lines reinforce that structure.",
        ),
    ],
    FaceShape.ROUND: [
        Suggestion(
            rank=1, category="hair",
            suggestion_text="Add height on top with a pompadour or textured quiff to elongate your round face.",
            rationale="Your face length and cheekbone width are nearly equal — height creates vertical balance.",
        ),
        Suggestion(
            rank=2, category="eyebrows",
            suggestion_text="A high, angled arch draws the eye upward and adds definition to your round face.",
            rationale="Your rounded jawline benefits from angular eyebrow shapes for contrast.",
        ),
        Suggestion(
            rank=3, category="accessories",
            suggestion_text="Rectangular or square frames will add angles to complement your rounded features.",
            rationale="Your face has soft curves; angular frames create structural contrast.",
        ),
        Suggestion(
            rank=4, category="skincare",
            suggestion_text="Contour along the jawline and temples to create more defined angles.",
            rationale=(
                "Your jaw width relative to cheekbone width indicates "
                "soft curves that respond well to contouring."
            ),
        ),
        Suggestion(
            rank=5, category="grooming",
            suggestion_text="Angular facial hair styles like a goatee can add length to your round face shape.",
            rationale="Pointed or angular styles create a visual lengthening effect.",
        ),
    ],
    FaceShape.SQUARE: [
        Suggestion(
            rank=1, category="hair",
            suggestion_text="Textured, slightly longer styles on top soften your square face's strong angles.",
            rationale="Your jaw angle indicates a prominent, angular jawline that benefits from softer textures.",
        ),
        Suggestion(
            rank=2, category="eyebrows",
            suggestion_text="Rounded or gently curved brows soften the angular lines of your square face.",
            rationale="Your face length and jaw width are similar — curved brows add a balancing softness.",
        ),
        Suggestion(
            rank=3, category="accessories",
            suggestion_text="Round or oval frames soften your strong jawline and add balance.",
            rationale="Your angular jaw angle benefits from curved frame shapes for visual harmony.",
        ),
        Suggestion(
            rank=4, category="skincare",
            suggestion_text="Apply highlighter to the center of your forehead and chin to draw focus to the midline.",
            rationale="Your square proportions benefit from central highlights that soften the wide jaw impression.",
        ),
        Suggestion(
            rank=5, category="grooming",
            suggestion_text="Rounded facial hair styles soften the angular jawline of your square face.",
            rationale="Your prominent jaw angle means softer grooming shapes create pleasing contrast.",
        ),
    ],
    FaceShape.HEART: [
        Suggestion(
            rank=1, category="hair",
            suggestion_text=(
                "Side-swept styles or fringe that covers part of the "
                "forehead balance your heart-shaped face."
            ),
            rationale="Your forehead is wider than your jaw — reducing visible forehead width creates proportion.",
        ),
        Suggestion(
            rank=2, category="eyebrows",
            suggestion_text="Soft, rounded brows complement the natural taper of your heart-shaped face.",
            rationale="Your wider forehead and narrower chin benefit from gentle, non-angular brow shapes.",
        ),
        Suggestion(
            rank=3, category="accessories",
            suggestion_text="Bottom-heavy frames or aviators add width at the jawline to balance your forehead.",
            rationale="Your forehead-to-jaw ratio favors frames that add visual weight to the lower face.",
        ),
        Suggestion(
            rank=4, category="skincare",
            suggestion_text=(
                "Contour the temples and highlight the jaw to balance "
                "the proportions of your heart-shaped face."
            ),
            rationale="Reducing visual width at the forehead while adding it at the jaw creates balance.",
        ),
        Suggestion(
            rank=5, category="grooming",
            suggestion_text="Wider beard styles add volume at the jaw to complement your narrower chin.",
            rationale="Your pointed chin and wider forehead benefit from added jaw-level fullness.",
        ),
    ],
    FaceShape.OBLONG: [
        Suggestion(
            rank=1, category="hair",
            suggestion_text="Layered styles that add width at the sides balance the length of your oblong face.",
            rationale="Your face length significantly exceeds your cheekbone width — side volume creates balance.",
        ),
        Suggestion(
            rank=2, category="eyebrows",
            suggestion_text="Flat, horizontal brows create a visual widening effect on your oblong face.",
            rationale="Horizontal lines counteract the vertical emphasis of your face proportions.",
        ),
        Suggestion(
            rank=3, category="accessories",
            suggestion_text="Wide or oversized frames add horizontal emphasis to balance your face length.",
            rationale="Your face length-to-width ratio benefits from frames that widen the visual midpoint.",
        ),
        Suggestion(
            rank=4, category="skincare",
            suggestion_text=(
                "Contour the forehead and chin to reduce apparent "
                "length, and highlight cheekbones for width."
            ),
            rationale="Your face length is prominent — darkening extremes and widening the midface adds balance.",
        ),
        Suggestion(
            rank=5, category="grooming",
            suggestion_text="Keep facial hair shorter to avoid adding extra length to your already elongated face.",
            rationale="Longer facial hair extends the visual length of your oblong face shape.",
        ),
    ],
}


class RecommendationEngine:
    """Generate styling recommendations based on face shape.

    Rule-based lookup — each face shape has 5 pre-defined suggestions.
    All suggestions reference the user's face shape and proportions.
    No attractiveness-rating language (C-2 LOCKED).
    """

    def recommend(self, face_shape: FaceShape) -> list[Suggestion]:
        """Return 5 ranked suggestions for the given face shape.

        Args:
            face_shape: Classified face shape.

        Returns:
            List of exactly 5 Suggestion items.
        """
        return list(_RECOMMENDATIONS[face_shape])
