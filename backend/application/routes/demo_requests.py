"""
Demande de démo — lead commercial public, indépendant du signup produit.
POST /demo-requests — accessible sans compte, ne crée ni User ni Organisation.
"""
import logging

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from core.database import get_db
from core.models import DemoRequest

logger = logging.getLogger(__name__)
router = APIRouter(tags=["demo-requests"])


class DemoRequestCreate(BaseModel):
    first_name: str
    last_name: str
    email: str
    company: str
    job_title: str | None = None
    company_size: str | None = None
    sources: list[str] = []
    message: str | None = None


@router.post("/demo-requests", status_code=201)
def create_demo_request(body: DemoRequestCreate, db: Session = Depends(get_db)):
    req = DemoRequest(
        first_name=body.first_name.strip(),
        last_name=body.last_name.strip(),
        email=body.email.strip(),
        company=body.company.strip(),
        job_title=(body.job_title or "").strip() or None,
        company_size=body.company_size or None,
        sources=body.sources or [],
        message=(body.message or "").strip() or None,
        status="NEW",
    )
    db.add(req)
    db.commit()
    logger.info("[demo-request] Nouvelle demande de %s (%s)", req.email, req.company)
    return {"status": "ok"}
