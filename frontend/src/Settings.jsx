import React, { useEffect, useState } from 'react'
import { api, getToken, setToken } from './api.js'

// Fase 6: conexión segura (HTTPS) · Fase 7: código de acceso y copia de seguridad
export function SecuritySettings() {
  const [conn, setConn] = useState(null)
  const [msg, setMsg] = useState('')
  const [error, setError] = useState('')
  useEffect(() => { api.connection().then(setConn).catch(() => {}) }, [])

  async function rotate() {
    if (!window.confirm('¿Generar un código de acceso nuevo? Todos los demás dispositivos (también uno perdido) tendrán que volver a vincularse.')) return
    try {
      const { code } = await api.rotateCode()
      setToken(code)
      setMsg(`Nuevo código: ${code}. Esta pantalla ya lo usa; escríbelo en tus otros dispositivos.`)
    } catch (err) { setError(err.message) }
  }
  async function download() {
    try {
      const res = await fetch('/api/backup', { headers: { 'X-App-Token': getToken() }, cache: 'no-store' })
      if (!res.ok) throw new Error(`Error ${res.status}`)
      const url = URL.createObjectURL(await res.blob())
      const a = document.createElement('a'); a.href = url; a.download = 'florida-teacher-app-copia.json'; a.click()
      setTimeout(() => URL.revokeObjectURL(url), 60000)
    } catch (err) { setError(err.message) }
  }
  async function restore(e) {
    const file = e.target.files[0]; e.target.value = ''
    if (!file) return
    try {
      const { templates_added: n } = await api.restoreBackup(JSON.parse(await file.text()))
      setMsg(`Copia restaurada: ${n} plantilla(s) nuevas.`)
    } catch (err) { setError(err.message || 'Archivo de copia no válido') }
  }

  return (
    <>
      <h3>Conexión segura (HTTPS)</h3>
      {!conn && <p className="muted">Comprobando…</p>}
      {conn?.secure && <p>✅ Estás usando una conexión cifrada.</p>}
      {conn && !conn.secure && (
        conn.https_available ? (
          <div className="steps">
            <p>Ahora mismo la conexión con el PC <strong>no está cifrada</strong>. Para cifrarla, una sola vez en la tablet:</p>
            <ol>
              <li><a href="/ca.crt" download>Descarga el certificado de la app</a> (es público, no contiene secretos).</li>
              <li>En Android: <em>Ajustes → Seguridad y privacidad → Más ajustes de seguridad → Cifrado y credenciales →
                Instalar un certificado → Certificado de CA</em>, y elige el archivo descargado
                (el nombre del menú puede variar según la marca).</li>
              <li>Abre <a href={conn.https_url}>{conn.https_url}</a>, vuelve a escribir el código de acceso e
                instala la app desde el menú de Chrome.</li>
            </ol>
            <p className="muted small">Ese certificado solo sirve para direcciones de tu red local: no permite suplantar
              ninguna web de Internet. Si desinstalas la app, quítalo en «Credenciales de usuario».</p>
          </div>
        ) : <p className="muted">HTTPS no está activo: arranca la app con <code>Iniciar.bat</code> (o <code>run.py</code>).</p>
      )}

      <h3>Código de acceso</h3>
      <p className="muted small">Si pierdes la tablet o crees que alguien conoce el código, genera uno nuevo.</p>
      <button className="secondary" onClick={rotate}>Cambiar código de acceso</button>

      <h3>Copia de seguridad</h3>
      <p className="muted small">Incluye tus plantillas y el registro de tareas creadas. No incluye contraseñas,
        sesiones ni datos del alumnado.</p>
      <div className="row">
        <button className="secondary" onClick={download}>Descargar copia</button>
        <label className="button secondary filelabel">Restaurar copia…
          <input type="file" accept="application/json,.json" onChange={restore} hidden /></label>
      </div>
      {msg && <p className="notice" role="status">{msg}</p>}
      {error && <p className="error" role="alert">{error}</p>}
    </>
  )
}
