// Cliente de la API FastAPI. Mismo origen (o proxy de Vite en desarrollo).
const TOKEN_KEY = 'fta.token'

export function getToken() {
  try { return localStorage.getItem(TOKEN_KEY) || '' } catch { return '' }
}
export function setToken(value) {
  try { localStorage.setItem(TOKEN_KEY, value) } catch { /* sin almacenamiento */ }
}

export class ApiError extends Error {
  constructor(status, message) { super(message); this.status = status }
}

async function request(method, path, body) {
  const headers = { 'Content-Type': 'application/json' }
  const token = getToken()
  if (token) headers['X-App-Token'] = token
  let res
  try {
    res = await fetch(path, { method, headers, body: body ? JSON.stringify(body) : undefined })
  } catch {
    throw new ApiError(0, 'No se puede contactar con el PC. ¿Está encendido el servidor y estás en la misma red?')
  }
  const data = await res.json().catch(() => ({}))
  if (!res.ok) throw new ApiError(res.status, data.detail || `Error ${res.status}`)
  return data
}

export const api = {
  status: () => request('GET', '/api/status'),
  saveCredentials: (username, password) => request('PUT', '/api/credentials', { username, password }),
  deleteCredentials: () => request('DELETE', '/api/credentials'),
  testLogin: () => request('POST', '/api/login/test'),
  courses: () => request('GET', '/api/courses'),
  syncCourses: () => request('POST', '/api/courses/sync'),
}
