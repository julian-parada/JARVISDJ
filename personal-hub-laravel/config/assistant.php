<?php

/*
|--------------------------------------------------------------------------
| Configuración de la API del asistente
|--------------------------------------------------------------------------
| Todo lo que puede variar entre tu instalación y la de un futuro cliente
| vive aquí, no en los controladores. Si tu tabla `tasks` usa otros nombres
| o valores, ajústalos en este archivo y el resto del código sigue igual.
*/

return [

    // Zona horaria con la que se calculan "hoy", "esta semana", etc.
    'timezone' => env('ASSISTANT_TIMEZONE', 'America/Bogota'),

    // Abilities de Sanctum que llevan los tokens del asistente.
    'abilities' => [
        'read' => 'assistant:read',
        'write' => 'assistant:write',
        'delete' => 'assistant:delete',
    ],

    // Nombres de columnas de tu tabla `tasks`.
    'tasks' => [
        'title' => 'title',
        'description' => 'description',
        'status' => 'status',
        'priority' => 'priority',
        'due_date' => 'due_date',
        'completed_at' => 'completed_at',
    ],

    // Valores que usa tu app para estado y prioridad.
    // Clave = valor que entiende el asistente, valor = lo que guarda tu BD.
    'status_values' => [
        'pending' => 'pending',
        'in_progress' => 'in_progress',
        'completed' => 'completed',
    ],

    'priority_values' => [
        'low' => 'low',
        'medium' => 'medium',
        'high' => 'high',
    ],

    // Máximo de registros que devuelve una consulta (protege tokens de IA).
    'max_results' => 25,
];
