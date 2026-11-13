import React, { useEffect, useMemo, useState } from 'react'
import { api, ApiError } from './api.js'
import { ContentsView } from './Contents.jsx'
import { GradingView } from './Grading.jsx'
import { StudentsView } from './Students.jsx'

// ------------------------------------------------------------ utilidades
const pad = (n) => String(n).padStart(2, '0')
function localValue(date) {
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`
}
function daysFromNow(days, h, m) {
  const d = new Date(); d.setDate(d.getDate() + days); d.setHours(h, m, 0, 0); return localValue(d)
}
function show(dt) {
  return dt ? new Date(dt).toLocaleString('es-ES', { dateStyle: 'full', timeStyle: 'short' }) : '—'
}
function size(bytes) {
  return bytes > 1048576 ? `${(bytes / 1048576).toFixed(1)} MB` : `${Math.max(1, Math.round(bytes / 1024))} KB`
}

function defaults() {
  return {
    name: '', description: '', show_description: false, section: 0, visible: true,
    allow_from: localValue(new Date(Math.ceil(Date.now() / 300000) * 300000)),
    due: daysFromNow(7, 23, 55), cutoff: '', grading_due: daysFromNow(14, 9, 0),
    use: { allow_from: true, due: true, cutoff: false, grading_due: true },
    online_text: false, file_submissions: true, max_files: '1', max_size_bytes: '0', grade_max: 10,
    r: { use_from: false, date_from: '', use_until: false, date_until: '', group_ids: [], grouping_id: '',
      grade_item: '', grade_min: 50, show_to_students: true },
  }
}

// Plantillas: las fechas se guardan relativas a hoy (+N días a HH:MM)
const DATE_KEYS = ['allow_from', 'due', 'cutoff', 'grading_due']
function toRelative(v) {
  if (!v) return null
  const d = new Date(v); const t = new Date(); t.setHours(0, 0, 0, 0)
  const day = new Date(d); day.setHours(0, 0, 0, 0)
  return { days: Math.round((day - t) / 86400000), time: v.slice(11, 16) }
}
function fromRelative(rel) {
  if (!rel) return ''
  const [h, m] = rel.time.split(':').map(Number)
  return daysFromNow(rel.days, h, m)
}
function formToTemplate(f) {
  const { name, description, show_description, section, visible, use, online_text, file_submissions,
    max_files, max_size_bytes, grade_max, r } = f
  return {
    name, description, show_description, section, visible, use, online_text, file_submissions,
    max_files, max_size_bytes, grade_max,
    rel: Object.fromEntries(DATE_KEYS.map((k) => [k, toRelative(f[k])])),
    r: { use_from: r.use_from, from: toRelative(r.date_from), use_until: r.use_until, until: toRelative(r.date_until),
      show_to_students: r.show_to_students },
  }
}
function templateToForm(t) {
  const base = defaults()
  const dates = Object.fromEntries(DATE_KEYS.map((k) => [k, fromRelative(t.rel?.[k]) || base[k]]))
  return {
    ...base, ...t, ...dates, use: { ...base.use, ...t.use },
    r: { ...base.r, use_from: !!t.r?.use_from, date_from: fromRelative(t.r?.from), use_until: !!t.r?.use_until,
      date_until: fromRelative(t.r?.until), show_to_students: t.r?.show_to_students ?? true },
  }
}

const DATE_LABELS = {
  allow_from: 'Permitir entregas desde',
  due: 'Fecha de entrega',
  cutoff: 'Fecha límite (después no se admiten entregas)',
  grading_due: 'Recordarme calificar el',
}

function toPayload(f) {
  const d = (k) => (f.use[k] && f[k] ? f[k] : null)
  return {
    name: f.name, description: f.description, show_description: f.show_description,
    section: Number(f.section), visible: f.visible,
    allow_from: d('allow_from'), due: d('due'), cutoff: d('cutoff'), grading_due: d('grading_due'),
    online_text: f.online_text, file_submissions: f.file_submissions,
    max_files: Number(f.max_files), max_size_bytes: Number(f.max_size_bytes), grade_max: Number(f.grade_max),
    restrictions: {
      date_from: f.r.use_from && f.r.date_from ? f.r.date_from : null,
      date_until: f.r.use_until && f.r.date_until ? f.r.date_until : null,
      group_ids: f.r.group_ids.map(Number),
      grouping_id: f.r.grouping_id ? Number(f.r.grouping_id) : null,
      grade: f.r.grade_item ? { item_id: Number(f.r.grade_item), min_percent: Number(f.r.grade_min) } : null,
      show_to_students: f.r.show_to_students,
    },
  }
}

function validate(p, files) {
  if (!p.name.trim()) return 'Escribe un nombre para la tarea'
  if (!p.online_text && !p.file_submissions) return 'Elige al menos un tipo de entrega'
  if (p.allow_from && p.due && p.due < p.allow_from) return 'La fecha de entrega es anterior a «Permitir entregas desde»'
  if (p.cutoff && p.due && p.cutoff < p.due) return 'La fecha límite es anterior a la fecha de entrega'
  if (p.grading_due && p.due && p.grading_due < p.due) return '«Recordarme calificar» es anterior a la fecha de entrega'
  const r = p.restrictions
  if (r.date_from && r.date_until && r.date_until <= r.date_from) return 'En las restricciones, «hasta» debe ser posterior a «desde»'
  if (files.length > 20) return 'Máximo 20 archivos'
  const big = files.find((x) => x.size > 100 * 1048576)
  if (big) return `«${big.name}» supera los 100 MB`
  return ''
}

// --------------------------------------------------------- formulario
function AssignmentForm({ course, options, onCreated, onCancel, onNeedLogin }) {
  const [f, setF] = useState(defaults)
  const [files, setFiles] = useState([])
  const [step, setStep] = useState('edit')  // edit | review | sending
  const [error, setError] = useState('')
  const set = (patch) => setF((o) => ({ ...o, ...patch }))
  const setR = (patch) => setF((o) => ({ ...o, r: { ...o.r, ...patch } }))
  const setUse = (k, v) => setF((o) => ({ ...o, use: { ...o.use, [k]: v } }))
  const payload = useMemo(() => toPayload(f), [f])
  const [templates, setTemplates] = useState([])
  const [allCourses, setAllCourses] = useState([])
  const [extra, setExtra] = useState([])   // otros cursos donde crear la misma tarea
  const [progress, setProgress] = useState('')
  useEffect(() => {
    api.templates().then((d) => setTemplates(d.templates)).catch(() => {})
    api.courses().then((d) => setAllCourses(d.courses.filter((c) => c.id !== course.id))).catch(() => {})
  }, [course.id])

  function applyTemplate(id) {
    const t = templates.find((x) => String(x.id) === id)
    if (!t) return
    const form = templateToForm(t.data)
    if (!options.sections.some((s) => s.number === Number(form.section))) form.section = 0
    setF(form)
  }
  async function saveTemplate() {
    const name = window.prompt('Nombre de la plantilla:', f.name)
    if (!name) return
    try {
      await api.saveTemplate(name, formToTemplate(f))
      setTemplates((await api.templates()).templates)
      window.alert('Plantilla guardada. Las fechas se guardan relativas a hoy.')
    } catch (err) { setError(err.message) }
  }
  async function deleteTemplate(id) {
    const t = templates.find((x) => String(x.id) === id)
    if (!t || !window.confirm(`¿Borrar la plantilla «${t.name}»?`)) return
    await api.deleteTemplate(t.id).catch((e) => setError(e.message))
    setTemplates((await api.templates()).templates)
  }
  const names = (list, ids) => list.filter((x) => ids.includes(x.id)).map((x) => x.name)

  function review(e) {
    e.preventDefault()
    const msg = validate(payload, files)
    setError(msg)
    if (!msg) { setStep('review'); window.scrollTo(0, 0) }
  }

  async function send() {
    setStep('sending'); setError('')
    let main
    try {
      setProgress(course.fullname)
      main = await api.createAssignment(course.id, payload, files)
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) { onNeedLogin(err.message); return }
      setError(err.message); setStep('review'); return
    }
    // Otros cursos: grupos, agrupamientos y notas son de cada curso, así que esas restricciones no se copian
    const generic = { ...payload, restrictions: { ...payload.restrictions, group_ids: [], grouping_id: null, grade: null } }
    const others = []
    for (const c of allCourses.filter((x) => extra.includes(x.id))) {
      setProgress(c.fullname)
      try {
        const res = await api.createAssignment(c.id, generic, files)
        others.push({ course: c.fullname, url: res.url })
      } catch (err) {
        others.push({ course: c.fullname, error: err.message })
      }
    }
    onCreated({ ...main, others })
  }

  const sectionName = options.sections.find((s) => s.number === Number(f.section))?.name
  const sizeLabel = options.max_sizes.find((o) => o.value === f.max_size_bytes)?.label
  const r = payload.restrictions

  if (step !== 'edit') {
    return (
      <section className="card wide" aria-live="polite">
        <h2>Revisa la tarea antes de crearla</h2>
        <dl className="summary">
          <dt>Curso</dt><dd>{course.fullname}</dd>
          <dt>Tema</dt><dd>{sectionName}</dd>
          <dt>Nombre</dt><dd>{payload.name}</dd>
          <dt>Visible</dt><dd>{payload.visible ? 'Sí' : 'No (oculta al alumnado)'}</dd>
          {Object.keys(DATE_LABELS).map((k) => <React.Fragment key={k}><dt>{DATE_LABELS[k]}</dt><dd>{show(payload[k])}</dd></React.Fragment>)}
          <dt>Entregas</dt><dd>{[payload.online_text && 'Texto en línea',
            payload.file_submissions && `Archivos (máx. ${payload.max_files}, ${sizeLabel || 'límite del curso'})`].filter(Boolean).join(' · ')}</dd>
          <dt>Calificación</dt><dd>{payload.grade_max > 0 ? `Sobre ${payload.grade_max}` : 'Sin calificación'}</dd>
          <dt>Archivos adjuntos</dt><dd>{files.length ? files.map((x) => x.name).join(', ') : 'Ninguno'}</dd>
          {extra.length > 0 && <><dt>También en</dt><dd>{allCourses.filter((c) => extra.includes(c.id)).map((c) => c.fullname).join(', ')}
            {(r.group_ids.length > 0 || r.grouping_id || r.grade) && <div className="muted small">(en esos cursos sin las restricciones de grupo/nota)</div>}</dd></>}
          <dt>Restricciones</dt>
          <dd>{[r.date_from && `desde ${show(r.date_from)}`, r.date_until && `hasta ${show(r.date_until)}`,
            r.group_ids.length && `grupo: ${names(options.groups, r.group_ids).join(' o ')}`,
            r.grouping_id && `agrupamiento: ${names(options.groupings, [r.grouping_id])[0]}`,
            r.grade && `nota ≥ ${r.grade.min_percent}% en ${names(options.grade_items, [r.grade.item_id])[0]}`,
          ].filter(Boolean).join(' · ') || 'Ninguna'}</dd>
        </dl>
        {error && <p className="error" role="alert">{error}</p>}
        {step === 'sending'
          ? <p className="spinner">Creando la tarea en «{progress}»{files.length ? ' y subiendo archivos' : ''}… puede tardar un poco.</p>
          : (
            <div className="row">
              <button onClick={send}>Crear tarea en Florida Oberta</button>
              <button className="secondary" onClick={() => setStep('edit')}>Volver a editar</button>
            </div>
          )}
      </section>
    )
  }

  return (
    <form className="card wide" onSubmit={review}>
      <h2>Nueva tarea · {course.fullname}</h2>
      <div className="row template-bar">
        <select defaultValue="" onChange={(e) => { applyTemplate(e.target.value); e.target.value = '' }} aria-label="Cargar plantilla">
          <option value="" disabled>{templates.length ? 'Cargar plantilla…' : 'Sin plantillas guardadas'}</option>
          {templates.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
        </select>
        <button type="button" className="secondary" onClick={saveTemplate}>Guardar como plantilla</button>
        {templates.length > 0 && (
          <select defaultValue="" onChange={(e) => { deleteTemplate(e.target.value); e.target.value = '' }} aria-label="Borrar plantilla">
            <option value="" disabled>Borrar plantilla…</option>
            {templates.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
          </select>
        )}
      </div>

      <fieldset>
        <legend>General</legend>
        <label>Nombre<input value={f.name} onChange={(e) => set({ name: e.target.value })} maxLength={255} required autoFocus /></label>
        <label>Descripción
          <textarea rows={5} value={f.description} onChange={(e) => set({ description: e.target.value })} />
        </label>
        <label className="check"><input type="checkbox" checked={f.show_description}
          onChange={(e) => set({ show_description: e.target.checked })} /><span>Mostrar la descripción en la página del curso</span></label>
        <div className="grid2">
          <label>Tema / sección
            <select value={f.section} onChange={(e) => set({ section: e.target.value })}>
              {options.sections.map((s) => <option key={s.number} value={s.number}>{s.name}</option>)}
            </select>
          </label>
          <label className="check end"><input type="checkbox" checked={f.visible}
            onChange={(e) => set({ visible: e.target.checked })} /><span>Visible para el alumnado</span></label>
        </div>
      </fieldset>

      <fieldset>
        <legend>Fechas</legend>
        {Object.entries(DATE_LABELS).map(([k, label]) => (
          <div className="daterow" key={k}>
            <label className="check"><input type="checkbox" checked={f.use[k]} onChange={(e) => setUse(k, e.target.checked)} /><span>{label}</span></label>
            <input type="datetime-local" value={f[k]} disabled={!f.use[k]} required={f.use[k]}
              onChange={(e) => set({ [k]: e.target.value })} />
          </div>
        ))}
      </fieldset>

      <fieldset>
        <legend>Entregas y calificación</legend>
        <label className="check"><input type="checkbox" checked={f.online_text} onChange={(e) => set({ online_text: e.target.checked })} /><span>Texto en línea</span></label>
        <label className="check"><input type="checkbox" checked={f.file_submissions} onChange={(e) => set({ file_submissions: e.target.checked })} /><span>Archivos enviados</span></label>
        {f.file_submissions && (
          <div className="grid2">
            <label>Nº máximo de archivos
              <select value={f.max_files} onChange={(e) => set({ max_files: e.target.value })}>
                {(options.max_files.length ? options.max_files : ['1']).map((v) => <option key={v} value={v}>{v}</option>)}
              </select>
            </label>
            <label>Tamaño máximo por archivo
              <select value={f.max_size_bytes} onChange={(e) => set({ max_size_bytes: e.target.value })}>
                {(options.max_sizes.length ? options.max_sizes : [{ value: '0', label: 'Límite del curso' }])
                  .map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
              </select>
            </label>
          </div>
        )}
        <label>Calificación máxima (0 = sin calificación)
          <input type="number" min="0" max="10000" value={f.grade_max} onChange={(e) => set({ grade_max: e.target.value })} />
        </label>
      </fieldset>

      <fieldset>
        <legend>Archivos adicionales (enunciado, plantillas…)</legend>
        <input type="file" multiple onChange={(e) => { const picked = [...e.target.files]; setFiles((old) => [...old, ...picked]); e.target.value = '' }} />
        {files.length > 0 && (
          <ul className="files">
            {files.map((x, i) => (
              <li key={`${x.name}-${i}`}>{x.name} <span className="muted small">({size(x.size)})</span>
                <button type="button" className="link" onClick={() => setFiles(files.filter((_, j) => j !== i))}>Quitar</button></li>
            ))}
          </ul>
        )}
        <p className="muted small">Se suben a Florida Oberta y se borran del PC en cuanto se adjuntan.</p>
      </fieldset>

      {options.restrictions_enabled && (
        <fieldset>
          <legend>Restricciones de acceso</legend>
          <div className="daterow">
            <label className="check"><input type="checkbox" checked={f.r.use_from} onChange={(e) => setR({ use_from: e.target.checked })} /><span>Accesible desde</span></label>
            <input type="datetime-local" value={f.r.date_from} disabled={!f.r.use_from} required={f.r.use_from} onChange={(e) => setR({ date_from: e.target.value })} />
          </div>
          <div className="daterow">
            <label className="check"><input type="checkbox" checked={f.r.use_until} onChange={(e) => setR({ use_until: e.target.checked })} /><span>Accesible hasta</span></label>
            <input type="datetime-local" value={f.r.date_until} disabled={!f.r.use_until} required={f.r.use_until} onChange={(e) => setR({ date_until: e.target.value })} />
          </div>
          {options.groups.length > 0 && (
            <div>
              <p className="label">Solo para estos grupos (si marcas varios, basta con pertenecer a uno)</p>
              <div className="chips">
                {options.groups.map((g) => (
                  <label key={g.id} className="check chip"><input type="checkbox" checked={f.r.group_ids.includes(g.id)}
                    onChange={(e) => setR({ group_ids: e.target.checked ? [...f.r.group_ids, g.id] : f.r.group_ids.filter((x) => x !== g.id) })} />
                    <span>{g.name}</span></label>
                ))}
              </div>
            </div>
          )}
          {options.groupings.length > 0 && (
            <label>Agrupamiento
              <select value={f.r.grouping_id} onChange={(e) => setR({ grouping_id: e.target.value })}>
                <option value="">— Ninguno —</option>
                {options.groupings.map((g) => <option key={g.id} value={g.id}>{g.name}</option>)}
              </select>
            </label>
          )}
          {options.grade_items.length > 0 && (
            <div className="grid2">
              <label>Requiere nota en
                <select value={f.r.grade_item} onChange={(e) => setR({ grade_item: e.target.value })}>
                  <option value="">— Sin condición de nota —</option>
                  {options.grade_items.map((g) => <option key={g.id} value={g.id}>{g.name}</option>)}
                </select>
              </label>
              {f.r.grade_item && (
                <label>Nota mínima (%)
                  <input type="number" min="0" max="100" value={f.r.grade_min} onChange={(e) => setR({ grade_min: e.target.value })} />
                </label>
              )}
            </div>
          )}
          <label className="check"><input type="checkbox" checked={f.r.show_to_students} onChange={(e) => setR({ show_to_students: e.target.checked })} />
            <span>Mostrar la restricción al alumnado (si no, la tarea no aparece hasta cumplirla)</span></label>
        </fieldset>
      )}

      {allCourses.length > 0 && (
        <fieldset>
          <legend>Crear también en otros cursos</legend>
          <div className="chips">
            {allCourses.map((c) => (
              <label key={c.id} className="check chip"><input type="checkbox" checked={extra.includes(c.id)}
                onChange={(e) => setExtra(e.target.checked ? [...extra, c.id] : extra.filter((x) => x !== c.id))} />
                <span>{c.fullname}</span></label>
            ))}
          </div>
          <p className="muted small">Se crea con los mismos datos y archivos, en el tema con el mismo número. Las restricciones de grupo, agrupamiento y nota no se copian.</p>
        </fieldset>
      )}

      {error && <p className="error" role="alert">{error}</p>}
      <div className="row">
        <button type="submit">Revisar</button>
        <button type="button" className="secondary" onClick={onCancel}>Cancelar</button>
      </div>
    </form>
  )
}

// ------------------------------------------------------- vista del curso
export function CourseDetail({ course, onBack, onNeedLogin }) {
  const [options, setOptions] = useState(null)
  const [list, setList] = useState([])
  const [mode, setMode] = useState('list')  // list | form | done
  const [tab, setTab] = useState('contents')  // contents | assignments
  const [created, setCreated] = useState(null)
  const [error, setError] = useState('')

  const loadList = () => api.assignments(course.id).then((d) => setList(d.assignments)).catch(() => {})
  useEffect(() => { loadList() }, [course.id])  // eslint-disable-line react-hooks/exhaustive-deps

  async function newAssignment(refresh = false) {
    setError('')
    try {
      if (!options || refresh) setOptions(await api.assignOptions(course.id, refresh))
      setMode('form')
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) onNeedLogin(err.message)
      else setError(err.message)
    }
  }
  const [loadingOptions, setLoadingOptions] = useState(false)
  const start = async (refresh) => { setLoadingOptions(true); await newAssignment(refresh); setLoadingOptions(false) }

  return (
    <section>
      <div className="toolbar">
        <div>
          <button className="link" onClick={onBack}>← Mis cursos</button>
          <h2>{course.fullname}</h2>
          <a className="muted small" href={course.url} target="_blank" rel="noreferrer noopener">Abrir en Florida Oberta ↗</a>
        </div>
        {mode === 'list' && (
          <button onClick={() => start(false)} disabled={loadingOptions}>{loadingOptions ? 'Abriendo formulario…' : '+ Nueva tarea'}</button>
        )}
      </div>
      {error && <p className="error" role="alert">{error}</p>}

      {mode === 'form' && options && (
        <AssignmentForm course={course} options={options} onNeedLogin={onNeedLogin}
          onCancel={() => setMode('list')}
          onCreated={(res) => { setCreated(res); setMode('done'); loadList() }} />
      )}

      {mode === 'done' && created && (
        <div className="card wide">
          <h2>✅ Tarea creada</h2>
          <p>«{created.name}» ya está en Florida Oberta.</p>
          {created.others?.length > 0 && (
            <ul className="files">
              {created.others.map((o) => (
                <li key={o.course}>{o.error
                  ? <span className="error">{o.course}: {o.error}</span>
                  : <a href={o.url} target="_blank" rel="noreferrer noopener">{o.course} ↗</a>}</li>
              ))}
            </ul>
          )}
          <p className="muted small">Revisa la primera vez en Florida Oberta que fechas, archivos y restricciones son correctos.</p>
          <div className="row">
            <a className="button" href={created.url} target="_blank" rel="noreferrer noopener">Ver en Florida Oberta ↗</a>
            <button className="secondary" onClick={() => start(false)}>Crear otra</button>
            <button className="secondary" onClick={() => setMode('list')}>Volver</button>
          </div>
        </div>
      )}

      {mode === 'list' && (
        <nav className="tabs subtabs">
          <button className={tab === 'contents' ? 'tab active' : 'tab'} onClick={() => setTab('contents')}>Contenidos</button>
          <button className={tab === 'grading' ? 'tab active' : 'tab'} onClick={() => setTab('grading')}>Entregas y notas</button>
          <button className={tab === 'students' ? 'tab active' : 'tab'} onClick={() => setTab('students')}>Por alumno</button>
          <button className={tab === 'assignments' ? 'tab active' : 'tab'} onClick={() => setTab('assignments')}>Tareas creadas desde la app</button>
        </nav>
      )}
      {mode === 'list' && tab === 'contents' && <ContentsView course={course} onNeedLogin={onNeedLogin} />}
      {mode === 'list' && tab === 'grading' && <GradingView course={course} onNeedLogin={onNeedLogin} />}
      {mode === 'list' && tab === 'students' && <StudentsView course={course} onNeedLogin={onNeedLogin} />}

      {mode === 'list' && tab === 'assignments' && (
        <>
          {list.length === 0
            ? <p className="muted">Todavía no has creado tareas en este curso desde la app.</p>
            : (
              <ul className="courses">
                {list.map((a) => (
                  <li key={a.id} className="course">
                    <a href={a.url} target="_blank" rel="noreferrer noopener">
                      <span className="course-name">{a.name}</span>
                      <span className="course-meta">
                        {a.due ? `Entrega: ${show(a.due)}` : 'Sin fecha de entrega'}
                        {a.files ? ` · ${a.files} archivo(s)` : ''}{a.restricted ? ' · con restricciones' : ''}
                      </span>
                    </a>
                  </li>
                ))}
              </ul>
            )}
        </>
      )}
    </section>
  )
}
