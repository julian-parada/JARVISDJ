<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

/**
 * Agrega a `tasks` solo las columnas que el asistente necesita y que aún
 * no existan. Es seguro correrla aunque ya tengas algunas de ellas.
 */
return new class extends Migration
{
    public function up(): void
    {
        Schema::table('tasks', function (Blueprint $table) {
            if (! Schema::hasColumn('tasks', 'priority')) {
                $table->string('priority', 20)->default('medium')->index();
            }
            if (! Schema::hasColumn('tasks', 'due_date')) {
                $table->date('due_date')->nullable()->index();
            }
            if (! Schema::hasColumn('tasks', 'completed_at')) {
                $table->timestamp('completed_at')->nullable();
            }
            if (! Schema::hasColumn('tasks', 'created_via')) {
                // web | assistant — sirve para métricas y auditoría
                $table->string('created_via', 20)->default('web');
            }
        });
    }

    public function down(): void
    {
        Schema::table('tasks', function (Blueprint $table) {
            if (Schema::hasColumn('tasks', 'created_via')) {
                $table->dropColumn('created_via');
            }
        });
    }
};
