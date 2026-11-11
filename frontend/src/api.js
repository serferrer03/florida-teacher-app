// Cliente de la API FastAPI. Mismo origen (o proxy de Vite en desarrollo).
const TOKEN_KEY = 'fta.token'

export function getToken() {
  try { return localStorage.getItem(TOKEN_KEY) || '' } catch { return '' }
}
export function setToken(value) {
  try { localStorage.setItem(TOKEN_KEY, value) } catch { /* sin almacenamiento */ }
}
export function clearToken() {
  try { localStorage.removeItem(TOKEN_KEY) } catch { /* sin almacenamiento */ }
}

export class ApiError extends Error {
  constructor(status, message) { super(message); this.status = status }
}

async function request(method, path, body) {
  const headers = { 'Content-Type': 'application/json', 'X-App-Token': getToken() }
  let res
  try {
    res = await fetch(path, { method, headers, body: body ? JSON.stringify(body) : undefined, cache: 'no-store' })
  } catch {
    throw new ApiError(0, 'No se puede contactar con el PC. ¿Está encendido el servidor y estás en la misma red?')
  }
  const data = await res.json().catch(() => ({}))
  if (!res.ok) {
    const detail = typeof data.detail === 'string' ? data.detail : `Error ${res.status}`
    throw new ApiError(res.status, detail)
  }
  return data
}

export const api = {
  status: () => request('GET', '/api/status'),
  loginStart: (body) => request('POST', '/api/login/start', body),
  loginStatus: () => request('GET', '/api/login/status'),
  loginCode: (code) => request('POST', '/api/login/code', { code }),
  loginCancel: () => request('POST', '/api/login/cancel'),
  logout: () => request('POST', '/api/logout'),
  courses: () => request('GET', '/api/courses'),
  syncCourses: () => request('POST', '/api/courses/sync'),
  privacy: () => request('GET', '/api/privacy'),
  deleteAll: () => request('DELETE', '/api/data'),
}
