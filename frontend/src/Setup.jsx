import React, { useEffect, useState } from 'react'
import QRCode from 'qrcode'
import { api } from './api.js'

function QR({ text, label }) {
  const [src, setSrc] = useState('')
  useEffect(() => { QRCode.toDataURL(text, { margin: 1, width: 220 }).then(setSrc).catch(() => setSrc('')) }, [text])
  return (
    <figure className="qr">
      {src && <img src={src} alt={`Código QR: ${label}`} width="220" height="220" />}
      <figcaption>{label}<br /><code className="small">{text.replace(/#code=.*/, '')}</code></figcaption>
    </figure>
  )
}

function TabletSection() {
  const [p, setP] = useState(null)
  useEffect(() => { api.pairing().then(setP).catch(() => {}) }, [])
  if (!p) return <p className="muted">Cargando…</p>
  const appUrl = `${p.https_url || p.http_url}#code=${p.code}`
  return (
    <>
      <p>Con la tablet en <strong>la misma Wi-Fi</strong> que este PC, abre la cámara y escanea:</p>
      <div className="qr-row">
        {p.ca_url && <QR text={p.ca_url} label="1 · Certificado de seguridad (una sola vez)" />}
        <QR text={appUrl} label={p.ca_url ? '2 · Abrir la app ya vinculada' : 'Abrir la app ya vinculada'} />
      </div>
      {p.ca_url && (
        <details>
          <summary>¿Cómo instalo el certificado (paso 1)?</summary>
          <ol className="small">
            <li>Escanea el QR 1: se descarga «florida-teacher-app-ca.crt».</li>
            <li>Android: <em>Ajustes → Seguridad y privacidad → Más ajustes de seguridad → Cifrado y credenciales → Instalar un certificado → Certificado de CA</em> y elige ese archivo.</li>
            <li>Escanea el QR 2 y, en el menú ⋮ de Chrome, pulsa <strong>«Instalar aplicación»</strong>: tendrás el icono en la pantalla de inicio.</li>
          </ol>
          <p className="muted small">Si prefieres no instalar el certificado, abre <code>{p.http_url}</code> y escribe el código <strong>{p.code}</strong>
            (funciona igual, pero sin cifrado y sin instalación completa).</p>
        </details>
      )}
      <p className="muted small">Código de acceso: <strong>{p.code}</strong> · No muestres estos QR a otras personas.</p>
    </>
  )
}

function Status({ result }) {
  if (!result) return null
  return <p className={result.ok ? 'notice' : 'error'} role="status">{result.ok ? '✅ ' : '❌ '}{result.message}</p>
}

function AISection({ s, reload }) {
  const [form, setForm] = useState({ ai_provider: s.ai_provider || 'auto', anthropic_api_key: '', gemini_api_key: '', ai_model: s.ai_model || '' })
  const [busy, setBusy] = useState(false)
  const [result, setResult] = useState(null)
  async function save(e) {
    e.preventDefault(); setBusy(true); setResult(null)
    const body = { ai_provider: form.ai_provider, ai_model: form.ai_model }
    if (form.anthropic_api_key) body.anthropic_api_key = form.anthropic_api_key
    if (form.gemini_api_key) body.gemini_api_key = form.gemini_api_key
    try {
      await api.saveSettings(body); await reload()
      setForm((f) => ({ ...f, anthropic_api_key: '', gemini_api_key: '' }))
      setResult(await api.testAI())
    } catch (err) { setResult({ ok: false, message: err.message }) } finally { setBusy(false) }
  }
  async function remove(name) {
    if (!window.confirm('¿Borrar esta clave del PC?')) return
    await api.saveSettings({ [name]: '' }); reload()
  }
  const keyField = (name, label, help, placeholder) => (
    <label>{label}
      <div className="row">
        <input className="grow" type="password" autoComplete="off" value={form[name]} onChange={(e) => setForm({ ...form, [name]: e.target.value })}
          placeholder={s[name].configured ? `Guardada (${s[name].hint}) · escribe otra para cambiarla` : placeholder} />
        {s[name].configured && <button type="button" className="secondary" onClick={() => remove(name)}>Quitar</button>}
      </div>
      <span className="muted small">{help}</span>
    </label>
  )
  return (
    <form className="grid" onSubmit={save}>
      <p>{s.ai_active
        ? <>✅ IA activa: <strong>{s.ai_active === 'gemini' ? 'Gemini' : 'Claude'}</strong> ({s.ai_model_active}).</>
        : 'Añade una clave para que la app redacte tareas, genere rúbricas, mejore comentarios y evalúe entregas.'}</p>
      {keyField('anthropic_api_key', 'Clave de Claude (Anthropic)', 'Consíguela en console.anthropic.com → API Keys.', 'sk-ant-…')}
      {keyField('gemini_api_key', 'Clave de Gemini (Google)', 'Consíguela en aistudio.google.com → Get API key.', 'AIza…')}
      <div className="grid2">
        <label>Usar
          <select value={form.ai_provider} onChange={(e) => setForm({ ...form, ai_provider: e.target.value })}>
            <option value="auto">Automático (Claude si hay clave; si no, Gemini)</option>
            <option value="claude">Siempre Claude</option>
            <option value="gemini">Siempre Gemini</option>
          </select>
        </label>
        <label>Modelo (opcional)
          <input value={form.ai_model} onChange={(e) => setForm({ ...form, ai_model: e.target.value.trim() })} placeholder="Recomendado por defecto" />
        </label>
      </div>
      <div className="row"><button type="submit" disabled={busy}>{busy ? 'Guardando y probando…' : 'Guardar y probar'}</button>
        {s.ai_active && <button type="button" className="secondary" disabled={busy} onClick={async () => { setBusy(true); setResult(await api.testAI()); setBusy(false) }}>Probar</button>}</div>
      <Status result={result} />
      <p className="muted small">Las claves se guardan cifradas en el PC y nunca se muestran. El uso de la API tiene coste según tu proveedor.</p>
    </form>
  )
}

function SheetsSection({ s, reload }) {
  const [url, setUrl] = useState(s.sheets_url || '')
  const [secret, setSecret] = useState('')
  const [result, setResult] = useState(null)
  const [busy, setBusy] = useState(false)
  async function save(e) {
    e.preventDefault(); setBusy(true); setResult(null)
    try {
      await api.saveSettings({ sheets_url: url, ...(secret ? { sheets_secret: secret } : {}) })
      await reload(); setSecret(''); setResult(await api.testSheets())
    } catch (err) { setResult({ ok: false, message: err.message }) } finally { setBusy(false) }
  }
  async function copyScript() {
    const { code } = await api.sheetsScript()
    try { await navigator.clipboard.writeText(code); setResult({ ok: true, message: 'Código copiado: pégalo en Apps Script' }) }
    catch { setResult({ ok: false, message: 'No se pudo copiar: abre integraciones/google-sheets.gs en el PC' }) }
  }
  function randomSecret() {
    const a = new Uint8Array(18); crypto.getRandomValues(a)
    setSecret(btoa(String.fromCharCode(...a)).replace(/[^A-Za-z0-9]/g, ''))
  }
  return (
    <form className="grid" onSubmit={save}>
      <p>{s.sheets_configured ? '✅ Hoja de Google conectada.' : 'Conecta tu hoja de cálculo de Google para registrar las notas de la evaluación automática.'}</p>
      <ol className="small steps-list">
        <li>Abre tu hoja de Google → <em>Extensiones → Apps Script</em>. <button type="button" className="link" onClick={copyScript}>Copiar el código</button> y pégalo (sustituye lo que haya) → Guardar.</li>
        <li>Pulsa <button type="button" className="link" onClick={randomSecret}>generar un secreto</button>, cópialo y en Apps Script: <em>⚙ Configuración del proyecto → Propiedades del script → SECRET</em> = ese valor.</li>
        <li><em>Implementar → Nueva implementación → Aplicación web</em>, ejecutar como «Yo», acceso «Cualquier usuario» → copia la URL que termina en <code>/exec</code>.</li>
      </ol>
      <label>URL de la aplicación web<input type="url" value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://script.google.com/macros/s/…/exec" /></label>
      <label>Secreto<input value={secret} onChange={(e) => setSecret(e.target.value)} autoComplete="off"
        placeholder={s.sheets_secret.configured ? `Guardado (${s.sheets_secret.hint})` : 'El mismo que pusiste en Apps Script'} /></label>
      <div className="row"><button type="submit" disabled={busy}>{busy ? 'Probando…' : 'Guardar y probar'}</button></div>
      <Status result={result} />
    </form>
  )
}

export function SetupView() {
  const [s, setS] = useState(null)
  const [error, setError] = useState('')
  const reload = () => api.settings().then(setS).catch((e) => setError(e.message))
  useEffect(() => { reload() }, [])
  if (error) return <p className="error">{error}</p>
  if (!s) return <p className="spinner">Cargando ajustes…</p>
  return (
    <section className="setup">
      <h2>Ajustes</h2>
      <details className="panel" open={location.hostname === 'localhost' || location.hostname === '127.0.0.1'}>
        <summary>📱 Conectar la tablet</summary>
        <TabletSection />
      </details>
      <details className="panel" open={!s.ai_active}>
        <summary>🤖 Inteligencia artificial {s.ai_active && <span className="badge ok">Activa</span>}</summary>
        <AISection s={s} reload={reload} />
      </details>
      <details className="panel">
        <summary>📊 Hoja de Google {s.sheets_configured && <span className="badge ok">Conectada</span>}</summary>
        <SheetsSection s={s} reload={reload} />
      </details>
    </section>
  )
}
