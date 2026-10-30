# Integrar la API del asistente en Personal Hub

Estos archivos se copian sobre tu proyecto Laravel existente. No reemplazan nada tuyo.

## 1. Copiar archivos

Copia respetando las carpetas:

```
config/assistant.php
routes/assistant.php
app/Services/Assistant/TaskRepository.php
app/Http/Controllers/Assistant/*.php
app/Console/Commands/CreateAssistantToken.php
app/Models/AcademicActivity.php
app/Models/Goal.php
database/migrations/2026_10_27_*.php
```

## 2. Registrar las rutas

En `routes/api.php`, al final:

```php
Route::prefix('assistant')->group(base_path('routes/assistant.php'));
```

## 3. Registrar el middleware de abilities y el rate limit

En `bootstrap/app.php` (Laravel 11/12), dentro de `->withMiddleware(...)`:

```php
$middleware->alias([
    'abilities' => \Laravel\Sanctum\Http\Middleware\CheckAbilities::class,
    'ability'   => \Laravel\Sanctum\Http\Middleware\CheckForAnyAbility::class,
]);
```

En `app/Providers/AppServiceProvider.php`, dentro de `boot()`:

```php
use Illuminate\Cache\RateLimiting\Limit;
use Illuminate\Support\Facades\RateLimiter;

RateLimiter::for('assistant', fn ($request) =>
    Limit::perMinute(60)->by($request->user()?->id ?: $request->ip())
);
```

## 4. Ajustar a tu tabla `tasks`

Abre `config/assistant.php` y revisa:

- `tasks` → nombres reales de tus columnas (`title`, `status`, ...).
- `status_values` → si guardas `pendiente`/`completada` en vez de `pending`/`completed`, cámbialo ahí.
- `priority_values` → igual para prioridad.

El código asume que tu modelo es `App\Models\Task` y tiene columna `user_id`.

## 5. Migrar

```bash
php artisan migrate
```

Las migraciones solo agregan lo que falta; si ya tienes `due_date` o una tabla `goals`, la saltan.
Si tu módulo de universidad ya tiene su propia tabla de actividades, **no** uses `create_academic_activities_table`: borra esa migración y ajusta `$table` en el modelo `AcademicActivity`.

## 6. Generar el token del asistente

```bash
php artisan assistant:token tu@correo.com
```

Copia el token: lo usarás al registrar tu usuario en el orquestador.
Con `--delete` el token también podrá borrar tareas (el asistente igual te pedirá confirmación).

## 7. Probar en Thunder Client

```
GET  http://localhost:8000/api/assistant/summary
Authorization: Bearer <token>
Accept: application/json
```

| Método | Ruta | Ability |
|---|---|---|
| GET | `/api/assistant/summary?date=YYYY-MM-DD` | read |
| GET | `/api/assistant/tasks?status=open&priority=high&due_from=&due_to=&overdue=1&q=informe` | read |
| GET | `/api/assistant/activities?days=7&subject=` | read |
| GET | `/api/assistant/goals?q=ahorro` | read |
| POST | `/api/assistant/tasks` `{title, description?, priority?, due_date?}` | write |
| PATCH | `/api/assistant/tasks/{id}/complete` | write |
| POST | `/api/assistant/activities` `{title, due_at, subject?, type?, notes?}` | write |
| POST | `/api/assistant/goals` `{title, target, unit?, current?, deadline?}` | write |
| PATCH | `/api/assistant/goals/{id}/progress` `{add}` o `{set}` | write |
| DELETE | `/api/assistant/tasks/{id}` | delete |
