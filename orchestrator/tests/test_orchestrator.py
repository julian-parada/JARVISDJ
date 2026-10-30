import httpx
import respx
from sqlalchemy import select

from jarvis import accounts
from jarvis.db import session_scope
from jarvis.llm import LLMResponse, ScriptedLLM
from jarvis.models import Credential, Message, PendingAction, ToolLog, UsageLog
from jarvis.orchestrator import Orchestrator
from jarvis.tools import default_registry
from tests.conftest import HUB_URL

API = f"{HUB_URL}/api/assistant"


def tool_call(name, inp=None, call_id="t1"):
    return LLMResponse(
        content=[{"type": "tool_use", "id": call_id, "name": name, "input": inp or {}}],
        stop_reason="tool_use", model="test-model", input_tokens=100, output_tokens=20,
    )


def text(msg):
    return LLMResponse(content=[{"type": "text", "text": msg}], stop_reason="end_turn",
                       model="test-model", input_tokens=150, output_tokens=30)


def make(settings, *responses):
    llm = ScriptedLLM(list(responses))
    return Orchestrator(llm=llm, registry=default_registry(), settings=settings), llm


@respx.mock
def test_resumen_dia_llama_hub_y_registra_todo(settings, user_id):
    route = respx.get(f"{API}/summary").mock(return_value=httpx.Response(200, json={
        "date": "2026-10-27", "tasks_due_today": [{"id": 4, "title": "Informe BD"}],
    }))
    orch, llm = make(settings, tool_call("resumen_dia"), text("Hoy tienes el informe de BD."))

    reply = orch.handle(user_id, "¿qué tengo pendiente hoy?")

    assert reply.text == "Hoy tienes el informe de BD."
    assert reply.tools_used == ["resumen_dia"]
    assert route.called
    assert route.calls[0].request.headers["Authorization"] == "Bearer secret-token"

    # el resultado de la herramienta volvió al modelo
    second_call_msgs = llm.calls[1]["messages"]
    assert second_call_msgs[-1]["content"][0]["type"] == "tool_result"
    assert "Informe BD" in second_call_msgs[-1]["content"][0]["content"]

    with session_scope() as s:
        logs = s.scalars(select(ToolLog)).all()
        assert [(l.tool_name, l.status) for l in logs] == [("resumen_dia", "ok")]
        usage = s.scalars(select(UsageLog)).all()
        assert sum(u.input_tokens for u in usage) == 250
        assert [m.role for m in s.scalars(select(Message).order_by(Message.id))] == ["user", "assistant"]


@respx.mock
def test_crear_tarea_traduce_parametros(settings, user_id):
    route = respx.post(f"{API}/tasks").mock(return_value=httpx.Response(201, json={"task": {"id": 9}}))
    orch, _ = make(
        settings,
        tool_call("crear_tarea", {"titulo": "Estudiar parcial", "prioridad": "high", "fecha_limite": "2026-10-30"}),
        text("Creada."),
    )
    orch.handle(user_id, "crea una tarea: estudiar para el parcial, prioridad alta, para el viernes")

    import json
    body = json.loads(route.calls[0].request.content)
    assert body == {"title": "Estudiar parcial", "priority": "high", "due_date": "2026-10-30"}


@respx.mock
def test_accion_sensible_requiere_confirmacion_en_otro_turno(settings, user_id):
    delete = respx.delete(f"{API}/tasks/7").mock(return_value=httpx.Response(200, json={"deleted": {"id": 7}}))

    # Turno 1: el modelo pide eliminar e intenta autoconfirmar en el mismo turno.
    orch, _ = make(
        settings,
        tool_call("eliminar_tarea", {"id": 7, "titulo": "Viejo informe"}),
        tool_call("confirmar_accion", call_id="t2"),
        text("¿Confirmas que elimino «Viejo informe»?"),
    )
    reply = orch.handle(user_id, "borra la tarea del viejo informe")
    assert reply.pending_confirmation == "eliminar la tarea «Viejo informe» (id 7)"
    assert not delete.called, "no debe borrar sin confirmación del usuario"

    with session_scope() as s:
        statuses = [(l.tool_name, l.status) for l in s.scalars(select(ToolLog).order_by(ToolLog.id))]
        assert statuses == [("eliminar_tarea", "needs_confirmation"), ("confirmar_accion", "error")]

    # Turno 2: el usuario confirma.
    orch.llm = ScriptedLLM([tool_call("confirmar_accion", call_id="t3"), text("Eliminada.")])
    reply = orch.handle(user_id, "sí, dale")
    assert reply.text == "Eliminada."
    assert delete.called

    with session_scope() as s:
        action = s.scalar(select(PendingAction))
        assert action.status == "confirmed"
        last = s.scalars(select(ToolLog).order_by(ToolLog.id)).all()[-2:]
        assert [(l.tool_name, l.status) for l in last] == [("eliminar_tarea", "ok"), ("confirmar_accion", "ok")]


