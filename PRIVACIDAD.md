# Protección de datos — Florida Teacher App

> **Aviso importante.** Este documento describe las medidas técnicas que incorpora la app y una
> guía práctica basada en el RGPD (Reglamento UE 2016/679) y la LOPDGDD (Ley Orgánica 3/2018).
> **No es asesoramiento jurídico.** Ninguna app puede garantizar por sí sola que no tengas ningún
> problema: eso depende también de cómo la uses y de las normas internas de Florida. El paso que
> más te protege es el de la sección 1: **pide el visto bueno por escrito a Florida.**

## 1. Antes de usarla: autorización de Florida

Florida Universitària es la **responsable del tratamiento** de los datos de Florida Oberta
(los tuyos como docente y, sobre todo, los del alumnado). Tú accedes a ellos como personal de
Florida y siguiendo sus instrucciones. Por eso:

1. **Consulta al Delegado/a de Protección de Datos (DPD) y al servicio informático de Florida**
   antes de usar la app con tu cuenta real. Explícales en una frase qué hace: «una herramienta
   personal que, desde mi PC, inicia sesión en Florida Oberta con mi cuenta de Microsoft
   (con mi verificación en dos pasos) para consultar mis cursos y, más adelante, crear tareas».
   Puedes adjuntarles este documento.
2. Pregunta en concreto por:
   - si la **política de uso aceptable** permite automatizar el navegador sobre Florida Oberta;
   - si puedes **guardar la contraseña** institucional cifrada en tu PC (la app no lo hace salvo
     que marques «Recordar contraseña»);
   - si puedes tratar **datos del alumnado** en un dispositivo propio (necesario a partir de la
     Fase 4: entregas y calificaciones).
3. Guarda su respuesta. Si te dicen que no, no la uses con la cuenta institucional.

## 2. Qué datos trata la app

| Dato | Dónde | Protección | Cuánto tiempo |
|------|-------|------------|---------------|
| Tu usuario (correo institucional) | `backend/data/app.db` | Archivo solo legible por tu usuario del PC | Hasta que lo borres |
| Tu contraseña | `app.db` | **Solo si marcas «Recordar contraseña»**. Cifrada (Fernet: AES-128 + HMAC-SHA256) | Hasta «Cerrar sesión» o «Borrar todos mis datos» |
| Cookies de sesión de Moodle y Microsoft | `backend/data/session.enc` | Cifradas (Fernet) | Se borran solas a los `SESSION_MAX_DAYS` días (14 por defecto) |
| Lista de tus cursos (nombre, código, categoría, enlace) | `app.db` | Archivo solo legible por tu usuario del PC | Se sustituye en cada sincronización |
| Clave de cifrado | `backend/data/secret.key` | Permisos 600 | Se destruye con «Borrar todos mis datos» |
| Código de acceso de la tablet | `backend/data/access_code` y en la tablet | Permisos 600 | Hasta que lo cambies |

**No se tratan** en la Fase 1: datos del alumnado, códigos de verificación de Microsoft (se usan
una vez y se descartan), analítica, telemetría, publicidad ni servicios de terceros. La app no
tiene servidor en Internet: todo ocurre entre tu tablet, tu PC, Florida Oberta y Microsoft.

## 3. Medidas incorporadas (privacidad desde el diseño, art. 25 y seguridad, art. 32 RGPD)

- **Minimización (art. 5.1.c):** solo se guarda lo imprescindible para listar tus cursos.
  La contraseña **no** se guarda por defecto.
- **Limitación del plazo (art. 5.1.e):** la sesión cifrada caduca sola; la lista de cursos se
  reemplaza en cada sincronización.
- **Cifrado en reposo** de contraseña y cookies; archivos de datos con permisos solo para tu
  usuario (`data/` 700, archivos 600). Las cookies antiguas sin cifrar de la primera versión se
  eliminan automáticamente al arrancar.
- **Verificación en dos pasos respetada:** la app nunca salta ni automatiza la MFA de Microsoft.
  Te muestra el número o te pide el código, y eres tú quien aprueba en tu móvil. Si la sesión
  caduca y Microsoft vuelve a pedir MFA, la app se detiene y te pide reconectar.
