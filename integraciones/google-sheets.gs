/**
 * Florida Teacher App → Google Sheets
 * Pega este código en tu hoja: Extensiones → Apps Script → (borra lo que haya) → pega → Guardar.
 * 1) Configuración del proyecto (⚙) → Propiedades del script → Añadir: SECRET = una contraseña larga
 *    (la misma que pondrás en GOOGLE_SHEETS_SECRET en backend/.env).
 * 2) Implementar → Nueva implementación → Tipo: Aplicación web → Ejecutar como: Yo →
 *    Quién tiene acceso: Cualquier usuario → Implementar → autoriza → copia la URL /exec
 *    en GOOGLE_SHEETS_WEBHOOK_URL de backend/.env.
 * Sin el secreto correcto nadie puede escribir en la hoja.
 */
const SHEET_NAME = 'Evaluaciones';
const HEADER = ['Curso', 'Tarea', 'Alumno', 'Nota', 'Observación', 'Estado', 'Actualizado'];

function doPost(e) {
  const out = (obj) => ContentService.createTextOutput(JSON.stringify(obj)).setMimeType(ContentService.MimeType.JSON);
  let body;
  try { body = JSON.parse(e.postData.contents); } catch (err) { return out({ ok: false, error: 'JSON no válido' }); }
  const secret = PropertiesService.getScriptProperties().getProperty('SECRET');
  if (!secret || body.secret !== secret) return out({ ok: false, error: 'secreto incorrecto' });

  const lock = LockService.getScriptLock();
  lock.waitLock(30000);
  try {
    const ss = SpreadsheetApp.getActiveSpreadsheet();
    const sh = ss.getSheetByName(SHEET_NAME) || ss.insertSheet(SHEET_NAME);
    if (sh.getLastRow() === 0) { sh.appendRow(HEADER); sh.setFrozenRows(1); }
    const values = sh.getDataRange().getValues();
    const index = {};
    for (let i = 1; i < values.length; i++) index[values[i][0] + '|' + values[i][1] + '|' + values[i][2]] = i + 1;
    (body.rows || []).forEach((r) => {
      const row = [r.curso, r.tarea, r.alumno, r.nota, r.observacion, r.estado, new Date()];
      const key = r.curso + '|' + r.tarea + '|' + r.alumno;
      if (index[key]) sh.getRange(index[key], 1, 1, row.length).setValues([row]);
      else { sh.appendRow(row); index[key] = sh.getLastRow(); }
    });
  } finally {
    lock.releaseLock();
  }
  return out({ ok: true, rows: (body.rows || []).length });
}
