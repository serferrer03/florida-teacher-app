import React from 'react'
import { createRoot } from 'react-dom/client'
import App from './App.jsx'
import './styles.css'
import { setToken } from './api.js'

const m = window.location.hash.match(/code=([A-Za-z0-9]+)/)
if (m) {
  setToken(m[1].toUpperCase())
  history.replaceState(null, '', window.location.pathname)  // borra el código de la barra
}

createRoot(document.getElementById('root')).render(<App />)
