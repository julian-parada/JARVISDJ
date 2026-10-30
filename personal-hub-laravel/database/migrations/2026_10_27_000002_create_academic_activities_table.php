<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

/**
 * Actividades académicas (parciales, entregas, exposiciones...).
 * Si tu módulo de universidad ya tiene una tabla equivalente, no corras
 * esta migración y apunta el modelo AcademicActivity a tu tabla.
 */
return new class extends Migration
{
    public function up(): void
    {
        if (Schema::hasTable('academic_activities')) {
            return;
        }

        Schema::create('academic_activities', function (Blueprint $table) {
            $table->id();
            $table->foreignId('user_id')->constrained()->cascadeOnDelete();
            $table->string('title');
            $table->string('subject')->nullable();          // materia
            $table->string('type', 30)->default('entrega');  // entrega, parcial, exposicion, quiz, otro
            $table->timestamp('due_at')->index();
            $table->text('notes')->nullable();
            $table->boolean('done')->default(false);
            $table->timestamps();

            $table->index(['user_id', 'due_at']);
        });
    }

    public function down(): void
    {
        Schema::dropIfExists('academic_activities');
    }
};
