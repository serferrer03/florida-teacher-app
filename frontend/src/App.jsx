import React, { useCallback, useEffect, useState } from 'react'
import { api, ApiError, getToken, setToken } from './api.js'

function formatDate(iso) {
  if (!iso) return 'nunca'
  return new Date(iso).toLocaleString('es-ES', { dateStyle: 'medium', timeStyle: 'short' })
}

function TokenForm({ onDone }) {
  const [value, setValue] = useState(getToken())
  return (
    <form className="card" onSubmit={(e) => { e.preventDefault(); setToken(value.trim()); onDone() }}>
      <h2>Código de acceso</h2>
      <p className="muted">El servidor del PC pide un código (APP_ACCESS_TOKEN en backend/.env).</p>
      <label>Código
        <input type="password" value={value} onChange={(e) => setValue(e.target.value)} autoFocus />
      </label>
      <button type="submit">Continuar</button>
    </form>
  )
}

function CredentialsForm({ initialUser, onSaved, onCancel }) {
  const [username, setUsername] = useState(initialUser || '')
  const [password, setPassword] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  async function submit(e) {
    e.preventDefault()
    setBusy(true); setError('')
    try {
      await api.saveCredentials(username, password)
      setPassword('')
      onSaved()
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <form className="card" onSubmit={submit}>
      <h2>Conectar con Florida Oberta</h2>
      <p className="muted">
        Tus credenciales se comprueban iniciando sesión en Moodle y se guardan cifradas
        solo en tu PC. Nunca salen de tu red local salvo hacia Florida Oberta.
      </p>
      <label>Usuario
        <input value={username} onChange={(e) => setUsername(e.target.value)}
          autoComplete="username" autoCapitalize="none" required />
      </label>
      <label>Contraseña
        <input type="password" value={password} onChange={(e) => setPassword(e.target.value)}
          autoComplete="current-password" required />
      </label>
      {error && <p className="error" role="alert">{error}</p>}
      <div className="row">
        <button type="submit" disabled={busy}>{busy ? 'Comprobando…' : 'Iniciar sesión y guardar'}</button>
        {onCancel && <button type="button" className="secondary" onClick={onCancel} disabled={busy}>Cancelar</button>}
      </div>
    </form>
  )
}

function Courses({ status, onEditCredentials, onLogout }) {
  const [courses, setCourses] = useState([])
  const [syncedAt, setSyncedAt] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [filter, setFilter] = useState('')

  const sync = useCallback(async () => {
    setBusy(true); setError('')
    try {
      const data = await api.syncCourses()
      setCourses(data.courses); setSyncedAt(data.synced_at)
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }, [])

  useEffect(() => {
    api.courses().then((data) => {
      setCourses(data.courses); setSyncedAt(data.synced_at)
      if (!data.synced_at) sync()
    }).catch((err) => setError(err.message))
  }, [sync])

  const q = filter.trim().toLowerCase()
  const visible = q
    ? courses.filter((c) => `${c.fullname} ${c.shortname || ''} ${c.category || ''}`.toLowerCase().includes(q))
    : courses

  return (
    <section>
      <div className="toolbar">
        <div>
          <h2>Mis cursos</h2>
          <p className="muted">Sesión: {status.username} · Actualizado: {formatDate(syncedAt)}</p>
        </div>
        <div className="row">
          <button onClick={sync} disabled={busy}>{busy ? 'Sincronizando…' : 'Actualizar'}</button>
          <button className="secondary" onClick={onEditCredentials}>Cambiar cuenta</button>
          <button className="secondary danger" onClick={onLogout}>Olvidar credenciales</button>
        </div>
      </div>
      {error && <p className="error" role="alert">{error}</p>}
      {courses.length > 5 && (
        <input className="search" placeholder="Buscar curso…" value={filter}
          onChange={(e) => setFilter(e.target.value)} />
      )}
      {!busy && courses.length === 0 && !error && <p className="muted">No hay cursos todavía.</p>}
      <ul className="courses">
        {visible.map((c) => (
          <li key={c.id} className="course">
            <a href={c.url} target="_blank" rel="noreferrer">
              <span className="course-name">{c.fullname}</span>
              <span className="course-meta">
                {[c.shortname, c.category].filter(Boolean).join(' · ') || `ID ${c.id}`}
              </span>
            </a>
          </li>
        ))}
      </ul>
    </section>
  )
}

export default function App() {
  const [status, setStatus] = useState(null)
  const [error, setError] = useState('')
  const [needToken, setNeedToken] = useState(false)
  const [editing, setEditing] = useState(false)

  const load = useCallback(async () => {
    setError('')
    try {
      setStatus(await api.status()); setNeedToken(false)
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) setNeedToken(true)
      else setError(err.message)
    }
  }, [])

  useEffect(() => { load() }, [load])

  async function logout() {
    if (!window.confirm('¿Borrar las credenciales y la sesión guardadas en el PC?')) return
    try { await api.deleteCredentials(); await load() } catch (err) { setError(err.message) }
  }

  let body
  if (needToken) body = <TokenForm onDone={load} />
  else if (error) body = <div className="card"><p className="error">{error}</p><button onClick={load}>Reintentar</button></div>
  else if (!status) body = <p className="muted">Cargando…</p>
  else if (!status.moodle_base_url) body = (
    <div className="card"><h2>Falta configuración</h2>
      <p>Define <code>MOODLE_BASE_URL</code> en <code>backend/.env</code> y reinicia el servidor.</p></div>
  )
  else if (!status.has_credentials || editing) body = (
    <CredentialsForm initialUser={status.username}
      onSaved={() => { setEditing(false); load() }}
      onCancel={status.has_credentials ? () => setEditing(false) : null} />
  )
  else body = <Courses status={status} onEditCredentials={() => setEditing(true)} onLogout={logout} />

  return (
    <div className="app">
      <header className="topbar">
        <h1>Florida Teacher App</h1>
        {status?.moodle_base_url && <span className="muted small">{new URL(status.moodle_base_url).host}</span>}
      </header>
      <main>{body}</main>
    </div>
  )
}
