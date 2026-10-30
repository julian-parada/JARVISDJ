<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

/**
 * Objetivos con progreso medible (ahorro, horas de estudio, etc.).
 */
return new class extends Migration
{
    public function up(): void
    {
        if (Schema::hasTable('goals')) {
            return;
        }

        Schema::create('goals', function (Blueprint $table) {
            $table->id();
            $table->foreignId('user_id')->constrained()->cascadeOnDelete();
            $table->string('title');
            $table->decimal('target_value', 14, 2);
            $table->decimal('current_value', 14, 2)->default(0);
            $table->string('unit', 30)->default('COP');   // COP, horas, km, libros...
            $table->date('deadline')->nullable();
            $table->boolean('active')->default(true);
            $table->timestamps();

            $table->index(['user_id', 'active']);
        });
    }

    public function down(): void
    {
        Schema::dropIfExists('goals');
    }
};
