/** Shared Pro upsell benefits — referenced by paywall/PremiumCard and subscription/PremiumUpsell. */
import {
  PRO_MONTHLY_ADA_APPROX,
  PRO_MONTHLY_GLOWUPS,
} from "./pricing";

export const PREMIUM_BENEFITS = [
  `${PRO_MONTHLY_GLOWUPS} glow-ups every month`,
  `About ${PRO_MONTHLY_ADA_APPROX} Ada advisor messages from the same pool`,
  "Priority processing",
] as const;
