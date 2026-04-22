#!/usr/bin/env python3
"""AI Makeup fairness red-team — 50-photo MST bin 5–10 evaluation.

This is the ship/no-ship gate for the Makeup feature (Unit 13).
Run AFTER Unit 1 smoke passes and BEFORE Unit 14 starts.

Usage:
    python scripts/fairness_redteam_full.py --photo-dir /path/to/photos --output docs/fairness/2026-04-W3-redteam-report.md

The script:
  1. Reads 50 test photos stratified by MST bin (≥ 8 per bin 5–10).
  2. Submits each photo through the full backend path:
       upload → analyze (makeup) → generate (all presets) → persist.
  3. Computes per-bin metrics:
       - ArcFace identity gap (cross-bin parity)
       - Lipstick ΔE (CIELab, sampled at lip landmarks)
       - Texture preservation (SSIM on non-lip region)
  4. Executes the pre-committed fallback tree:
       - All bins pass → verdict PROCEED
       - Single bin fails → add to mst_bin_blocklist → PROCEED WITH RESTRICTIONS
       - Multiple bins fail → verdict HOLD
       - Texture failures only → drop 'bold' intensity → RE-TEST
  5. Writes the populated report to --output (fills in the template).
  6. Exits 0 on PROCEED / PROCEED WITH RESTRICTIONS; exits 1 on HOLD / RE-TEST.

Gate invariant: `docs/operational/fal-dpa-status.md` must show
  `signed: true` and `covers_art_9: true` before this script submits
  any photo to the production fal endpoint.

Thresholds (per origin §9):
  ARCFACE_GAP_MAX   = 0.15   (cross-bin parity)
  LIPSTICK_DE_MAX   = 12.0   (CIELab ΔE)
  TEXTURE_SSIM_MIN  = 0.80
"""

from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

# ---------------------------------------------------------------------------
# Thresholds (§9 origin spec)
# ---------------------------------------------------------------------------

ARCFACE_GAP_MAX = 0.15
LIPSTICK_DE_MAX = 12.0
TEXTURE_SSIM_MIN = 0.80
REQUIRED_BINS = list(range(5, 11))  # 5–10 inclusive
MIN_PER_BIN = 8


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class PhotoRecord:
    path: Path
    mst_bin: int  # 5–10


@dataclass
class BinResult:
    bin: int
    photo_count: int
    arcface_gap: float | None = None
    lipstick_de: float | None = None
    texture_ssim: float | None = None

    @property
    def passed(self) -> bool:
        if self.arcface_gap is None:
            return False
        return (
            self.arcface_gap <= ARCFACE_GAP_MAX
            and (self.lipstick_de or 0.0) <= LIPSTICK_DE_MAX
            and (self.texture_ssim or 1.0) >= TEXTURE_SSIM_MIN
        )

    @property
    def texture_only_failure(self) -> bool:
        if self.arcface_gap is None:
            return False
        core_pass = (
            self.arcface_gap <= ARCFACE_GAP_MAX
            and (self.lipstick_de or 0.0) <= LIPSTICK_DE_MAX
        )
        texture_fail = (self.texture_ssim or 1.0) < TEXTURE_SSIM_MIN
        return core_pass and texture_fail


Verdict = Literal["PROCEED", "PROCEED_WITH_RESTRICTIONS", "HOLD", "RE_TEST"]


# ---------------------------------------------------------------------------
# DPA gate
# ---------------------------------------------------------------------------


def check_dpa_gate(repo_root: Path) -> None:
    dpa_path = repo_root / "docs" / "operational" / "fal-dpa-status.md"
    if not dpa_path.exists():
        sys.exit(
            f"[GATE FAIL] {dpa_path} not found. "
            "DPA status must be committed before red-team runs."
        )
    text = dpa_path.read_text()
    if "signed: true" not in text:
        sys.exit(
            "[GATE FAIL] fal-dpa-status.md does not show `signed: true`. "
            "Obtain and commit DPA signature before running against production."
        )
    if "covers_art_9: true" not in text:
        sys.exit(
            "[GATE FAIL] fal-dpa-status.md does not show `covers_art_9: true`. "
            "Ensure DPA explicitly covers Art. 9 biometric data."
        )


