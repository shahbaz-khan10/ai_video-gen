"""FastAPI dependencies. Tests override these with ``app.dependency_overrides``."""

from typing import Annotated

from fastapi import Depends, Request

from app.core.config import Settings
from app.services.generation_service import GenerationService
from app.services.image_store import ImageStore


def get_app_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_generation_service(request: Request) -> GenerationService:
    return request.app.state.generation_service


def get_image_store(request: Request) -> ImageStore:
    return request.app.state.generation_service.images


SettingsDep = Annotated[Settings, Depends(get_app_settings)]
GenerationServiceDep = Annotated[GenerationService, Depends(get_generation_service)]
ImageStoreDep = Annotated[ImageStore, Depends(get_image_store)]
