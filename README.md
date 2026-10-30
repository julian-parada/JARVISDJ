# 🤖 JARVIS · V1

Asistente personal con IA (Claude) que gestiona tus **tareas, actividades de la universidad y objetivos** conversando por **terminal** o **Telegram**.

- Funciona solo con una API key de Anthropic: guarda todo en su propia base de datos.
- Opcionalmente se conecta a **Personal Hub** (Laravel) para usar tus datos reales.
- Es multi-usuario desde el inicio, con auditoría, medición de consumo y credenciales cifradas.

---

## ⚡ Inicio rápido (Windows)

### Necesitas
1. **Python 3.11 o superior**: https://www.python.org/downloads/
   Al instalarlo, ⚠️ marca **"Add python.exe to PATH"**.
2. Una **API key de Anthropic**: https://console.anthropic.com/settings/keys (con saldo cargado).

### Pasos
1. Descarga el repositorio (**Code → Download ZIP**) o clónalo:
   ```bash
   git clone https://github.com/julian-parada/JARVISDJ.git
   ```
2. Entra a la carpeta `orchestrator` y haz **doble clic en `instalar.bat`**.
   - Instala todo y te hace unas preguntas: tu API key, tu nombre y si quieres Telegram.
   - Al final prueba la conexión con Claude.
3. Haz **doble clic en `iniciar.bat`** y háblale:

```
tú › crea una tarea: estudiar para el parcial de cálculo, prioridad alta, para el viernes
jarvis › Listo, creé «Estudiar para el parcial de cálculo» para el viernes 31, prioridad alta.

tú › tengo exposición de redes el martes a las 10am
jarvis › Anotada la exposición de Redes para el martes 3 a las 10:00.

tú › quiero ahorrar 500 mil para diciembre, ya llevo 120 mil
jarvis › Creé el objetivo «Ahorro diciembre»: vas en 24 %.

tú › ¿qué tengo pendiente hoy?
jarvis › ...
```

> En Linux/macOS: `cd orchestrator && ./instalar.sh` y luego `.venv/bin/jarvis chat`.

---

## 📱 Telegram (opcional)

1. En Telegram habla con **@BotFather**, envía `/newbot` y copia el token.
2. Si no lo pusiste durante la instalación, vuelve a ejecutar `instalar.bat` (o `jarvis setup`) y pégalo.
3. Abre una terminal en `orchestrator` y genera un código:
   ```bash
   .venv\Scripts\jarvis link-code
   ```
4. Haz doble clic en **`telegram.bat`** y déjalo abierto.
5. En tu bot envía `/vincular CODIGO`. Listo, ya puedes escribirle desde el iPhone.

| Comando del bot | Qué hace |
|---|---|
| `/vincular CODIGO` | Une este chat a tu cuenta |
| `/nuevo` | Reinicia la conversación |
| `/desvincular` | Desconecta este chat |

> El bot solo responde mientras `telegram.bat` esté abierto en tu PC. Para tenerlo 24/7, usa la sección Docker en un servidor.

---

## 🧰 Qué sabe hacer

| Herramienta | Permiso | Ejemplo |
|---|---|---|
| `resumen_dia` | 🟢 lectura | «¿qué tengo hoy?» |
| `listar_tareas` | 🟢 lectura | «¿qué tareas de alta prioridad tengo?» |
| `crear_tarea` | 🟡 escritura | «recuérdame pagar el recibo el lunes» |
| `completar_tarea` | 🟡 escritura | «ya terminé el informe» |
| `eliminar_tarea` | 🔴 sensible | «borra la tarea del café» → pide confirmación |
| `listar_actividades` | 🟢 lectura | «¿qué entregas tengo esta semana?» |
| `crear_actividad` | 🟡 escritura | «parcial de cálculo el jueves a las 8» |
| `estado_objetivos` | 🟢 lectura | «¿cómo voy con el ahorro?» |
| `crear_objetivo` | 🟡 escritura | «quiero leer 10 libros este año» |
| `registrar_avance_objetivo` | 🟡 escritura | «ahorré 50 mil más» |

**Seguridad:** el modelo solo puede usar estas herramientas. Las acciones sensibles quedan pendientes hasta que confirmes **en un mensaje posterior**, porque el modelo no puede autoconfirmarse, y la confirmación vence a los 10 minutos.

