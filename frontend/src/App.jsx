import React, { useCallback, useEffect, useRef, useState } from 'react'
import { api, ApiError, clearToken, getToken, setToken } from './api.js'
import { CourseDetail } from './Assignments.jsx'
import { CalendarView } from './Calendar.jsx'

function formatDate(iso) {
  if (!iso) return 'nunca'
  return new Date(iso).toLocaleString('es-ES', { dateStyle: 'medium', timeStyle: 'short' })
}

// ------------------------------------------------------------ código de acceso
function TokenForm({ onDone, failed }) {
  const [value, setValue] = useState('')
  return (
    <form className="card" onSubmit={(e) => { e.preventDefault(); setToken(value.trim().toUpperCase()); onDone() }}>
      <h2>Vincular esta tablet</h2>
      <p className="muted">
        Escribe el código de acceso que aparece en la consola del PC al arrancar el servidor
        (también está en <code>backend/data/access_code</code>). Solo hace falta una vez.
      </p>
      {failed && <p className="error" role="alert">Código incorrecto.</p>}
      <label>Código de acceso
        <input value={value} onChange={(e) => setValue(e.target.value)} autoFocus
          autoCapitalize="characters" autoComplete="off" spellCheck="false" required />
      </label>
      <button type="submit">Vincular</button>
    </form>
  )
}

