# NXME Mobile ↔ Backend Wiring Audit
**Date:** 2026-03-23

## Critical (Breaking Functionality)

### 1. Analysis Response Shape Mismatch
- **Mobile expects:** `{ id, status, face_validation: { passed, error_code } }`
- **Backend sends:** `{ analysis_id, face_shape, symmetry_score, recommendations }` — NO `face_validation` field
- **Impact:** Mobile cannot detect face validation errors
- **Fix:** Either add face_validation to backend response OR update mobile types to match backend

### 2. Job Status Response Field Mismatches
- **Mobile:** `before_url` → **Backend:** `before_image_url`
- **Mobile:** `after_url` → **Backend:** `after_image_url`
- **Mobile:** `error_message` → **Backend:** `failure_reason`
- **Mobile:** expects `suggestions` → **Backend:** doesn't send it
- **Mobile:** `id` → **Backend:** `job_id`
- **Impact:** Result screen cannot display images
- **Fix:** Update mobile types to match backend field names

### 3. Token Refresh Endpoint Missing
- **Mobile calls:** POST /v1/auth/refresh
- **Backend:** Endpoint doesn't exist
- **Impact:** Sessions can never be extended
- **Fix:** Add refresh endpoint to backend

## High Priority

### 4. Feed Doesn't Filter Blocked Users Server-Side
- Mobile removes blocked posts locally but feed API doesn't exclude them
- **Impact:** Blocked posts reappear on refresh
- **Fix:** Backend feed query should exclude posts from blocked users

### 5. No Profile History Auto-Refresh
- After creating a post, user must manually refresh to see it
- **Fix:** Navigate to profile after post creation, trigger refresh

### 6. Rate Limiting Headers Not Parsed
- Backend returns Retry-After on 429, mobile ignores it
- **Fix:** Parse header and show countdown

## Medium

### 7. 402 Payment Required Handling
- Backend returns 402 for insufficient entitlements
- Mobile doesn't clearly distinguish "upgrade needed" from "error"
- **Fix:** Show PaywallModal on 402

### 8. Post Refund Endpoint Missing
- Mobile references POST /v1/jobs/{id}/refund but backend doesn't have it
- **Fix:** Add to backend or remove refund UI

## Aligned (Working Correctly)
- Auth register/login/logout ✅
- Feed endpoint paths ✅
- Comment create/list ✅
- Block/unblock ✅
- Profile/history ✅
- Entitlement ✅
- Navigation routes ✅
