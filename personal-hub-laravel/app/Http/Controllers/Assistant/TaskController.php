<?php

namespace App\Http\Controllers\Assistant;

use App\Http\Controllers\Controller;
use App\Services\Assistant\TaskRepository;
use Illuminate\Http\JsonResponse;
use Illuminate\Http\Request;
use Illuminate\Validation\Rule;

class TaskController extends Controller
{
    public function __construct(private TaskRepository $tasks) {}

    /** GET /api/assistant/tasks */
    public function index(Request $request): JsonResponse
    {
        $filters = $request->validate([
            'status' => ['nullable', Rule::in(['open', 'all', 'pending', 'in_progress', 'completed'])],
            'priority' => ['nullable', Rule::in(['low', 'medium', 'high'])],
            'due_from' => ['nullable', 'date'],
            'due_to' => ['nullable', 'date'],
            'overdue' => ['nullable', 'boolean'],
            'q' => ['nullable', 'string', 'max:100'],
            'limit' => ['nullable', 'integer', 'min:1', 'max:'.config('assistant.max_results')],
        ]);

        $items = $this->tasks->search($request->user(), $filters)
            ->map(fn ($t) => $this->tasks->present($t))
            ->values();

        return response()->json(['count' => $items->count(), 'tasks' => $items]);
    }

    /** POST /api/assistant/tasks */
    public function store(Request $request): JsonResponse
    {
        $data = $request->validate([
            'title' => ['required', 'string', 'max:255'],
            'description' => ['nullable', 'string', 'max:2000'],
            'priority' => ['nullable', Rule::in(['low', 'medium', 'high'])],
            'due_date' => ['nullable', 'date'],
        ]);

        $task = $this->tasks->create($request->user(), $data);

        return response()->json(['task' => $this->tasks->present($task)], 201);
    }

    /** PATCH /api/assistant/tasks/{id}/complete */
    public function complete(Request $request, int $id): JsonResponse
    {
        $task = $this->tasks->findForUser($request->user(), $id);
        $task = $this->tasks->complete($task);

        return response()->json(['task' => $this->tasks->present($task)]);
    }

    /** DELETE /api/assistant/tasks/{id} — requiere ability assistant:delete */
    public function destroy(Request $request, int $id): JsonResponse
    {
        $task = $this->tasks->findForUser($request->user(), $id);
        $presented = $this->tasks->present($task);
        $task->delete();

        return response()->json(['deleted' => $presented]);
    }
}
