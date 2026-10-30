"""Modo local: JARVIS funcionando sin Personal Hub."""

from datetime import timedelta

from sqlalchemy import select

from jarvis.db import session_scope
from jarvis.llm import ScriptedLLM
from jarvis.models import LocalTask, ToolLog
from jarvis.orchestrator import Orchestrator
from jarvis.timeutil import local_now
from jarvis.tools import default_registry
from tests.test_orchestrator import text, tool_call

TODAY = local_now("America/Bogota").date()


def run(settings, uid, message, *responses):
    llm = ScriptedLLM(list(responses))
    orch = Orchestrator(llm=llm, registry=default_registry(), settings=settings)
    return orch.handle(uid, message), llm


def last_result(llm):
    return llm.calls[-1]["messages"][-1]["content"][0]


def test_sin_hub_se_exponen_todas_las_herramientas(settings, local_user_id):
    _, llm = run(settings, local_user_id, "hola", text("Hola"))
    names = {t["name"] for t in llm.calls[0]["tools"]}
    assert {"resumen_dia", "crear_tarea", "crear_actividad", "crear_objetivo", "registrar_avance_objetivo"} <= names


def test_ciclo_completo_de_tareas(settings, local_user_id):
    manana = (TODAY + timedelta(days=1)).isoformat()
    ayer = (TODAY - timedelta(days=1)).isoformat()

    run(settings, local_user_id, "crea tarea",
        tool_call("crear_tarea", {"titulo": "Informe BD", "prioridad": "high", "fecha_limite": TODAY.isoformat()}),
        text("ok"))
    run(settings, local_user_id, "otra",
        tool_call("crear_tarea", {"titulo": "Pagar recibo", "fecha_limite": ayer}), text("ok"))
    run(settings, local_user_id, "otra",
        tool_call("crear_tarea", {"titulo": "Comprar café", "fecha_limite": manana}), text("ok"))

    _, llm = run(settings, local_user_id, "¿qué tengo hoy?", tool_call("resumen_dia"), text("..."))
    resumen = last_result(llm)["content"]
    assert '"tasks_due_today": [{"id": 1, "title": "Informe BD"' in resumen
    assert '"tasks_overdue": [{"id": 2, "title": "Pagar recibo"' in resumen
    assert "Comprar café" not in resumen.split('"tasks_high_priority_open"')[0]

    _, llm = run(settings, local_user_id, "busca", tool_call("listar_tareas", {"buscar": "café"}), text("..."))
    assert '"count": 1' in last_result(llm)["content"]

    run(settings, local_user_id, "completa el informe", tool_call("completar_tarea", {"id": 1}), text("Hecho"))
    _, llm = run(settings, local_user_id, "pendientes", tool_call("listar_tareas"), text("..."))
    assert "Informe BD" not in last_result(llm)["content"]

    # eliminar sigue requiriendo confirmación en modo local
    run(settings, local_user_id, "borra la de café",
        tool_call("eliminar_tarea", {"id": 3, "titulo": "Comprar café"}), text("¿Confirmas?"))
    with session_scope() as s:
        assert s.get(LocalTask, 3) is not None
    run(settings, local_user_id, "sí", tool_call("confirmar_accion"), text("Eliminada"))
    with session_scope() as s:
        assert s.get(LocalTask, 3) is None


def test_actividades_y_objetivos(settings, local_user_id):
    en_dos_dias = (TODAY + timedelta(days=2)).isoformat()
    run(settings, local_user_id, "parcial",
        tool_call("crear_actividad", {"titulo": "Parcial Cálculo", "materia": "Cálculo II", "tipo": "parcial",
                                      "fecha": f"{en_dos_dias}T08:00"}), text("ok"))
    run(settings, local_user_id, "objetivo",
        tool_call("crear_objetivo", {"titulo": "Ahorro diciembre", "meta": 500000}), text("ok"))
    run(settings, local_user_id, "ahorré",
        tool_call("registrar_avance_objetivo", {"id": 1, "sumar": 125000}), text("ok"))

    _, llm = run(settings, local_user_id, "actividades", tool_call("listar_actividades"), text("..."))
    result = last_result(llm)["content"]
    assert "Parcial Cálculo" in result and f"{en_dos_dias}T08:00-05:00" in result

    _, llm = run(settings, local_user_id, "¿cómo voy?", tool_call("estado_objetivos"), text("..."))
    assert '"progress_percent": 25.0' in last_result(llm)["content"]


def test_errores_de_datos_llegan_al_modelo(settings, local_user_id):
    _, llm = run(settings, local_user_id, "x", tool_call("completar_tarea", {"id": 99}), text("No existe"))
    assert last_result(llm)["is_error"] and "No encontré" in last_result(llm)["content"]

    _, llm = run(settings, local_user_id, "x",
                 tool_call("crear_tarea", {"titulo": "a", "fecha_limite": "viernes"}), text("..."))
    assert last_result(llm)["is_error"] and "YYYY-MM-DD" in last_result(llm)["content"]


def test_usuarios_aislados(settings, local_user_id):
    from jarvis import accounts

    with session_scope() as s:
        otro = accounts.create_user(s, name="Otro").id
    run(settings, local_user_id, "x", tool_call("crear_tarea", {"titulo": "Secreta"}), text("ok"))
    _, llm = run(settings, otro, "x", tool_call("listar_tareas"), text("..."))
    assert "Secreta" not in last_result(llm)["content"]
    _, llm = run(settings, otro, "x", tool_call("completar_tarea", {"id": 1}), text("..."))
    assert last_result(llm)["is_error"]
    with session_scope() as s:
        assert s.scalar(select(LocalTask)).status == "pending"
        assert s.scalars(select(ToolLog).where(ToolLog.user_id == otro)).all()
