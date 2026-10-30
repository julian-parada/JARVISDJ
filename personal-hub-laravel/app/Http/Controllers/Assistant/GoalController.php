<?php

namespace App\Http\Controllers\Assistant;

use App\Http\Controllers\Controller;
use App\Models\Goal;
use Illuminate\Http\JsonResponse;
use Illuminate\Http\Request;

class GoalController extends Controller
{
    /** GET /api/assistant/goals */
    public function index(Request $request): JsonResponse
    {
        $data = $request->validate(['q' => ['nullable', 'string', 'max:100']]);

        $query = Goal::query()->where('user_id', $request->user()->id)->where('active', true);

        if (! empty($data['q'])) {
            $query->whereRaw('LOWER(title) LIKE ?', ['%'.mb_strtolower($data['q']).'%']);
        }

        $goals = $query->orderBy('deadline')->get()->map(fn (Goal $g) => self::present($g));

        return response()->json(['count' => $goals->count(), 'goals' => $goals]);
    }

    /** POST /api/assistant/goals */
    public function store(Request $request): JsonResponse
    {
        $data = $request->validate([
            'title' => ['required', 'string', 'max:255'],
            'target' => ['required', 'numeric', 'gt:0'],
            'unit' => ['nullable', 'string', 'max:30'],
            'current' => ['nullable', 'numeric', 'min:0'],
            'deadline' => ['nullable', 'date'],
        ]);

        $goal = Goal::create([
            'user_id' => $request->user()->id,
            'title' => $data['title'],
            'target_value' => $data['target'],
            'current_value' => $data['current'] ?? 0,
            'unit' => $data['unit'] ?? 'COP',
            'deadline' => $data['deadline'] ?? null,
            'active' => true,
        ]);

        return response()->json(['goal' => self::present($goal->fresh())], 201);
    }

    /** PATCH /api/assistant/goals/{id}/progress  {add?: number, set?: number} */
    public function progress(Request $request, int $id): JsonResponse
    {
        $data = $request->validate([
            'add' => ['nullable', 'numeric', 'required_without:set'],
            'set' => ['nullable', 'numeric', 'min:0', 'required_without:add'],
        ]);

        $goal = Goal::where('user_id', $request->user()->id)->findOrFail($id);
        $goal->current_value = array_key_exists('set', $data) && $data['set'] !== null
            ? $data['set']
            : (float) $goal->current_value + (float) $data['add'];
        $goal->save();

        return response()->json(['goal' => self::present($goal->fresh())]);
    }

    public static function present(Goal $g): array
    {
        return [
            'id' => $g->id,
            'title' => $g->title,
            'current' => (float) $g->current_value,
            'target' => (float) $g->target_value,
            'unit' => $g->unit,
            'progress_percent' => $g->progress_percent,
            'deadline' => $g->deadline?->toDateString(),
        ];
    }
}
