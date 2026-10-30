<?php

namespace App\Http\Controllers\Assistant;

use App\Http\Controllers\Controller;
use App\Models\AcademicActivity;
use App\Models\Goal;
use App\Services\Assistant\TaskRepository;
use Carbon\CarbonImmutable;
use Illuminate\Http\JsonResponse;
use Illuminate\Http\Request;

class SummaryController extends Controller
{
    public function __construct(private TaskRepository $tasks) {}

    /** GET /api/assistant/summary?date=2026-10-27 */
    public function show(Request $request): JsonResponse
    {
        $data = $request->validate(['date' => ['nullable', 'date']]);
        $tz = config('assistant.timezone');
        $user = $request->user();

        $day = isset($data['date'])
            ? CarbonImmutable::parse($data['date'], $tz)->startOfDay()
            : CarbonImmutable::now($tz)->startOfDay();
        $date = $day->toDateString();

        $present = fn ($t) => $this->tasks->present($t);

        $dueToday = $this->tasks->search($user, ['due_from' => $date, 'due_to' => $date])->map($present)->values();
        $overdue = $this->tasks->search($user, ['overdue' => true])->map($present)->values();
        $highPriority = $this->tasks->search($user, ['priority' => 'high', 'limit' => 5])->map($present)->values();

        $activities = AcademicActivity::query()
            ->where('user_id', $user->id)
            ->where('done', false)
            ->whereBetween('due_at', [$day->utc(), $day->addDays(3)->endOfDay()->utc()])
            ->orderBy('due_at')
            ->get()
            ->map(fn ($a) => ActivityController::present($a, $tz))
            ->values();

        $goals = Goal::query()->where('user_id', $user->id)->where('active', true)
            ->orderBy('deadline')->limit(5)->get()
            ->map(fn ($g) => GoalController::present($g))
            ->values();

        return response()->json([
            'date' => $date,
            'weekday' => $day->locale('es')->dayName,
            'tasks_due_today' => $dueToday,
            'tasks_overdue' => $overdue,
            'tasks_high_priority_open' => $highPriority,
            'activities_next_3_days' => $activities,
            'active_goals' => $goals,
        ]);
    }
}