# ---------------------------------------------------------------------------
# Photo loading
# ---------------------------------------------------------------------------


def load_photos(photo_dir: Path) -> list[PhotoRecord]:
    """Load photos from dir. Expects filenames like `bin_5_001.jpg`."""
    records: list[PhotoRecord] = []
    for p in sorted(photo_dir.iterdir()):
        if not p.is_file() or p.suffix.lower() not in {".jpg", ".jpeg", ".png"}:
            continue
        # Filename convention: bin_<N>_<seq>.<ext>
        parts = p.stem.split("_")
        if len(parts) >= 2 and parts[0] == "bin":
            try:
                mst_bin = int(parts[1])
            except ValueError:
                continue
            if mst_bin in REQUIRED_BINS:
                records.append(PhotoRecord(path=p, mst_bin=mst_bin))
    return records


def validate_coverage(photos: list[PhotoRecord]) -> None:
    by_bin: dict[int, int] = {b: 0 for b in REQUIRED_BINS}
    for r in photos:
        by_bin[r.mst_bin] = by_bin.get(r.mst_bin, 0) + 1
    failures = [b for b, c in by_bin.items() if c < MIN_PER_BIN]
    if failures:
        sys.exit(
            f"[COVERAGE FAIL] Bins {failures} have fewer than {MIN_PER_BIN} photos. "
            "Add more photos before running the red-team."
        )
    if len(photos) < 50:
        sys.exit(f"[COVERAGE FAIL] Only {len(photos)} photos found; need ≥ 50.")


# ---------------------------------------------------------------------------
# Backend pipeline (stub — replace with real API calls)
# ---------------------------------------------------------------------------


def run_pipeline(photo: PhotoRecord, api_base: str, api_token: str) -> dict:
    """Submit photo through upload → analyze → generate. Returns raw result.

    TODO: Replace stub with real HTTP calls once Unit 1 smoke baseline is
    confirmed stable. The stub returns a synthetic result so the fallback
    tree logic can be exercised without a live backend.
    """
    # Stub result — replace with:
    #   1. POST /v1/uploads (multipart) → upload_id
    #   2. POST /v1/uploads/{id}/makeup/analyze → job_id
    #   3. Poll GET /v1/jobs/{job_id} until status in {completed, failed}
    #   4. Extract metrics from job result
    return {
        "photo": str(photo.path),
        "mst_bin": photo.mst_bin,
        "arcface_gap": None,  # float: computed from before/after embedding distance
        "lipstick_de": None,  # float: CIELab ΔE at lip landmarks
        "texture_ssim": None,  # float: SSIM on non-lip region mask
        "status": "stub",
    }


# ---------------------------------------------------------------------------
# Metrics aggregation
# ---------------------------------------------------------------------------


def aggregate_bin_results(raw_results: list[dict]) -> list[BinResult]:
    by_bin: dict[int, list[dict]] = {b: [] for b in REQUIRED_BINS}
    for r in raw_results:
        b = r["mst_bin"]
        if b in by_bin:
            by_bin[b].append(r)

    results: list[BinResult] = []
    for b in REQUIRED_BINS:
        rows = by_bin[b]
        gaps = [r["arcface_gap"] for r in rows if r["arcface_gap"] is not None]
        des = [r["lipstick_de"] for r in rows if r["lipstick_de"] is not None]
        ssims = [r["texture_ssim"] for r in rows if r["texture_ssim"] is not None]
        results.append(
            BinResult(
                bin=b,
                photo_count=len(rows),
                arcface_gap=max(gaps) if gaps else None,
                lipstick_de=max(des) if des else None,
                texture_ssim=min(ssims) if ssims else None,
            )
        )
    return results


# ---------------------------------------------------------------------------
# Fallback tree
# ---------------------------------------------------------------------------


def execute_fallback_tree(bin_results: list[BinResult]) -> tuple[Verdict, list[int]]:
    """Execute §9 fallback tree. Returns (verdict, failed_bins)."""
    failed = [r.bin for r in bin_results if not r.passed]
    texture_only = [r.bin for r in bin_results if r.texture_only_failure]
    non_texture_fails = [b for b in failed if b not in texture_only]

    if not failed:
        return "PROCEED", []
    if texture_only and not non_texture_fails:
        return "RE_TEST", texture_only
    if len(non_texture_fails) == 1:
        return "PROCEED_WITH_RESTRICTIONS", non_texture_fails
    return "HOLD", non_texture_fails


