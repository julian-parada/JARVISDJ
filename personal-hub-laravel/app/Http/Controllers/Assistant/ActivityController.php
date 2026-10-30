<?php

namespace App\Http\Controllers\Assistant;

use App\Http\Controllers\Controller;
use App\Models\AcademicActivity;
use Carbon\CarbonImmutable;
use Illuminate\Http\JsonResponse;
use Illuminate\Http\Request;

class ActivityController extends Controller
{
    /** GET /api/assistant/activities?days=7 */
    public function index(Request $request): JsonResponse
    {
        $data = $request->validate([
            'days' => ['nullable', 'integer', 'min:1', 'max:60'],
            'subject' => ['nullable', 'string', 'max:100'],
        ]);

        $tz = config('assistant.timezone');
        $from = CarbonImmutable::now($tz)->startOfDay();
        $to = $from->addDays((int) ($data['days'] ?? 7))->endOfDay();

        $query = AcademicActivity::query()
            ->where('user_id', $request->user()->id)
            ->where('done', false)
            ->whereBetween('due_at', [$from->utc(), $to->utc()])
            ->orderBy('due_at');

        if (! empty($data['subject'])) {
            $query->whereRaw('LOWER(subject) LIKE ?', ['%'.mb_strtolower($data['subject']).'%']);
        }

        $items = $query->limit(config('assistant.max_results'))->get()
            ->map(fn (AcademicActivity $a) => self::present($a, $tz));

        return response()->json(['count' => $items->count(), 'activities' => $items]);
    }

    /** POST /api/assistant/activities */
    public function store(Request $request): JsonResponse
    {
        $data = $request->validate([
            'title' => ['required', 'string', 'max:255'],
            'due_at' => ['required', 'date'],
            'subject' => ['nullable', 'string', 'max:120'],
            'type' => ['nullable', 'in:entrega,parcial,exposicion,quiz,otro'],
            'notes' => ['nullable', 'string', 'max:2000'],
        ]);

        $tz = config('assistant.timezone');
        // "2026-11-03" (sin hora) => ese día a las 23:59 hora local
        $dueAt = strlen(trim($data['due_at'])) <= 10
            ? CarbonImmutable::parse($data['due_at'], $tz)->setTime(23, 59)
            : CarbonImmutable::parse($data['due_at'], $tz);

        $activity = AcademicActivity::create([
            'user_id' => $request->user()->id,
            'title' => $data['title'],
            'subject' => $data['subject'] ?? null,
            'type' => $data['type'] ?? 'entrega',
            'due_at' => $dueAt->utc(),
            'notes' => $data['notes'] ?? null,
        ]);

        return response()->json(['activity' => self::present($activity, $tz)], 201);
    }

    public static function present(AcademicActivity $a, string $tz): array
    {
        return [
            'id' => $a->id,
            'title' => $a->title,
            'subject' => $a->subject,
            'type' => $a->type,
            'due_at' => $a->due_at->setTimezone($tz)->toIso8601String(),
            'notes' => $a->notes,
        ];
    }
}
