# Despliegue: Neon (base de datos) + Render (aplicación)

La aplicación (backend y frontend) se publica como **un solo servicio web** en Render. Los datos, incluidos los
archivos que suben los estudiantes, viven en **Neon (PostgreSQL)**, así que no se pierden cuando Render reinicia.

## 1. Crear la base de datos en Neon
1. Entra a https://neon.com y crea una cuenta (sirve iniciar sesión con GitHub o Google).
2. **Create project**: pon un nombre (p. ej. `asesor-pedagogico`), deja la versión de Postgres por defecto y elige una
   región cercana a Render (p. ej. *AWS US East (N. Virginia)* si tu servicio de Render está en Virginia).
3. En el panel del proyecto pulsa **Connect**. Activa **Connection pooling** (la cadena debe tener `-pooler` en el host)
   y copia la cadena de conexión. Se ve así:
   ```
   postgresql://USUARIO:CONTRASEÑA@ep-xxxx-pooler.us-east-2.aws.neon.tech/neondb?sslmode=require
   ```
4. No hay que crear tablas: la aplicación las crea sola al arrancar.

Notas del plan gratuito de Neon: no pide tarjeta, la base se **suspende tras ~5 minutos sin uso** y la primera
consulta después tarda un instante en despertarla. El almacenamiento es limitado (unos cientos de MB, revisa
https://neon.com/pricing); por eso el límite de subida por archivo es de 10 MB.

## 2. Subir el código a GitHub
```powershell
git add .
git commit -m "Despliegue con Neon"
git push origin main
```
Comprueba con `git status` que **no** se suban `.env`, `*.db` ni `backend/storage/evidencias/`.

## 3. Publicar en Render
**Opción A (recomendada): Blueprint**
1. En https://dashboard.render.com: **New → Blueprint** y elige tu repositorio. Render lee `render.yaml`.
2. Te pedirá los valores marcados como secretos: `DATABASE_URL` (la cadena de Neon), `DOCENTE_EMAIL`,
   `DOCENTE_PASSWORD` y `LLM_API_KEY`. `JWT_SECRET` lo genera Render.
3. Pulsa **Apply**.

**Opción B: manual** (**New → Web Service**)
- Build Command: `pip install -r requirements.txt`
- Start Command: `cd backend && uvicorn app.main:app --host 0.0.0.0 --port $PORT`
- Health Check Path: `/api/health`
- Variables de entorno: las de la tabla de abajo.

| Variable | Valor |
|---|---|
| `PYTHON_VERSION` | `3.12.8` |
| `APP_ENV` | `production` |
| `JWT_SECRET` | cadena aleatoria larga (`python -c "import secrets; print(secrets.token_urlsafe(48))"`) |
| `DATABASE_URL` | la cadena **pooled** de Neon |
| `DOCENTE_EMAIL` / `DOCENTE_PASSWORD` | tus credenciales de docente (se crea la cuenta al arrancar) |
| `LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL` | tu proveedor de IA (ver README) |

## 4. Verificar
- Abre `https://TU-SERVICIO.onrender.com/api/health`: debe responder `{"status":"ok",...}`.
- Abre la URL principal e inicia sesión con `DOCENTE_EMAIL` / `DOCENTE_PASSWORD`.
- En los **Logs** de Render deben aparecer las líneas de arranque sin errores.

## Problemas frecuentes
| Error en los logs | Causa |
|---|---|
| `Falta JWT_SECRET` | No definiste la variable `JWT_SECRET`. |
| `DATABASE_URL tiene un formato inválido` | Comillas, espacios o corchetes en el valor. Debe ser la URL tal cual. |
| `password authentication failed` | Contraseña o usuario incorrectos: copia de nuevo la cadena desde **Connect** en Neon. |
| `could not translate host name` / `timeout` | El host está mal copiado o Neon estaba despertando: reintenta. |
| La primera visita tarda ~1 minuto | El plan gratuito de Render duerme el servicio sin tráfico. |

Si cambias la contraseña de la base en Neon, actualiza `DATABASE_URL` en Render.
