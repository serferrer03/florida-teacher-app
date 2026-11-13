import React, { useCallback, useEffect, useState } from 'react'
import { api, ApiError } from './api.js'

const MOD_LABEL = {
  assign: 'Tarea', resource: 'Archivo', url: 'Enlace', forum: 'Foro', quiz: 'Cuestionario', page: 'Página',
  folder: 'Carpeta', label: 'Texto', lesson: 'Lección', choice: 'Consulta', feedback: 'Encuesta',
  glossary: 'Glosario', workshop: 'Taller', scorm: 'SCORM', h5pactivity: 'H5P', book: 'Libro',
  data: 'Base de datos', wiki: 'Wiki', lti: 'Herramienta externa', bigbluebuttonbn: 'Videoconferencia',
}

function ResourceForm({ course, section, onDone, onCancel, onNeedLogin }) {
  const [type, setType] = useState('file')
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [url, setUrl] = useState('https://')
  const [visible, setVisible] = useState(true)
  const [files, setFiles] = useState([])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  async function submit(e) {
    e.preventDefault()
    if (type === 'file' && !files.length) { setError('Elige al menos un archivo'); return }
    if (type === 'url' && !/^https?:\/\/\S+\.\S+/.test(url)) { setError('Escribe una dirección válida (https://…)'); return }
    const what = type === 'file' ? `el archivo «${name}» (${files.length} archivo/s)` : `el enlace «${name}»`
    if (!window.confirm(`¿Añadir ${what} en «${section.name}»${visible ? '' : ' (oculto)'}?`)) return
    setBusy(true); setError('')
    try {
      await api.addResource(course.id, { type, name, description, section: section.number, visible, url: type === 'url' ? url : null }, type === 'file' ? files : [])
      onDone()
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) onNeedLogin(err.message)
      else setError(err.message)
      setBusy(false)
    }
  }

  return (
    <form className="card wide" onSubmit={submit}>
      <h2>Añadir a «{section.name}»</h2>
      <div className="chips" role="radiogroup">
        <label className="check chip"><input type="radio" name="t" checked={type === 'file'} onChange={() => setType('file')} /><span>Archivo</span></label>
        <label className="check chip"><input type="radio" name="t" checked={type === 'url'} onChange={() => setType('url')} /><span>Enlace (URL)</span></label>
      </div>
      <label>Nombre<input value={name} onChange={(e) => setName(e.target.value)} maxLength={255} required /></label>
      {type === 'url'
        ? <label>Dirección<input type="url" value={url} onChange={(e) => setUrl(e.target.value)} required /></label>
        : (
          <>
            <input type="file" multiple onChange={(e) => {
              const picked = [...e.target.files]
              setFiles((old) => [...old, ...picked])
              if (!name && picked[0]) setName(picked[0].name.replace(/\.[^.]+$/, ''))
              e.target.value = ''
            }} />
            {files.length > 0 && (
              <ul className="files">{files.map((x, i) => (
                <li key={`${x.name}-${i}`}>{x.name}
                  <button type="button" className="link" onClick={() => setFiles(files.filter((_, j) => j !== i))}>Quitar</button></li>
              ))}</ul>
            )}
            {files.length > 1 && <p className="muted small">Se creará un único recurso con todos los archivos (el primero es el principal).</p>}
          </>
        )}
      <label>Descripción (opcional)<textarea rows={3} value={description} onChange={(e) => setDescription(e.target.value)} /></label>
      <label className="check"><input type="checkbox" checked={visible} onChange={(e) => setVisible(e.target.checked)} /><span>Visible para el alumnado</span></label>
      {error && <p className="error" role="alert">{error}</p>}
      {busy
        ? <p className="spinner">Añadiendo a Florida Oberta…</p>
        : <div className="row"><button type="submit">Añadir</button><button type="button" className="secondary" onClick={onCancel}>Cancelar</button></div>}
    </form>
  )
}