- **Control de acceso en la red local:** toda la API exige un código de emparejamiento aleatorio;
  tras 5 intentos fallidos la IP queda bloqueada 5 minutos.
- **Sin terceros:** sin CDN, fuentes externas, analítica ni CORS abierto; cabeceras de seguridad
  (CSP, `no-store` en la API, `X-Frame-Options: DENY`) y sin documentación pública de la API.
- **La tablet no guarda datos de Florida Oberta en caché:** el service worker nunca cachea `/api`.
- **Registros sin datos personales:** los logs no incluyen usuario, contraseña ni contenido de
  Moodle.
- **Derechos de acceso y supresión:** la pestaña *Privacidad* muestra qué hay guardado; *Cerrar
  sesión* borra cookies y contraseña; *Borrar todos mis datos* borra todo y destruye la clave de
  cifrado (lo cifrado antes queda irrecuperable).

## 4. Lo que te toca a ti (medidas organizativas)

- [ ] Autorización de Florida (sección 1).
- [ ] **Cifrado de disco** en el PC: BitLocker (Windows), FileVault (macOS) o LUKS (Linux).
- [ ] Usuario del PC con contraseña, bloqueo automático de pantalla y sistema actualizado.
- [ ] **Tablet con bloqueo** (PIN/huella) y sin compartir con otras personas o alumnado.
- [ ] Usar la app solo en **tu red de casa o del centro**, nunca en Wi-Fi públicas. En el
      firewall, permite el puerto 8000 solo en redes privadas. No lo abras a Internet (ni
      redirección de puertos en el router).
- [ ] No copiar `backend/data/` a USB, nubes personales ni repositorios (está en `.gitignore`).
- [ ] No compartir el código de acceso de la tablet.

## 5. Si pierdes el PC o la tablet, o sospechas un acceso indebido

1. Desde otro dispositivo, **cambia la contraseña de Microsoft** y cierra todas las sesiones
   (Cuenta de Microsoft → Seguridad → cerrar sesión en todas partes / «Mis inicios de sesión»).
2. Si conservas el PC: pestaña *Privacidad* → *Borrar todos mis datos*, o borra `backend/data/`.
   Si perdiste la tablet: borra `backend/data/access_code` y reinicia el servidor (se genera un
   código nuevo y la tablet perdida deja de tener acceso).
3. **Avisa cuanto antes al DPD de Florida.** Si hubiera datos personales afectados, el responsable
   (Florida) debe valorar la notificación a la autoridad de control en un plazo de 72 horas
   (art. 33 RGPD), y para eso necesita saberlo enseguida.

## 6. Datos del alumnado (Fase 4: entregas y calificación)

Activada con la autorización de Florida. Cómo se tratan:

- **Qué se lee:** nombre, estado de la entrega (entregado, retraso), nota, fecha de última
  modificación, texto en línea, comentarios y archivos entregados de **una tarea**, solo cuando
  abres «Entregas y notas». No se leen correos ni otros campos de identidad.
- **Dónde se guarda: en ningún sitio.** Se piden a Florida Oberta en cada consulta y solo viven en
  la memoria de la pantalla de la tablet. No van a la base de datos, ni a disco, ni a los
  registros (la consola solo anota recuentos) ni a la caché (`Cache-Control: no-store`, el service
  worker nunca cachea `/api`).
- **Archivos entregados:** el PC los pide a Florida Oberta y los pasa a la tablet sin escribirlos en
  disco. Al pulsar «⬇» se descargan **en la tablet**: bórralos de la carpeta Descargas cuando ya no
  los necesites.
- **Notas y comentarios:** se escriben directamente en Florida Oberta (sistema oficial), con
  confirmación previa; la app no guarda copia.
- La pestaña *Privacidad* lo refleja en «No se guarda».

Recomendaciones: no califiques con la pantalla a la vista de terceros, cierra la app al terminar
y no hagas capturas con datos del alumnado.
