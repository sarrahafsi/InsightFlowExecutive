"""
Orchestration API — expose l'état et les décisions de l'orchestrateur AI.
"""
from fastapi import APIRouter

router = APIRouter(prefix="/api/orchestration", tags=["orchestration"])


@router.get("/latest")
def get_latest_orchestration():
    """Retourne la dernière décision prise par l'orchestrateur AI."""
    from tasks.orchestrate_tasks import get_latest
    result = get_latest()
    if not result:
        return {"status": "no_data", "message": "Aucune orchestration exécutée depuis le démarrage."}
    return result


@router.post("/trigger")
def trigger_orchestration(source: str = "gmail", new_items: int = 0):
    """Déclenche manuellement une analyse orchestrateur (utile pour les tests)."""
    from tasks.orchestrate_tasks import run_orchestration
    task = run_orchestration.delay(source=source, new_items=new_items)
    return {"status": "launched", "task_id": str(task.id), "source": source}