export function ContentsView({ course, onNeedLogin }) {
  const [sections, setSections] = useState(null)
  const [error, setError] = useState('')
  const [busyKey, setBusyKey] = useState('')
  const [adding, setAdding] = useState(null)   // sección donde se añade un recurso
  const [open, setOpen] = useState({})

  const fail = useCallback((err) => {
    if (err instanceof ApiError && err.status === 409) onNeedLogin(err.message)
    else setError(err.message)
  }, [onNeedLogin])

  const load = useCallback(async () => {
    setError('')
    try { setSections((await api.contents(course.id)).sections) } catch (err) { fail(err) }
  }, [course.id, fail])
  useEffect(() => { load() }, [load])

  async function act(key, question, fn) {
    if (question && !window.confirm(question)) return
    setBusyKey(key); setError('')
    try { await fn(); await load() } catch (err) { fail(err) } finally { setBusyKey('') }
  }
  const toggle = (kind, it) => act(`${kind}${it.id ?? it.cmid}`,
    `¿${it.visible ? 'Ocultar' : 'Mostrar'} «${it.name}» al alumnado?`,
    () => api.setVisibility(course.id, kind, it.id ?? it.cmid, !it.visible))
  const rename = (kind, it) => {
    const name = window.prompt('Nuevo nombre:', it.name)
    if (!name || name.trim() === it.name) return
    act(`${kind}${it.id ?? it.cmid}`, null, () => api.rename(course.id, kind, it.id ?? it.cmid, name.trim()))
  }

  if (adding) {
    return <ResourceForm course={course} section={adding} onNeedLogin={onNeedLogin}
      onCancel={() => setAdding(null)} onDone={() => { setAdding(null); load() }} />
  }
  if (!sections) return error ? <p className="error" role="alert">{error}</p> : <p className="spinner">Cargando contenidos…</p>

  return (
    <div className="contents">
      {error && <p className="error" role="alert">{error}</p>}
      <div className="row"><button className="secondary" onClick={load}>Recargar</button></div>
      {sections.map((s) => {
        const isOpen = open[s.id] ?? true
        return (
          <section key={s.id} className={`section-card${s.visible ? '' : ' hidden-item'}`}>
            <header>
              <button className="link expand" aria-expanded={isOpen} onClick={() => setOpen({ ...open, [s.id]: !isOpen })}>
                {isOpen ? '▾' : '▸'} {s.name}
              </button>
              {!s.visible && <span className="badge">Oculto</span>}
              <span className="actions">
                <button className="link" disabled={!!busyKey} onClick={() => rename('section', s)}>Renombrar</button>
                {s.number > 0 && (
                  <button className="link" disabled={!!busyKey} onClick={() => toggle('section', s)}>
                    {busyKey === `section${s.id}` ? '…' : s.visible ? 'Ocultar' : 'Mostrar'}</button>
                )}
                <button className="link" onClick={() => setAdding(s)}>+ Añadir</button>
              </span>
            </header>
            {isOpen && (
              s.items.length === 0
                ? <p className="muted small pad">Sin contenido.</p>
                : (
                  <ul className="items">
                    {s.items.map((it) => (
                      <li key={it.cmid} className={it.visible ? '' : 'hidden-item'}>
                        <a href={it.url} target="_blank" rel="noreferrer noopener">
                          <span className="mod">{MOD_LABEL[it.modname] || it.modname}</span> {it.name}
                        </a>
                        {!it.visible && <span className="badge">Oculto</span>}
                        <span className="actions">
                          <button className="link" disabled={!!busyKey} onClick={() => rename('cm', it)}>Renombrar</button>
                          <button className="link" disabled={!!busyKey} onClick={() => toggle('cm', it)}>
                            {busyKey === `cm${it.cmid}` ? '…' : it.visible ? 'Ocultar' : 'Mostrar'}</button>
                        </span>
                      </li>
                    ))}
                  </ul>
                )
            )}
          </section>
        )
      })}
    </div>
  )
}
