import React, { useCallback, useEffect, useState } from 'react'
import { api } from './api.js'

const STATE = {
  waiting: 'Programada: se evaluará al cerrarse la tarea',
  running: 'Evaluando entregas…',
  review: 'Evaluada: revisa las propuestas y publícalas',
  done: 'Todas las notas publicadas',
  error: 'Error',
}

function Ack({ onDone }) {
  const [ok, setOk] = useState(false)
  return (
    <div className="notice-box">
      <p><strong>Antes de activar la evaluación con IA</strong></p>
      <ul className="small">
        <li>El contenido de las entregas (sin el nombre del alumno) se envía a la API de Claude (Anthropic) para proponer nota y observación.</li>
        <li>Nombres, notas y observaciones se escriben en tu hoja de Google.</li>
        <li>Ninguna nota se publica en Florida Oberta sin que tú la revises (art. 22 RGPD; la Ley de IA de la UE considera de alto riesgo la evaluación con IA).</li>
        <li>Esto es un tratamiento nuevo: necesitas la autorización expresa del DPD de Florida para enviar datos a Anthropic y a Google (ver PRIVACIDAD.md §7).</li>
      </ul>
      <label className="check"><input type="checkbox" checked={ok} onChange={(e) => setOk(e.target.checked)} />
        <span>Confirmo que Florida me ha autorizado a usar la evaluación con IA en estas condiciones.</span></label>
      <button disabled={!ok} onClick={() => api.autoevalAck().then(onDone)}>Continuar</button>
    </div>
  )
}

