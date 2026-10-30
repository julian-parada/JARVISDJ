<?php

namespace App\Services\Assistant;

use App\Models\Task;
use App\Models\User;
use Carbon\CarbonImmutable;
use Illuminate\Database\Eloquent\Builder;
use Illuminate\Support\Collection;

/**
 * Único punto que conoce la estructura real de la tabla `tasks`.
 * Los controladores y el asistente hablan en un "idioma neutro"
 * (pending/high/due_date) y aquí se traduce a tu esquema.
 */
class TaskRepository
{
    public function col(string $key): string
    {
        return config("assistant.tasks.$key", $key);
    }

    public function statusValue(string $neutral): string
    {
        return config("assistant.status_values.$neutral", $neutral);
    }

    public function priorityValue(string $neutral): string
    {
        return config("assistant.priority_values.$neutral", $neutral);
    }

    public function today(): CarbonImmutable
    {
        return CarbonImmutable::now(config('assistant.timezone'))->startOfDay();
    }

    public function forUser(User $user): Builder
    {
        return Task::query()->where('user_id', $user->id);
    }

    public function open(Builder $query): Builder
    {
        return $query->where($this->col('status'), '!=', $this->statusValue('completed'));
    }

    /**
     * @param  array{status?:string,priority?:string,due_from?:string,due_to?:string,overdue?:bool,q?:string,limit?:int}  $filters
     */
    public function search(User $user, array $filters): Collection
    {
        $query = $this->forUser($user);
        $due = $this->col('due_date');

        $status = $filters['status'] ?? 'open';
        if ($status === 'open') {
            $this->open($query);
        } elseif ($status !== 'all') {
            $query->where($this->col('status'), $this->statusValue($status));
        }

        if (! empty($filters['priority'])) {
            $query->where($this->col('priority'), $this->priorityValue($filters['priority']));
        }
        if (! empty($filters['due_from'])) {
            $query->whereDate($due, '>=', $filters['due_from']);
        }
        if (! empty($filters['due_to'])) {
            $query->whereDate($due, '<=', $filters['due_to']);
        }
        if (! empty($filters['overdue'])) {
            $this->open($query)->whereDate($due, '<', $this->today()->toDateString());
        }
        if (! empty($filters['q'])) {
            $term = '%'.mb_strtolower($filters['q']).'%';
            $title = $this->col('title');
            $query->whereRaw("LOWER($title) LIKE ?", [$term]);
        }

        $limit = min((int) ($filters['limit'] ?? config('assistant.max_results')), config('assistant.max_results'));

        return $query
            ->orderByRaw("$due IS NULL")   // primero las que tienen fecha
            ->orderBy($due)
            ->limit($limit)
            ->get();
    }

    public function create(User $user, array $data): Task
    {
        $task = new Task();
        $task->user_id = $user->id;
        $task->{$this->col('title')} = $data['title'];
        $task->{$this->col('description')} = $data['description'] ?? null;
        $task->{$this->col('priority')} = $this->priorityValue($data['priority'] ?? 'medium');
        $task->{$this->col('due_date')} = $data['due_date'] ?? null;
        $task->{$this->col('status')} = $this->statusValue('pending');
        $task->created_via = 'assistant';
        $task->save();

        return $task;
    }

    public function complete(Task $task): Task
    {
        $task->{$this->col('status')} = $this->statusValue('completed');
        $task->{$this->col('completed_at')} = now();
        $task->save();

        return $task;
    }

    public function findForUser(User $user, int $id): Task
    {
        return $this->forUser($user)->findOrFail($id);
    }

    /** Representación neutra que recibe el asistente. */
    public function present(Task $task): array
    {
        $statusMap = array_flip(config('assistant.status_values'));
        $priorityMap = array_flip(config('assistant.priority_values'));
        $rawStatus = $task->{$this->col('status')};
        $rawPriority = $task->{$this->col('priority')};
        $due = $task->{$this->col('due_date')};

        return [
            'id' => $task->id,
            'title' => $task->{$this->col('title')},
            'description' => $task->{$this->col('description')},
            'status' => $statusMap[$rawStatus] ?? $rawStatus,
            'priority' => $priorityMap[$rawPriority] ?? $rawPriority,
            'due_date' => $due ? CarbonImmutable::parse($due)->toDateString() : null,
            'overdue' => $due
                && ($statusMap[$rawStatus] ?? $rawStatus) !== 'completed'
                && CarbonImmutable::parse($due)->lt($this->today()),
        ];
    }
}
