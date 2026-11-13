import React, { useCallback, useEffect, useState } from 'react'
import { api, ApiError } from './api.js'

const MONTHS = ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre']

export function CalendarView({ onNeedLogin }) {
  const now = new Date()
  const [ym, setYm] = useState({ y: now.getFullYear(), m: now.getMonth() + 1 })
  const [events, setEvents] = useState(null)
  const [error, setError] = useState('')

  const load = useCallback(async () => {
    setEvents(null); setError('')
    try { setEvents((await api.calendar(ym.y, ym.m)).events) } catch (err) {
      if (err instanceof ApiError && err.status === 409) onNeedLogin(err.message)
      else setError(err.message)
      setEvents([])
    }
  }, [ym, onNeedLogin])
  useEffect(() => { load() }, [load])

  const move = (d) => setYm(({ y, m }) => {
    const t = new Date(y, m - 1 + d, 1); return { y: t.getFullYear(), m: t.getMonth() + 1 }
  })
  const today = new Date().toDateString()
  const byDay = {}
  for (const e of events || []) {
    const key = new Date(e.start * 1000).toDateString()
    ;(byDay[key] ||= []).push(e)
  }

  return (
    <section className="calendar">
      <div className="toolbar">
        <h2>Calendario · {MONTHS[ym.m - 1]} {ym.y}</h2>
        <div className="row">
          <button className="secondary" onClick={() => move(-1)} aria-label="Mes anterior">‹</button>
          <button className="secondary" onClick={() => setYm({ y: now.getFullYear(), m: now.getMonth() + 1 })}>Hoy</button>
          <button className="secondary" onClick={() => move(1)} aria-label="Mes siguiente">›</button>
        </div>
      </div>
      {error && <p className="error" role="alert">{error}</p>}
      {!events && <p className="spinner">Cargando el calendario de Florida Oberta…</p>}
      {events && events.length === 0 && !error && <p className="muted">No hay eventos este mes.</p>}
      {Object.entries(byDay).map(([key, list]) => {
        const d = new Date(key)
        const past = d < new Date(today)
        return (
          <div key={key} className={`day${key === today ? ' today' : ''}${past ? ' past' : ''}`}>
            <h3>{d.toLocaleDateString('es-ES', { weekday: 'long', day: 'numeric', month: 'long' })}{key === today && ' · hoy'}</h3>
            <ul className="items">
              {list.map((e) => (
                <li key={e.id}>
                  <span className="time">{new Date(e.start * 1000).toLocaleTimeString('es-ES', { hour: '2-digit', minute: '2-digit' })}</span>
                  {e.url
                    ? <a href={e.url} target="_blank" rel="noreferrer noopener">{e.name}</a>
                    : <span className="grow">{e.name}</span>}
                  {e.course && <span className="muted small">{e.course}</span>}
                </li>
              ))}
            </ul>
          </div>
        )
      })}
    </section>
  )
}
