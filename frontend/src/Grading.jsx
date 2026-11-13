import React, { useCallback, useEffect, useState } from 'react'
import { api, ApiError } from './api.js'

// PRIVACIDAD: los datos del alumnado solo viven en la memoria de esta pantalla.
const FILTERS = {
  all: ['Todos', () => true],
  submitted: ['Entregados', (s) => s.submitted],
  pending: ['Sin entregar', (s) => !s.submitted],
  late: ['Con retraso', (s) => s.late],
  ungraded: ['Entregados sin nota', (s) => s.submitted && !/\d/.test(s.grade.split('/')[0])],
}

function GradeBox({ course, cmid, s, onSaved, fail }) {
  const [grade, setGrade] = useState('')
  const [feedback, setFeedback] = useState('')
  const [notify, setNotify] = useState(true)
  const [busy, setBusy] = useState(false)

  async function save(e) {
    e.preventDefault()
    const g = grade.trim() === '' ? null : Number(grade.replace(',', '.'))
    if (g !== null && (Number.isNaN(g) || g < 0)) { window.alert('Nota no válida'); return }
    if (g === null && !feedback.trim()) { window.alert('Escribe una nota o un comentario'); return }
    const what = [g !== null && `nota ${g}`, feedback.trim() && 'comentario'].filter(Boolean).join(' y ')
    if (!window.confirm(`¿Guardar ${what} para ${s.name}${notify ? ' y avisarle' : ''}?`)) return
    setBusy(true)
    try {
      await api.grade(course.id, cmid, { userid: s.userid, grade: g, feedback: feedback.trim() || null, notify })
      setGrade(''); setFeedback(''); onSaved()
    } catch (err) { fail(err) } finally { setBusy(false) }
  }

  return (
    <form className="gradebox" onSubmit={save}>
      <label>Nota<input inputMode="decimal" value={grade} onChange={(e) => setGrade(e.target.value)} placeholder="p. ej. 7,5" /></label>
      <label className="grow">Comentario<textarea rows={2} value={feedback} onChange={(e) => setFeedback(e.target.value)} /></label>
      <label className="check"><input type="checkbox" checked={notify} onChange={(e) => setNotify(e.target.checked)} /><span>Notificar</span></label>
      <button type="submit" disabled={busy}>{busy ? 'Guardando…' : 'Guardar'}</button>
    </form>
  )
}

function SubmissionsList({ course, assign, onBack, onNeedLogin }) {
  const [data, setData] = useState(null)
  const [error, setError] = useState('')
  const [filter, setFilter] = useState('all')
  const [q, setQ] = useState('')
  const [open, setOpen] = useState(null)

  const fail = useCallback((err) => {
    if (err instanceof ApiError && err.status === 409) onNeedLogin(err.message)
    else setError(err.message)
  }, [onNeedLogin])
  const load = useCallback(async () => {
    setError('')
    try { setData(await api.submissions(course.id, assign.cmid)) } catch (err) { fail(err) }
  }, [course.id, assign.cmid, fail])
  useEffect(() => { load(); return () => setData(null) }, [load])

  const rows = (data?.submissions || []).filter(FILTERS[filter][1])
    .filter((s) => !q || s.name.toLowerCase().includes(q.toLowerCase()))

  return (
    <section>
      <button className="link" onClick={onBack}>← Tareas del curso</button>
      <div className="toolbar">
        <h3>{assign.name}</h3>
        <button className="secondary" onClick={load}>Recargar</button>
      </div>
      {error && <p className="error" role="alert">{error}</p>}
      {!data && !error && <p className="spinner">Consultando entregas en Florida Oberta…</p>}
      {data && (
        <>
          <p className="muted">{data.counts.total} participantes · {data.counts.submitted} entregados · {data.counts.late} con retraso</p>
          <div className="chips">
            {Object.entries(FILTERS).map(([k, [label]]) => (
              <button key={k} className={filter === k ? 'tab active' : 'tab'} onClick={() => setFilter(k)}>{label}</button>
            ))}
          </div>
          {data.counts.total > 8 && <input className="search" placeholder="Buscar alumno…" value={q} onChange={(e) => setQ(e.target.value)} />}
          <ul className="subs">
            {rows.map((s) => (
              <li key={s.userid}>
                <button className="sub-head" onClick={() => setOpen(open === s.userid ? null : s.userid)} aria-expanded={open === s.userid}>
                  <span className="sub-name">{s.name}</span>
                  <span className={`badge${s.submitted ? ' ok' : ''}${s.late ? ' warn' : ''}`}>{s.status.join(' · ') || '—'}</span>
                  <span className="sub-grade">{s.grade || '—'}</span>
                </button>
                {open === s.userid && (
                  <div className="sub-body">
                    {s.modified && <p className="muted small">Última modificación: {s.modified}</p>}
                    {s.files.length > 0 && (
                      <div className="row">{s.files.map((f) => (
                        <button key={f.url} className="secondary" onClick={() => api.downloadFile(course.id, assign.cmid, f).catch(fail)}>⬇ {f.name}</button>
                      ))}</div>
                    )}
                    {s.onlinetext && <blockquote className="onlinetext">{s.onlinetext}</blockquote>}
                    {s.feedback && <p className="small"><strong>Comentario actual:</strong> {s.feedback}</p>}
                    <GradeBox course={course} cmid={assign.cmid} s={s} fail={fail} onSaved={load} />
                  </div>
                )}
              </li>
            ))}
          </ul>
          {rows.length === 0 && <p className="muted">Nadie en este filtro.</p>}
        </>
      )}
    </section>
  )
}

export function GradingView({ course, onNeedLogin }) {
  const [assigns, setAssigns] = useState(null)
  const [current, setCurrent] = useState(null)
  const [error, setError] = useState('')
  useEffect(() => {
    api.contents(course.id)
      .then((d) => setAssigns(d.sections.flatMap((s) => s.items.filter((i) => i.modname === 'assign').map((i) => ({ ...i, section: s.name })))))
      .catch((err) => (err instanceof ApiError && err.status === 409 ? onNeedLogin(err.message) : setError(err.message)))
  }, [course.id, onNeedLogin])

  if (current) return <SubmissionsList course={course} assign={current} onBack={() => setCurrent(null)} onNeedLogin={onNeedLogin} />
  if (error) return <p className="error" role="alert">{error}</p>
  if (!assigns) return <p className="spinner">Buscando tareas del curso…</p>
  if (!assigns.length) return <p className="muted">Este curso no tiene tareas.</p>
  return (
    <>
      <p className="muted small">Los datos del alumnado se consultan al momento y no se guardan en el PC ni en la tablet.</p>
      <ul className="courses">
        {assigns.map((a) => (
          <li key={a.cmid} className="course">
            <a href={a.url} onClick={(e) => { e.preventDefault(); setCurrent(a) }}>
              <span className="course-name">{a.name}</span>
              <span className="course-meta">{a.section}{a.visible ? '' : ' · oculta'}</span>
            </a>
          </li>
        ))}
      </ul>
    </>
  )
}
