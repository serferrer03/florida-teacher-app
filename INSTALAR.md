# Instalar Florida Teacher App (5 minutos)

## 1. En el PC (Windows), una sola vez

1. Instala **Python 3.12** (marca «Add python.exe to PATH») y **Node.js LTS**.
   Si ya los tienes, sáltate este paso; `Iniciar.bat` te avisa si falta alguno.
2. Descarga el proyecto:
   - Con Git: `git clone https://github.com/serferrer03/florida-teacher-app.git` y
     `git checkout claude/florida-oberta-fase-1-rbg897`.
   - Sin Git: en GitHub, elige la rama `claude/florida-oberta-fase-1-rbg897` →
     **Code → Download ZIP** y descomprímelo.
3. Doble clic en **`Iniciar.bat`**. La primera vez tarda unos minutos (instala todo) y Windows
   pide permiso para el firewall: acéptalo (solo redes privadas).
4. Se abre la app en el PC. Inicia sesión con tu cuenta de Florida (Office 365) y aprueba en
   Microsoft Authenticator si te lo pide.

Opcional: **`Inicio-automatico.bat`** para que arranque sola al encender el PC.

## 2. En la tablet (Android), una sola vez

1. Conecta la tablet a **la misma Wi-Fi** que el PC.
2. En el PC, abre la pestaña **Ajustes → 📱 Conectar la tablet**.
3. Con la cámara de la tablet:
   - Escanea el **QR 1** (certificado) e instálalo: *Ajustes de Android → Seguridad →
     Cifrado y credenciales → Instalar un certificado → Certificado de CA*.
   - Escanea el **QR 2**: la app se abre ya vinculada.
4. En Chrome, menú **⋮ → Instalar aplicación**. Ya tienes el icono en la pantalla de inicio.

## 3. Activar la inteligencia artificial (opcional, recomendado)

En **Ajustes → 🤖 Inteligencia artificial** pega una clave y pulsa «Guardar y probar»:
- **Claude**: console.anthropic.com → API Keys.
- **Gemini**: aistudio.google.com → Get API key.

Con la IA activa puedes:
- **Crear tareas describiéndolas en una frase** («✨ Crear con IA»).
- **Generar rúbricas.**
- **Mejorar la redacción** de los comentarios.
- **Programar la evaluación automática** al cierre de cada tarea. Revisas las notas antes de
  publicarlas.

Para registrar las notas en tu **hoja de Google**: **Ajustes → 📊 Hoja de Google** (3 pasos guiados).

> Antes de usar la evaluación con IA, lee [PRIVACIDAD.md](PRIVACIDAD.md) §7: necesitas la
> autorización expresa de Florida para enviar entregas al proveedor de IA y notas a Google.

## Actualizar

- Con Git: doble clic en **`Actualizar.bat`**.
- Sin Git: descarga de nuevo el ZIP y copia encima, **conservando** la carpeta `backend\data`.

## Si algo falla

- **La tablet no conecta:** confirma la misma Wi-Fi y que la ventana negra de la app sigue
  abierta en el PC.
- **Florida Oberta pide reconectar:** pulsa «Conectar» y aprueba en Authenticator.
- **Para ver qué hace el navegador:** pon `MOODLE_HEADLESS=false` en `backend\.env`. Para
  guardar capturas de los errores, pon `DIAGNOSTICS=true`.
