/**
 * Client-side makeup preset definitions.
 *
 * Slugs match the backend YAML (prompts/makeup_presets.yaml).
 * The backend enforces MST blocklist and deprecation; the client shows all
 * non-deprecated presets by default and lets the server reject blocked ones.
 */
import type { MakeupIntensity } from "../lib/makeup";

export interface MakeupPresetDefinition {
  slug: string;
  displayName: string;
  description: string;
  defaultIntensity: MakeupIntensity;
  supportedIntensities: MakeupIntensity[];
}

export const MAKEUP_PRESETS: MakeupPresetDefinition[] = [
  {
    slug: "natural_glow",
    displayName: "Natural Glow",
    description: "Subtle enhancement, no-makeup look",
    defaultIntensity: "light",
    supportedIntensities: ["subtle", "light", "medium"],
  },
  {
    slug: "soft_glam",
    displayName: "Soft Glam",
    description: "Polished everyday look",
    defaultIntensity: "medium",
    supportedIntensities: ["subtle", "light", "medium", "bold"],
  },
  {
    slug: "bold_red",
    displayName: "Bold Red",
    description: "Statement red lip with defined eyes",
    defaultIntensity: "medium",
    supportedIntensities: ["light", "medium", "bold"],
  },
  {
    slug: "smoky_eye",
    displayName: "Smoky Eye",
    description: "Dramatic eye-focused look",
    defaultIntensity: "medium",
    supportedIntensities: ["subtle", "light", "medium", "bold"],
  },
  {
    slug: "bridal",
    displayName: "Bridal",
    description: "Timeless elegant finish",
    defaultIntensity: "medium",
    supportedIntensities: ["subtle", "light", "medium"],
  },
  {
    slug: "dramatic_night",
    displayName: "Dramatic Night",
    description: "High-impact evening look",
    defaultIntensity: "bold",
    supportedIntensities: ["medium", "bold"],
  },
  {
    slug: "groomed",
    displayName: "Groomed",
    description: "Clean, refined finish",
    defaultIntensity: "subtle",
    supportedIntensities: ["subtle", "light"],
  },
];

export const INTENSITY_LABELS: Record<MakeupIntensity, string> = {
  subtle: "Subtle",
  light: "Light",
  medium: "Medium",
  bold: "Bold",
};

export const ALL_INTENSITIES: MakeupIntensity[] = ["subtle", "light", "medium", "bold"];