export function AutoEvalPanel({ course, assign, fail }) {
  const [status, setStatus] = useState(null)
  const [data, setData] = useState(null)
  const [form, setForm] = useState(null)
  const [edits, setEdits] = useState({})
  const [selected, setSelected] = useState([])
  const [notify, setNotify] = useState(true)
  const [msg, setMsg] = useState('')
  const [open, setOpen] = useState(false)

  const load = useCallback(async () => {
    try {
      const [st, d] = await Promise.all([api.autoevalStatus(), api.autoeval(course.id, assign.cmid)])
      setStatus(st); setData(d)
      setForm((f) => f || (d.config
        ? { criteria: d.config.criteria, grade_max: d.config.grade_max, close_at: d.config.close_at, enabled: !!d.config.enabled }
        : { criteria: '', grade_max: 10, close_at: '', enabled: true }))
    } catch (err) { fail(err) }
  }, [course.id, assign.cmid, fail])
  useEffect(() => { if (open) load() }, [open, load])
  useEffect(() => {  // refresca mientras evalúa
    if (data?.config?.state !== 'running') return undefined
    const t = setTimeout(load, 3000); return () => clearTimeout(t)
  }, [data, load])

  async function save(e) {
    e.preventDefault()
    try {
      await api.saveAutoeval(course.id, assign.cmid, { ...form, name: assign.name, grade_max: Number(form.grade_max) })
      setMsg('Guardado. Se evaluará automáticamente al llegar la fecha de cierre (con el PC y la app encendidos).'); load()
    } catch (err) { fail(err) }
  }
  async function runNow() {
    if (!window.confirm('¿Evaluar ahora todas las entregas con IA? (las propuestas anteriores se sustituyen)')) return
    try { await api.runAutoeval(course.id, assign.cmid); setMsg(''); load() } catch (err) { fail(err) }
  }
  async function saveEdit(r) {
    const e = edits[r.userid]; if (!e) return
    try {
      await api.editResult(course.id, assign.cmid, r.userid, { grade: e.grade === '' ? null : Number(String(e.grade).replace(',', '.')), observation: e.observation })
      setEdits((x) => { const y = { ...x }; delete y[r.userid]; return y }); load()
    } catch (err) { fail(err) }
  }
  async function publish(userids) {
    const n = userids ? userids.length : data.results.filter((r) => r.status === 'proposed' && r.grade !== null).length
    if (!n) { window.alert('No hay propuestas seleccionadas con nota'); return }
    if (!window.confirm(`¿Publicar ${n} nota(s) revisada(s) en Florida Oberta${notify ? ' y avisar a los alumnos' : ''}?`)) return
    try {
      const r = await api.publishAutoeval(course.id, assign.cmid, { userids, notify })
      setMsg(`Publicadas: ${r.published}.${r.errors.length ? ` Errores: ${r.errors.length}.` : ''}${r.sheet_error ? ` Hoja de Google: ${r.sheet_error}` : ''}`)
      setSelected([]); load()
    } catch (err) { fail(err) }
  }

  return (
    <details className="autoeval" open={open} onToggle={(e) => setOpen(e.target.open)}>
      <summary>🤖 Evaluación automática con IA {data?.config && <span className="badge">{{ waiting: 'Programada', running: 'Evaluando', review: 'Por revisar', done: 'Publicada', error: 'Error' }[data.config.state]}</span>}</summary>
      {!status && open && <p className="spinner">Cargando…</p>}
      {status && !status.acknowledged && <Ack onDone={load} />}
      {status?.acknowledged && form && (
        <div className="grid">
          {!status.ai_configured && <p className="error">Falta la clave de la API de Claude: añade ANTHROPIC_API_KEY en backend/.env y reinicia.</p>}
          {!status.sheets_configured && <p className="muted small">Hoja de Google sin configurar (GOOGLE_SHEETS_WEBHOOK_URL y GOOGLE_SHEETS_SECRET en backend/.env): se evaluará igualmente, sin actualizarla.</p>}
          <form className="grid" onSubmit={save}>
            <label>Criterios de evaluación / rúbrica
              <textarea rows={5} required minLength={10} value={form.criteria} onChange={(e) => setForm({ ...form, criteria: e.target.value })}
                placeholder={'Ej.: Funciona correctamente (4 p). Código limpio y comentado (3 p). Explicación de la solución (3 p). Penaliza el plagio.'} />
            </label>
            <div className="grid2">
              <label>Nota máxima<input type="number" min="1" step="0.5" value={form.grade_max} onChange={(e) => setForm({ ...form, grade_max: e.target.value })} required /></label>
              <label>Evaluar al cerrarse la tarea el<input type="datetime-local" value={form.close_at} onChange={(e) => setForm({ ...form, close_at: e.target.value })} required /></label>
            </div>
            <label className="check"><input type="checkbox" checked={form.enabled} onChange={(e) => setForm({ ...form, enabled: e.target.checked })} /><span>Activada</span></label>
            <div className="row">
              <button type="submit">Guardar</button>
              {data?.config && <button type="button" className="secondary" onClick={runNow} disabled={data.config.state === 'running'}>Evaluar ahora</button>}
              {data?.config && <button type="button" className="secondary danger" onClick={() => window.confirm('¿Desactivar y borrar las propuestas de esta tarea?') && api.deleteAutoeval(course.id, assign.cmid).then(() => { setForm(null); load() })}>Quitar</button>}
            </div>
          </form>
          {data?.config && <p className={data.config.state === 'error' ? 'error' : 'muted'}>
            {data.config.state === 'running' && <span className="spinner" />}{STATE[data.config.state]}{data.config.last_error ? ` — ${data.config.last_error}` : ''}</p>}
          {msg && <p className="notice" role="status">{msg}</p>}

          {data?.results?.length > 0 && (
            <>
              <h4>Propuestas de la IA (revísalas antes de publicar)</h4>
              <ul className="subs">
                {data.results.map((r) => {
                  const e = edits[r.userid] || { grade: r.grade ?? '', observation: r.observation }
                  const changed = !!edits[r.userid]
                  return (
                    <li key={r.userid} className={`result ${r.status}`}>
                      <div className="row">
                        {r.status !== 'published' && (
                          <input type="checkbox" aria-label={`Seleccionar ${r.name}`} checked={selected.includes(r.userid)}
                            onChange={(ev) => setSelected(ev.target.checked ? [...selected, r.userid] : selected.filter((x) => x !== r.userid))} />
                        )}
                        <strong className="grow">{r.name}</strong>
                        <span className="badge">{r.status === 'published' ? 'Publicada' : r.status === 'needs_review' ? 'Revisar' : 'Propuesta'}</span>
                      </div>
                      <div className="gradebox">
                        <label>Nota<input inputMode="decimal" value={e.grade} disabled={r.status === 'published'}
                          onChange={(ev) => setEdits({ ...edits, [r.userid]: { ...e, grade: ev.target.value } })} /></label>
                        <label className="grow">Observación<textarea rows={3} value={e.observation} disabled={r.status === 'published'}
                          onChange={(ev) => setEdits({ ...edits, [r.userid]: { ...e, observation: ev.target.value } })} /></label>
                        {changed && <button className="secondary" onClick={() => saveEdit(r)}>Guardar cambio</button>}
                      </div>
                    </li>
                  )
                })}
              </ul>
              <div className="row">
                <label className="check"><input type="checkbox" checked={notify} onChange={(e) => setNotify(e.target.checked)} /><span>Notificar a los alumnos</span></label>
                <button onClick={() => publish(selected)} disabled={!selected.length || Object.keys(edits).length > 0}>Publicar seleccionadas ({selected.length})</button>
                <button className="secondary" onClick={() => publish(null)} disabled={Object.keys(edits).length > 0}>Publicar todas las propuestas</button>
              </div>
              <p className="muted small">«Publicar todas» no incluye las marcadas «Revisar»: esas publícalas seleccionándolas una a una tras revisarlas.</p>
            </>
          )}
        </div>
      )}
    </details>
  )
}
