/**
 * Identity helper for the current session.
 *
 * `GET /v1/users/me` mirrors `app.api.users.MeResponse` — it returns the
 * username/display_name/avatar of whoever is on the wire (JWT user or guest
 * token). Mobile uses this after guest provisioning so screens like
 * profile.tsx know which `/v1/users/{username}/profile` to load.
 */
import { apiFetch } from "./api";
import { PROFILE_ENDPOINTS } from "../constants/config";

export interface MeResponse {
  username: string;
  display_name: string;
  avatar_url: string | null;
  /**
   * ISO timestamp when the user granted face-mod consent, or null if
   * they haven't. `ConsentProvider` hydrates its `hasConsent` from
   * this on app boot so the client's cached state never drifts from
   * the server's — if it did, the analyze endpoint would 428 and the
   * Analyze button would appear to do nothing.
   */
  face_mod_consent_at: string | null;
}

export function fetchMe(): Promise<MeResponse> {
  return apiFetch<MeResponse>(PROFILE_ENDPOINTS.ME);
}
