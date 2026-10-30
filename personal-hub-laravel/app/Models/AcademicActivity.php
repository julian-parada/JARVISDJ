<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Builder;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;

class AcademicActivity extends Model
{
    protected $fillable = ['user_id', 'title', 'subject', 'type', 'due_at', 'notes', 'done'];

    protected $casts = [
        'due_at' => 'datetime',
        'done' => 'boolean',
    ];

    public function user(): BelongsTo
    {
        return $this->belongsTo(User::class);
    }

    public function scopeUpcoming(Builder $query): Builder
    {
        return $query->where('done', false)->where('due_at', '>=', now()->startOfDay());
    }
}