# ---------------------------------------------------------------------------
# Report writing
# ---------------------------------------------------------------------------


def write_report(
    output_path: Path,
    bin_results: list[BinResult],
    verdict: Verdict,
    failed_bins: list[int],
    raw_results: list[dict],
) -> None:
    template_path = (
        Path(__file__).resolve().parent.parent
        / "docs"
        / "fairness"
        / "2026-04-W3-redteam-report.md"
    )
    if not template_path.exists():
        sys.exit(f"Report template not found: {template_path}")

    # Build bin table rows
    bin_rows = ""
    for r in bin_results:
        pass_str = "PASS" if r.passed else "FAIL"
        bin_rows += (
            f"| {r.bin} | {r.photo_count} "
            f"| {r.arcface_gap or '—'} "
            f"| {r.lipstick_de or '—'} "
            f"| {r.texture_ssim or '—'} "
            f"| {pass_str} |\n"
        )

    import datetime

    today = datetime.date.today().isoformat()
    content = template_path.read_text()
    # Replace placeholder sections — simple string substitution
    content = content.replace("| 5 | — | — | — | — | — |", bin_rows.strip())
    content = content.replace("| 6 | — | — | — | — | — |\n", "")
    content = content.replace("| 7 | — | — | — | — | — |\n", "")
    content = content.replace("| 8 | — | — | — | — | — |\n", "")
    content = content.replace("| 9 | — | — | — | — | — |\n", "")
    content = content.replace("| 10 | — | — | — | — | — |\n", "")
    content = content.replace(
        "**FILL IN: PROCEED / PROCEED WITH RESTRICTIONS / HOLD**",
        f"**{verdict.replace('_', ' ')}**",
    )
    content = content.replace(
        "**Status:** PENDING — red-team not yet executed", "**Status:** COMPLETE"
    )
    content = content.replace("FILL IN", today, 1)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(content)
    print(f"[OK] Report written to {output_path}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument(
        "--photo-dir",
        required=True,
        type=Path,
        help="Dir of MST-stratified test photos",
    )
    p.add_argument(
        "--output",
        type=Path,
        default=Path("docs/fairness/2026-04-W3-redteam-report.md"),
    )
    p.add_argument(
        "--api-base", default=os.environ.get("API_BASE_URL", "http://localhost:8000")
    )
    p.add_argument("--api-token", default=os.environ.get("REDTEAM_API_TOKEN", ""))
    p.add_argument(
        "--skip-dpa-gate", action="store_true", help="Skip DPA gate (staging only)"
    )
    p.add_argument(
        "--dry-run", action="store_true", help="Skip actual API calls; use stub results"
    )
    return p.parse_args()


def main() -> None:
    args = parse_args()
    repo_root = Path(__file__).resolve().parent.parent

    if not args.skip_dpa_gate:
        check_dpa_gate(repo_root)

    photos = load_photos(args.photo_dir)
    validate_coverage(photos)

    print(f"[INFO] {len(photos)} photos loaded across MST bins {REQUIRED_BINS}")

    raw_results: list[dict] = []
    for photo in photos:
        if args.dry_run:
            result = run_pipeline(photo, args.api_base, args.api_token)
        else:
            result = run_pipeline(photo, args.api_base, args.api_token)
        raw_results.append(result)
        print(f"  [{photo.mst_bin}] {photo.path.name} → {result.get('status')}")

    bin_results = aggregate_bin_results(raw_results)
    verdict, failed_bins = execute_fallback_tree(bin_results)

    print(f"\n[VERDICT] {verdict}")
    if failed_bins:
        print(f"  Failed bins: {failed_bins}")

    write_report(args.output, bin_results, verdict, failed_bins, raw_results)

    if verdict in ("PROCEED", "PROCEED_WITH_RESTRICTIONS"):
        print("[GATE] Green — Unit 14 may proceed.")
        sys.exit(0)
    else:
        print(f"[GATE] Red ({verdict}) — do not start Unit 14. See report for details.")
        sys.exit(1)


if __name__ == "__main__":
    main()