// ------------------------------------------------------- conexión Microsoft
function ConnectForm({ status, reason, onStarted, onCancel }) {
  const [username, setUsername] = useState(status.username || '')
  const [password, setPassword] = useState('')
  const [remember, setRemember] = useState(status.password_remembered)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const canReuse = status.password_remembered && username === status.username

  async function start(manual) {
    setBusy(true); setError('')
    try {
      await api.loginStart({ username: username.trim(), password: password || null, remember_password: remember, manual })
      setPassword('')
      onStarted()
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <form className="card" onSubmit={(e) => { e.preventDefault(); start(false) }}>
      <h2>Conectar con Florida Oberta</h2>
      {reason && <p className="error" role="alert">{reason}</p>}
      <p className="muted">
        Inicia sesión con tu cuenta de Microsoft (Office 365) de Florida. Si te pide verificación
        en dos pasos, aquí verás el número o podrás escribir el código.
      </p>
      <label>Correo institucional
        <input type="email" value={username} onChange={(e) => setUsername(e.target.value)}
          autoComplete="username" autoCapitalize="none" required />
      </label>
      <label>Contraseña
        <input type="password" value={password} onChange={(e) => setPassword(e.target.value)}
          autoComplete="current-password" required={!canReuse}
          placeholder={canReuse ? 'Recordada (déjala vacía para usarla)' : ''} />
      </label>
      <label className="check">
        <input type="checkbox" checked={remember} onChange={(e) => setRemember(e.target.checked)} />
        <span>Recordar contraseña en el PC (cifrada). Si no la recuerdas, la pediré cuando caduque la sesión.</span>
      </label>
      {error && <p className="error" role="alert">{error}</p>}
      <div className="row">
        <button type="submit" disabled={busy}>{busy ? 'Iniciando…' : 'Conectar'}</button>
        {onCancel && <button type="button" className="secondary" onClick={onCancel} disabled={busy}>Cancelar</button>}
      </div>
      <details>
        <summary>¿Tu cuenta usa otro método o falla?</summary>
        <p className="muted">
          Puedes iniciar sesión tú mismo en una ventana del navegador que se abrirá en el PC
          (requiere <code>MOODLE_HEADLESS=false</code> y estar delante del PC).
        </p>
        <button type="button" className="secondary" disabled={busy} onClick={() => start(true)}>
          Iniciar sesión manualmente en el PC
        </button>
      </details>
      <p className="muted small">
        Tus datos se quedan en tu PC, cifrados, y solo se envían a Florida Oberta y Microsoft.
        Consulta la pestaña Privacidad.
      </p>
    </form>
  )
}

function LoginProgress({ onFinished }) {
  const [job, setJob] = useState(null)
  const [code, setCode] = useState('')
  const [error, setError] = useState('')
  const timer = useRef(null)

  useEffect(() => {
    let alive = true
    async function poll() {
      try {
        const s = await api.loginStatus()
        if (!alive) return
        setJob(s)
        if (['success', 'error', 'cancelled', 'idle'].includes(s.state)) {
          if (s.state === 'success') onFinished(true)
          return
        }
      } catch (err) {
        if (alive) setError(err.message)
      }
      timer.current = setTimeout(poll, 1200)
    }
    poll()
    return () => { alive = false; clearTimeout(timer.current) }
  }, [onFinished])

  async function sendCode(e) {
    e.preventDefault()
    try { setJob(await api.loginCode(code.trim())); setCode('') } catch (err) { setError(err.message) }
  }

  const state = job?.state
  return (
    <div className="card" aria-live="polite">
      <h2>Iniciando sesión</h2>
      {state === 'mfa_number' && (
        <>
          <p>Abre <strong>Microsoft Authenticator</strong> en tu móvil y escribe este número:</p>
          <p className="big-number">{job.number}</p>
        </>
      )}
      {state === 'mfa_push' && <p>Aprueba la solicitud en <strong>Microsoft Authenticator</strong> en tu móvil.</p>}
      {state === 'mfa_code' && (
        <form onSubmit={sendCode} className="grid">
          <label>Código de verificación
            <input inputMode="numeric" autoComplete="one-time-code" value={code}
              onChange={(e) => setCode(e.target.value)} autoFocus required />
          </label>
          <button type="submit">Enviar código</button>
        </form>
      )}
      {(!state || state === 'working' || state === 'manual') && <p className="spinner">{job?.message || 'Conectando…'}</p>}
      {state === 'error' && <p className="error" role="alert">{job.message}</p>}
      {state === 'cancelled' && <p className="muted">{job.message}</p>}
      {error && <p className="error">{error}</p>}
      <div className="row">
        {['error', 'cancelled', 'idle'].includes(state)
          ? <button onClick={() => onFinished(false)}>Volver</button>
          : <button className="secondary" onClick={() => api.loginCancel().catch(() => {})}>Cancelar</button>}
      </div>
    </div>
  )
}

// ------------------------------------------------------------------ cursos
function Courses({ status, onNeedLogin, onOpen }) {
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
      if (err instanceof ApiError && err.status === 409) onNeedLogin(err.message)
      else setError(err.message)
    } finally {
      setBusy(false)
    }
  }, [onNeedLogin])

  useEffect(() => {
    const loginError = status.login?.result?.courses_error
    if (loginError) setError(`Sesión iniciada, pero no se pudieron descargar los cursos: ${loginError}`)
    api.courses().then((data) => {
      setCourses(data.courses); setSyncedAt(data.synced_at)
      if (data.courses.length === 0 && !loginError) sync()  // primera vez o lista vacía: intentar
    }).catch((err) => setError(err.message))
  }, [])  // eslint-disable-line react-hooks/exhaustive-deps

  const q = filter.trim().toLowerCase()
  const visible = q
    ? courses.filter((c) => `${c.fullname} ${c.shortname || ''} ${c.category || ''}`.toLowerCase().includes(q))
    : courses

  return (
    <section>
      <div className="toolbar">
        <div>
          <h2>Mis cursos</h2>
          <p className="muted">{status.username || 'Florida Oberta'} · Actualizado: {formatDate(syncedAt)}</p>
        </div>
        <button onClick={sync} disabled={busy}>{busy ? 'Sincronizando…' : 'Actualizar'}</button>
      </div>
      {error && <p className="error" role="alert">{error}</p>}
      {courses.length > 5 && (
        <input className="search" placeholder="Buscar curso…" value={filter}
          onChange={(e) => setFilter(e.target.value)} />
      )}
      {busy && courses.length === 0 && <p className="spinner">Descargando tus cursos de Florida Oberta…</p>}
      {!busy && courses.length === 0 && !error && (
        <p className="muted">
          {syncedAt
            ? 'Florida Oberta no devolvió ningún curso. Pulsa «Actualizar»; si sigue vacío, copia las líneas «Cursos vía…» de la consola del PC.'
            : 'No hay cursos todavía. Pulsa «Actualizar».'}
        </p>
      )}
      <ul className="courses">
        {visible.map((c) => (
          <li key={c.id} className="course">
            <a href={c.url} onClick={(e) => { e.preventDefault(); onOpen(c) }}>
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

// -------------------------------------------------------------- privacidad
function Privacy({ onChanged }) {
  const [info, setInfo] = useState(null)
  const [error, setError] = useState('')
  const load = useCallback(() => api.privacy().then(setInfo).catch((e) => setError(e.message)), [])
  useEffect(() => { load() }, [load])

  async function logout() {
    if (!window.confirm('¿Cerrar sesión? Se borran las cookies y la contraseña recordada del PC.')) return
    await api.logout().catch((e) => setError(e.message)); load(); onChanged()
  }
  async function wipe() {
    if (!window.confirm('¿Borrar TODOS los datos de la app en el PC? Se destruye también la clave de cifrado. No se puede deshacer.')) return
    await api.deleteAll().catch((e) => setError(e.message)); load(); onChanged()
  }
  function unlink() {
    if (!window.confirm('¿Desvincular esta tablet? Tendrás que volver a escribir el código de acceso.')) return
    clearToken(); window.location.reload()
  }

  return (
    <section className="privacy">
      <h2>Privacidad y datos</h2>
      <p className="muted">
        La app funciona solo en tu PC y tu red local. No usa servidores propios, analítica ni
        terceros: solo se conecta a Florida Oberta y a Microsoft, igual que tu navegador.
      </p>
      {error && <p className="error">{error}</p>}
      {info && (
        <>
          <table>
            <thead><tr><th>Dato</th><th>¿Guardado?</th><th>Protección</th></tr></thead>
            <tbody>
              {info.items.map((i) => (
                <tr key={i.what}>
                  <td>{i.what}{i.detail && <div className="muted small">{i.detail}</div>}</td>
                  <td>{i.stored ? 'Sí' : 'No'}</td>
                  <td>{i.protection}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <h3>No se guarda</h3>
          <ul>{info.not_stored.map((t) => <li key={t}>{t}</li>)}</ul>
          <p className="muted small">Ubicación en el PC: <code>{info.location}</code></p>
        </>
      )}
      <div className="row">
        <button className="secondary" onClick={logout}>Cerrar sesión</button>
        <button className="secondary" onClick={unlink}>Desvincular esta tablet</button>
        <button className="secondary danger" onClick={wipe}>Borrar todos mis datos</button>
      </div>
    </section>
  )
}

// --------------------------------------------------------------------- app
export default function App() {
  const [status, setStatus] = useState(null)
  const [error, setError] = useState('')
  const [token, setTokenState] = useState({ need: false, failed: false })
  const [view, setView] = useState('courses')
  const [course, setCourse] = useState(null)
  const [connect, setConnect] = useState({ open: false, reason: '' })
  const [loggingIn, setLoggingIn] = useState(false)

  const load = useCallback(async () => {
    setError('')
    try {
      const s = await api.status()
      setStatus(s); setTokenState({ need: false, failed: false })
      if (s.login && !['success', 'error', 'cancelled'].includes(s.login.state)) setLoggingIn(true)
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) setTokenState({ need: true, failed: Boolean(getToken()) })
      else setError(err.message)
    }
  }, [])

  useEffect(() => { load() }, [load])

  const onLoginFinished = useCallback((ok) => {
    setLoggingIn(false)
    if (ok) setConnect({ open: false, reason: '' })
    load()
  }, [load])
  const onNeedLogin = useCallback((reason) => setConnect({ open: true, reason }), [])

  let body
  if (token.need) body = <TokenForm onDone={load} failed={token.failed} />
  else if (error) body = <div className="card"><p className="error">{error}</p><button onClick={load}>Reintentar</button></div>
  else if (!status) body = <p className="muted">Cargando…</p>
  else if (!status.moodle_base_url) body = (
    <div className="card"><h2>Falta configuración</h2>
      <p>Define <code>MOODLE_BASE_URL</code> en <code>backend/.env</code> y reinicia el servidor.</p></div>
  )
  else if (view === 'privacy') body = <Privacy onChanged={load} />
  else if (view === 'calendar' && status.has_session && !loggingIn && !connect.open) body = <CalendarView onNeedLogin={onNeedLogin} />
  else if (loggingIn) body = <LoginProgress onFinished={onLoginFinished} />
  else if (!status.has_session || connect.open) body = (
    <ConnectForm status={status} reason={connect.reason}
      onStarted={() => setLoggingIn(true)}
      onCancel={status.has_session ? () => setConnect({ open: false, reason: '' }) : null} />
  )
  else if (course) body = <CourseDetail course={course} onBack={() => setCourse(null)} onNeedLogin={onNeedLogin} />
  else body = <Courses status={status} onNeedLogin={onNeedLogin} onOpen={setCourse} />

  return (
    <div className="app">
      <header className="topbar">
        <h1>Florida Teacher App <span className="version">v{__APP_VERSION__}</span></h1>
        {status && !token.need && (
          <nav className="tabs">
            <button className={view === 'courses' ? 'tab active' : 'tab'} onClick={() => { setView('courses'); setCourse(null) }}>Cursos</button>
            <button className={view === 'calendar' ? 'tab active' : 'tab'} onClick={() => setView('calendar')}>Calendario</button>
            <button className={view === 'privacy' ? 'tab active' : 'tab'} onClick={() => setView('privacy')}>Privacidad</button>
            {status.has_session && view === 'courses' && !loggingIn && (
              <button className="tab" onClick={() => setConnect({ open: true, reason: '' })}>Cuenta</button>
            )}
          </nav>
        )}
      </header>
      <main>{body}</main>
    </div>
  )
}
