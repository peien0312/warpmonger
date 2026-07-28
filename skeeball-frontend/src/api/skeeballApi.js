// [HOST-INTEGRATION] This module is the ONLY place the frontend talks to the
// backend. The host must serve these endpoints (same request/response shapes)
// or edit this file to match the host API. Auth is cookie-based
// (credentials: 'include') — see INTEGRATION.md for the full endpoint contract.
const BASE = '/api/skeeball/session'

async function post(path, body) {
  const res = await fetch(`${BASE}${path}`, {
    method: 'POST',
    headers: body ? { 'Content-Type': 'application/json' } : undefined,
    credentials: 'include',
    body: body ? JSON.stringify(body) : undefined,
  })
  let data = null
  try {
    data = await res.json()
  } catch {
    // Non-JSON response (proxy error page, etc.) — treated as failure below.
  }
  if (!res.ok) {
    const err = new Error(data?.error || `request_failed_${res.status}`)
    err.status = res.status
    err.code = data?.error || null
    throw err
  }
  return data
}

/** → { sessionId, nonce, maxBalls, expiresAt }; throws with .code e.g. 'insufficient_tokens'. */
export function startSession() {
  return post('/start')
}

/** → { accepted, ballsThrown, maxBalls } */
export function postRoll(sessionId, { rollIndex, pinsHit, score, nonce, clientTs }) {
  return post(`/${sessionId}/roll`, { rollIndex, pinsHit, score, nonce, clientTs })
}

/** → { totalScore, ticketsAwarded, ticketBalance } */
export function completeSession(sessionId) {
  return post(`/${sessionId}/complete`)
}

/** Admin: save level config. Throws with .status/.code on failure. */
export async function putLevel(level, adminKey) {
  const res = await fetch('/api/skeeball/admin/config/level', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json', 'x-admin-key': adminKey },
    credentials: 'include',
    body: JSON.stringify(level),
  })
  let data = null
  try {
    data = await res.json()
  } catch {
    // Non-JSON response — treated as failure below.
  }
  if (!res.ok) {
    const err = new Error(data?.error || data?.message || `request_failed_${res.status}`)
    err.status = res.status
    err.code = data?.error || null
    throw err
  }
  return data
}

// Ticket-booth endpoints (getPrizes/redeem) were removed in the abbeystoys
// integration — prizes are granted directly on session complete.

