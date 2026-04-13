/**
 * Module-level cache for resolved feature flags.
 *
 * Exists so low-level modules (e.g. `apiFetch`) can read the current flag
 * state without pulling in React context. `FeaturesProvider` calls
 * `setAuthRequired` once the backend response lands.
 *
 * Default is `true` (prod-safe) — guest-token provisioning stays off until
 * the backend explicitly reports `auth_required=false`.
 */

let authRequired = true;

export function setAuthRequired(value: boolean): void {
  authRequired = value;
}

export function getAuthRequired(): boolean {
  return authRequired;
}
