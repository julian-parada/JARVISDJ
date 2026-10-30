<?php

namespace App\Console\Commands;

use App\Models\User;
use Illuminate\Console\Command;

/**
 * Crea un token de Sanctum exclusivo para el asistente.
 *
 *   php artisan assistant:token tu@correo.com
 *   php artisan assistant:token tu@correo.com --delete   (incluye borrar tareas)
 *   php artisan assistant:token tu@correo.com --revoke   (revoca los tokens previos)
 */
class CreateAssistantToken extends Command
{
    protected $signature = 'assistant:token {email} {--delete : Permite borrar tareas} {--revoke : Revoca tokens anteriores del asistente}';

    protected $description = 'Genera un token con permisos limitados para el asistente JARVIS';

    public function handle(): int
    {
        $user = User::where('email', $this->argument('email'))->first();

        if (! $user) {
            $this->error('No existe un usuario con ese correo.');

            return self::FAILURE;
        }

        if ($this->option('revoke')) {
            $count = $user->tokens()->where('name', 'jarvis-assistant')->delete();
            $this->info("Tokens anteriores revocados: $count");
        }

        $abilities = [config('assistant.abilities.read'), config('assistant.abilities.write')];
        if ($this->option('delete')) {
            $abilities[] = config('assistant.abilities.delete');
        }

        $token = $user->createToken('jarvis-assistant', $abilities)->plainTextToken;

        $this->newLine();
        $this->line('Abilities: '.implode(', ', $abilities));
        $this->warn('Copia este token ahora, no se volverá a mostrar:');
        $this->line($token);

        return self::SUCCESS;
    }
}
