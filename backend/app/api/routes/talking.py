"""Talking videos: speech (Chatterbox) + lip-sync (MuseTalk) on a finished video or an uploaded photo."""

from __future__ import annotations

from fastapi import APIRouter, Query, Request
from fastapi.concurrency import run_in_threadpool

from app.services.talking_service import TalkJob, TalkRequest

router = APIRouter(prefix="/talking", tags=["talking"])


def _svc(request: Request):
    return request.app.state.talking_service


@router.get("/status", summary="Whether the speech and lip-sync services are running")
def status(request: Request) -> dict:
    return _svc(request).status()


@router.get("/voices", summary="Reference voices the user recorded")
def voices(request: Request) -> list:
    return _svc(request).voices()


@router.post("/voices", status_code=201, summary="Add a voice: the raw recording (5-60 s) is the body")
async def add_voice(request: Request, name: str = Query(min_length=1, max_length=60),
                    gender: str = Query(pattern="^(male|female)$")) -> dict:
    data = await request.body()
    return await run_in_threadpool(_svc(request).add_voice, data, name, gender)


@router.post("", status_code=202, response_model=TalkJob, summary="Make a video or photo speak the text")
def create(body: TalkRequest, request: Request) -> TalkJob:
    return _svc(request).create(body)


@router.get("/{job_id}", response_model=TalkJob, summary="Talking-video job status")
def get(job_id: str, request: Request) -> TalkJob:
    return _svc(request).get(job_id)