@respx.mock
def test_cancelar_accion(settings, user_id):
    delete = respx.delete(f"{API}/tasks/7").mock(return_value=httpx.Response(200, json={}))
    orch, _ = make(settings, tool_call("eliminar_tarea", {"id": 7}), text("¿Confirmas?"))
    orch.handle(user_id, "borra la 7")

    orch.llm = ScriptedLLM([tool_call("cancelar_accion"), text("Cancelado.")])
    orch.handle(user_id, "no, mejor no")

    orch.llm = ScriptedLLM([tool_call("confirmar_accion"), text("No había nada.")])
    orch.handle(user_id, "sí")
    assert not delete.called


def test_herramienta_no_permitida(settings, user_id):
    orch, llm = make(settings, tool_call("formatear_disco"), text("No puedo hacer eso."))
    reply = orch.handle(user_id, "formatea el disco")
    assert reply.text == "No puedo hacer eso."
    result = llm.calls[1]["messages"][-1]["content"][0]
    assert result["is_error"] is True
    with session_scope() as s:
        assert s.scalar(select(ToolLog)).status == "denied"


def test_herramientas_habilitadas_por_usuario(settings, user_id):
    from jarvis.models import User

    with session_scope() as s:
        s.get(User, user_id).settings.enabled_tools = ["resumen_dia"]
    orch, llm = make(settings, text("Hola"))
    orch.handle(user_id, "hola")
    names = {t["name"] for t in llm.calls[0]["tools"]}
    assert names == {"resumen_dia", "confirmar_accion", "cancelar_accion"}


@respx.mock
def test_error_de_la_api_de_ia_se_muestra_legible(settings, user_id):
    from jarvis.llm import LLMError

    class Broken:
        def complete(self, **kw):
            raise LLMError("Tu ANTHROPIC_API_KEY no es válida.")

    orch = Orchestrator(llm=Broken(), registry=default_registry(), settings=settings)
    reply = orch.handle(user_id, "hola")
    assert "no es válida" in reply.text
    with session_scope() as s:
        assert s.scalars(select(Message)).all() == []  # el turno fallido no ensucia el historial


@respx.mock
def test_errores_del_hub_llegan_legibles_al_modelo(settings, user_id):
    respx.get(f"{API}/tasks").mock(return_value=httpx.Response(403, json={}))
    orch, llm = make(settings, tool_call("listar_tareas"), text("No tengo permiso."))
    orch.handle(user_id, "mis tareas")
    result = llm.calls[1]["messages"][-1]["content"][0]
    assert result["is_error"] is True
    assert "permiso" in result["content"]


def test_historial_alterna_y_se_reinicia(settings, user_id):
    orch, llm = make(settings, text("Hola Julian"), text("Bien"), text("Arrancamos de cero"))
    orch.handle(user_id, "hola")
    orch.handle(user_id, "¿cómo vas?")
    msgs = llm.calls[1]["messages"]
    assert [m["role"] for m in msgs] == ["user", "assistant", "user"]

    orch.reset_context(user_id)
    orch.handle(user_id, "nuevo tema")
    assert [m["role"] for m in llm.calls[2]["messages"]] == ["user"]


def test_prompt_incluye_fecha_y_preferencias(settings, user_id):
    from jarvis.models import User

    with session_scope() as s:
        s.get(User, user_id).settings.prompt_extra = "Llámame jefe."
    orch, llm = make(settings, text("ok"))
    orch.handle(user_id, "hola", channel="voice")
    system = llm.calls[0]["system"]
    assert "Eres Jarvis" in system and "Llámame jefe." in system
    assert "voz alta" in system


def test_vinculacion_telegram(settings, user_id):
    with session_scope() as s:
        code = accounts.new_link_code(s, user_id)
    with session_scope() as s:
        assert accounts.redeem_link_code(s, code.lower(), "telegram", "555").id == user_id
    with session_scope() as s:
        assert accounts.redeem_link_code(s, code, "telegram", "999") is None  # ya usado
        assert accounts.user_for_channel(s, "telegram", "555").id == user_id


def test_credenciales_se_guardan_cifradas(settings, user_id):
    with session_scope() as s:
        cred = s.scalar(select(Credential))
        assert "secret-token" not in cred.secret_encrypted


@respx.mock
def test_objetivos_y_actividades_contra_personal_hub(settings, user_id):
    import json

    goals = respx.post(f"{API}/goals").mock(return_value=httpx.Response(201, json={"goal": {"id": 1}}))
    progress = respx.patch(f"{API}/goals/1/progress").mock(return_value=httpx.Response(200, json={"goal": {"id": 1}}))
    acts = respx.post(f"{API}/activities").mock(return_value=httpx.Response(201, json={"activity": {"id": 1}}))

    orch, _ = make(settings, tool_call("crear_objetivo", {"titulo": "Ahorro", "meta": 500000}), text("ok"))
    orch.handle(user_id, "x")
    orch.llm = ScriptedLLM([tool_call("registrar_avance_objetivo", {"id": 1, "sumar": 1000}), text("ok")])
    orch.handle(user_id, "x")
    orch.llm = ScriptedLLM([tool_call("crear_actividad", {"titulo": "Parcial", "fecha": "2026-11-03"}), text("ok")])
    orch.handle(user_id, "x")

    assert json.loads(goals.calls[0].request.content) == {"title": "Ahorro", "target": 500000}
    assert json.loads(progress.calls[0].request.content) == {"add": 1000}
    assert json.loads(acts.calls[0].request.content) == {"title": "Parcial", "due_at": "2026-11-03"}
