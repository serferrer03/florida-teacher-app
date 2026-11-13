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
  const headers = { 'X-App-Token': getToken() }
  const isForm = body instanceof FormData
  if (body && !isForm) headers['Content-Type'] = 'application/json'
  let res
  try {
    res = await fetch(path, { method, headers, body: body ? (isForm ? body : JSON.stringify(body)) : undefined, cache: 'no-store' })
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
  assignOptions: (courseId, refresh = false) =>
    request('GET', `/api/courses/${courseId}/assign-options${refresh ? '?refresh=true' : ''}`),
  contents: (courseId) => request('GET', `/api/courses/${courseId}/contents`),
  setVisibility: (courseId, kind, id, visible) => request('POST', `/api/courses/${courseId}/visibility`, { kind, id, visible }),
  rename: (courseId, kind, id, name) => request('POST', `/api/courses/${courseId}/rename`, { kind, id, name }),
  addResource: (courseId, data, files) => {
    const fd = new FormData()
    fd.append('data', JSON.stringify(data))
    files.forEach((f) => fd.append('files', f, f.name))
    return request('POST', `/api/courses/${courseId}/resources`, fd)
  },
  submissions: (courseId, cmid) => request('GET', `/api/courses/${courseId}/assign/${cmid}/submissions`),
  grade: (courseId, cmid, body) => request('POST', `/api/courses/${courseId}/assign/${cmid}/grade`, body),
  // Descarga a través del PC (sin guardarla allí): se abre en la tablet desde memoria
  downloadFile: async (courseId, cmid, file) => {
    let res
    try {
      res = await fetch(`/api/courses/${courseId}/assign/${cmid}/file?url=${encodeURIComponent(file.url)}`,
        { headers: { 'X-App-Token': getToken() }, cache: 'no-store' })
    } catch { throw new ApiError(0, 'No se puede contactar con el PC') }
    if (!res.ok) {
      const data = await res.json().catch(() => ({}))
      throw new ApiError(res.status, data.detail || `Error ${res.status}`)
    }
    const url = URL.createObjectURL(await res.blob())
    const a = document.createElement('a'); a.href = url; a.download = file.name; a.click()
    setTimeout(() => URL.revokeObjectURL(url), 60000)
  },
  connection: () => request('GET', '/api/connection'),
  rotateCode: () => request('POST', '/api/access/rotate'),
  restoreBackup: (data) => request('POST', '/api/backup', data),
  templates: () => request('GET', '/api/templates'),
  saveTemplate: (name, data) => request('POST', '/api/templates', { name, data }),
  deleteTemplate: (id) => request('DELETE', `/api/templates/${id}`),
  calendar: (year, month) => request('GET', `/api/calendar?year=${year}&month=${month}`),
  assignments: (courseId) => request('GET', `/api/courses/${courseId}/assignments`),
  createAssignment: (courseId, data, files) => {
    const fd = new FormData()
    fd.append('data', JSON.stringify(data))
    files.forEach((f) => fd.append('files', f, f.name))
    return request('POST', `/api/courses/${courseId}/assignments`, fd)
  },
  deleteAll: () => request('DELETE', '/api/data'),
}
