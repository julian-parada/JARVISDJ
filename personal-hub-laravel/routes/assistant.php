<?php

/*
|--------------------------------------------------------------------------
| Rutas de la API del asistente (JARVIS)
|--------------------------------------------------------------------------
| Se cargan desde routes/api.php con:
|
|     Route::prefix('assistant')->group(base_path('routes/assistant.php'));
|
| Quedan bajo /api/assistant/... y requieren un token de Sanctum con
| abilities específicas (ver comando `php artisan assistant:token`).
*/

use App\Http\Controllers\Assistant\ActivityController;
use App\Http\Controllers\Assistant\GoalController;
use App\Http\Controllers\Assistant\SummaryController;
use App\Http\Controllers\Assistant\TaskController;
use Illuminate\Support\Facades\Route;

Route::middleware(['auth:sanctum', 'throttle:assistant'])->group(function () {

    // Lectura
    Route::middleware('abilities:assistant:read')->group(function () {
        Route::get('/summary', [SummaryController::class, 'show']);
        Route::get('/tasks', [TaskController::class, 'index']);
        Route::get('/activities', [ActivityController::class, 'index']);
        Route::get('/goals', [GoalController::class, 'index']);
    });

    // Escritura simple
    Route::middleware('abilities:assistant:write')->group(function () {
        Route::post('/tasks', [TaskController::class, 'store']);
        Route::patch('/tasks/{id}/complete', [TaskController::class, 'complete'])->whereNumber('id');
        Route::post('/activities', [ActivityController::class, 'store']);
        Route::post('/goals', [GoalController::class, 'store']);
        Route::patch('/goals/{id}/progress', [GoalController::class, 'progress'])->whereNumber('id');
    });

    // Sensible
    Route::middleware('abilities:assistant:delete')->group(function () {
        Route::delete('/tasks/{id}', [TaskController::class, 'destroy'])->whereNumber('id');
    });
});
