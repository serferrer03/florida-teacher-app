import React, { useCallback, useEffect, useState } from 'react'
import { api, ApiError } from './api.js'

// Tareas agrupadas por alumno. PRIVACIDAD: los datos solo viven en esta pantalla.
function mark(t) {
  if (!t) return { icon: '·', cls: 'na', label: 'No aplica' }
  if (t.submitted) return t.late ? { icon: '⏰', cls: 'late', label: 'Entregada con retraso' } : { icon: '✅', cls: 'ok', label: 'Entregada' }
  return { icon: '❌', cls: 'no', label: 'No entregada' }
}

export function StudentsView({ course, onNeedLogin }) {
  const [data, setData] = useState(null)
  const [error, setError] = useState('')
  const [q, setQ] = useState('')
  const [onlyPending, setOnlyPending] = useState(false)
  const [open, setOpen] = useState(null)

  const load = useCallback(async () => {
    setError(''); setData(null)
    try { setData(await api.studentsOverview(course.id)) } catch (err) {
      if (err instanceof ApiError && err.status === 409) onNeedLogin(err.message)
      else setError(err.message)
    }
  }, [course.id, onNeedLogin])
  useEffect(() => { load(); return () => setData(null) }, [load])

  if (error) return <p className="error" role="alert">{error}</p>
  if (!data) return <p className="spinner">Consultando todas las tareas del curso… puede tardar un poco.</p>
  if (!data.assignments.length) return <p className="muted">Este curso no tiene tareas.</p>

  const total = data.assignments.length
  const rows = data.students.map((s) => ({
    ...s, done: data.assignments.filter((a) => s.tasks[a.cmid]?.submitted).length,
  })).filter((s) => (!q || s.name.toLowerCase().includes(q.toLowerCase())) && (!onlyPending || s.done < total))

  return (
    <section>
      <div className="toolbar">
        <p className="muted">{data.students.length} alumnos · {total} tareas · ✅ entregada · ⏰ con retraso · ❌ sin entregar</p>
        <button className="secondary" onClick={load}>Recargar</button>
      </div>
      <div className="row">
        <input className="search grow" placeholder="Buscar alumno…" value={q} onChange={(e) => setQ(e.target.value)} />
        <label className="check chip"><input type="checkbox" checked={onlyPending} onChange={(e) => setOnlyPending(e.target.checked)} /><span>Solo con tareas pendientes</span></label>
      </div>
      <div className="matrix-wrap">
        <table className="matrix">
          <thead><tr><th>Alumno</th><th>Entregadas</th>{data.assignments.map((a) => <th key={a.cmid} title={a.name}><span>{a.name}</span></th>)}</tr></thead>
          <tbody>
            {rows.map((s) => (
              <React.Fragment key={s.userid}>
                <tr className={open === s.userid ? 'open' : ''} onClick={() => setOpen(open === s.userid ? null : s.userid)}>
                  <th scope="row">{s.name}</th>
                  <td className={s.done === total ? 'ok' : 'pending'}>{s.done}/{total}</td>
                  {data.assignments.map((a) => {
                    const m = mark(s.tasks[a.cmid])
                    return <td key={a.cmid} className={m.cls} title={`${a.name}: ${m.label}`}>{m.icon}</td>
                  })}
                </tr>
                {open === s.userid && (
                  <tr className="detail"><td colSpan={total + 2}>
                    <ul className="files">
                      {data.assignments.map((a) => {
                        const t = s.tasks[a.cmid]; const m = mark(t)
                        return <li key={a.cmid}>{m.icon} <strong>{a.name}</strong> — {m.label}{t?.grade && /\d/.test(t.grade.split('/')[0]) ? ` · Nota: ${t.grade}` : ''}</li>
                      })}
                    </ul>
                  </td></tr>
                )}
              </React.Fragment>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  )
}