---

## 🛠️ Comandos útiles

Desde la carpeta `orchestrator`, con el prefijo `.venv\Scripts\` en Windows:

| Comando | Para qué |
|---|---|
| `jarvis setup` | Configurar o reconfigurar |
| `jarvis estado` | Revisar que todo esté bien (prueba Claude y Personal Hub) |
| `jarvis chat` | Conversar por terminal |
| `jarvis telegram` | Arrancar el bot |
| `jarvis link-code` | Código para vincular Telegram |
| `jarvis settings --prompt-extra "Sé directo y llámame Julian"` | Personalizar tono |
| `jarvis settings --model claude-haiku-5-5` | Usar un modelo más barato |
| `jarvis logs` | Ver las últimas acciones que ejecutó |
| `jarvis usage` | Ver tokens consumidos |

---

## 🔗 Conectar Personal Hub (Laravel)

Por defecto JARVIS guarda los datos en `orchestrator/jarvis.db`. Para usar tu Personal Hub:

1. Sigue [`personal-hub-laravel/INSTALAR.md`](personal-hub-laravel/INSTALAR.md): copias los archivos, migras y generas un token.
2. Conéctalo:
   ```bash
   jarvis set-hub --url http://localhost:8000 --token "5|aBcD..."
   ```
3. `jarvis estado` debe mostrar `[OK] Personal Hub responde`.

Para volver al modo local: `jarvis unset-hub`.

---

## 🏗️ Arquitectura

```
Terminal / Telegram  (Fase 2: voz)
          │
          ▼
   Orquestador (Python) ──► Claude API (decide qué herramienta usar)
          │
          ▼  solo herramientas registradas, con nivel de permiso + log
   Proveedor "tasks"
     ├── Modo local (SQLite / PostgreSQL)
     └── Personal Hub API (Laravel + Sanctum)
```

```
JARVISDJ/
├── orchestrator/            ← el asistente (Python)
│   ├── jarvis/
│   │   ├── orchestrator.py  ← ciclo Claude ↔ herramientas, permisos, confirmaciones
│   │   ├── tools/           ← herramientas (tasks.py, system.py)
│   │   ├── connectors/      ← local_store.py, personal_hub.py
│   │   ├── channels/        ← terminal.py, telegram_bot.py
│   │   ├── models.py        ← tablas (todas con user_id)
│   │   └── cli.py           ← comando `jarvis`
│   ├── tests/
│   ├── instalar.bat · iniciar.bat · telegram.bat
│   └── Dockerfile · docker-compose.yml
└── personal-hub-laravel/    ← archivos para tu proyecto Laravel
```

### Agregar una capacidad (luces, portátil…)
1. Crea un conector en `jarvis/connectors/` y regístralo en `CONNECTOR_BUILDERS`.
2. Crea sus herramientas en `jarvis/tools/` heredando de `Tool`, con `provider` y `permission`.
3. Regístralas en `default_registry()`.

El orquestador no se modifica.

---

## 🐳 Servidor 24/7 (Docker)

```bash
cd orchestrator
cp .env.example .env              # completa ANTHROPIC_API_KEY, TELEGRAM_BOT_TOKEN y JARVIS_MASTER_KEY
docker compose up -d --build
docker compose exec bot jarvis create-user --name Julian
docker compose exec bot jarvis link-code
```

## 🧪 Pruebas

```bash
cd orchestrator
.venv\Scripts\pip install -e ".[dev]"
.venv\Scripts\pytest
```

GitHub Actions las corre en Windows y Linux en cada push.

---

## 🗺️ Roadmap

- [x] **Fase 1:** cerebro y pendientes (terminal + Telegram)
- [ ] **Fase 2:** voz (Whisper local + TTS)
- [ ] **Fase 3:** luces (Home Assistant)
- [ ] **Fase 4:** portátil (agente con lista blanca)
- [ ] **Fase 5:** resumen matutino y recordatorios proactivos

**Antes de venderlo:** nombre propio (JARVIS es marca de Marvel), migraciones con Alembic, política de tratamiento de datos (Ley 1581 de 2012), registro público y pagos.
