from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import ModelDefaults, Provider
from app.schemas.provider import (
    DefaultsOut,
    DefaultsUpdate,
    ProviderOut,
    ProviderUpdate,
    TestProviderRequest,
    TestProviderResult,
)
from app.services import provider_service

router = APIRouter(prefix="/providers", tags=["模型服务商"])


@router.get("", response_model=list[ProviderOut])
def list_providers(db: Session = Depends(get_db)):
    return db.query(Provider).order_by(Provider.created_at).all()


@router.post("", response_model=ProviderOut, status_code=201)
def create_provider(data: dict, db: Session = Depends(get_db)):
    return provider_service.create_provider(db, data)


@router.put("/{provider_id}", response_model=ProviderOut)
def update_provider(provider_id: str, data: ProviderUpdate, db: Session = Depends(get_db)):
    return provider_service.update_provider(db, provider_id, data)


@router.delete("/{provider_id}", status_code=204)
def delete_provider(provider_id: str, db: Session = Depends(get_db)):
    provider_service.delete_provider(db, provider_id)


@router.post("/{provider_id}/test", response_model=TestProviderResult)
def test_provider(
    provider_id: str, req: TestProviderRequest | None = None, db: Session = Depends(get_db)
):
    provider = provider_service.get_provider(db, provider_id)
    return provider_service.test_provider_connection(provider, req.model_type if req else None)


@router.get("/defaults/models", response_model=DefaultsOut)
def get_model_defaults(db: Session = Depends(get_db)):
    return provider_service.get_defaults(db)


@router.put("/defaults/models", response_model=DefaultsOut)
def update_model_defaults(data: DefaultsUpdate, db: Session = Depends(get_db)):
    return provider_service.update_defaults(db, data)
