/**
 * Shared auth types used across login and signup screens.
 */

export interface LoginResponse {
  access_token: string;
  refresh_token: string;
  user_id: string;
  expires_at: number;
}
