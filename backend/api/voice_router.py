import pathlib
from typing import Annotated
from uuid import uuid4, UUID

from fastapi import APIRouter, Depends, UploadFile, HTTPException, Response

from auth import JwtAuth
from models import User, Voice
from repository import (
    get_voice_repository,
    get_user_repository,
    VoiceRepository,
    UserRepository,
)
from s3_service import upload_audio, download_audio

router = APIRouter(dependencies=[Depends(JwtAuth())])


@router.post("/voice")
async def upload_voice(
    to_user: int,
    audio_file: UploadFile,
    from_user_kakao_id: Annotated[int, Depends(JwtAuth())],
    voice_repo: Annotated[VoiceRepository, Depends(get_voice_repository)],
    user_repo: Annotated[UserRepository, Depends(get_user_repository)],
):
    # save voice data to db
    from_user: User = user_repo.find_by_kakao_id(from_user_kakao_id)
    s3_id = uuid4()

    voice = Voice(from_user=from_user.id, to_user=to_user, s3_id=s3_id.bytes)
    voice_repo.insert(voice)

    # upload to s3
    upload_audio(f"{s3_id}.mp3", await audio_file.read())

    # (tmp)
    return "ok"


@router.get("/voice/{voice_id}/meta")
async def get_voice_metadata(
    voice_id: int,
    user_kakao_id: Annotated[int, Depends(JwtAuth())],
    voice_repo: Annotated[VoiceRepository, Depends(get_voice_repository)],
    user_repo: Annotated[UserRepository, Depends(get_user_repository)],
):
    # find voice
    voice = voice_repo.find_by_id(voice_id)
    if not voice:
        raise HTTPException(status_code=500, detail="voice required")

    # authorize: 보낸 쪽(from_user), 받는 쪽(to_user)모두 권한 있임
    user: User = user_repo.find_by_kakao_id(user_kakao_id)
    assert user is not None
    if user.id not in [voice.to_user, voice.from_user]:
        raise HTTPException(status_code=401, detail="unauthorized")

    return {
        "voice_id": voice.id,
        "s3_id": str(UUID(bytes=voice.s3_id)),
        "from_user": voice.from_user,
        "to_user": voice.to_user,
        "annonymous": voice.annonymous,
        "is_read": voice.is_read,
        "is_correct": voice.is_correct,
        "created_at": voice.created_at,
    }


@router.get("/voice/{voice_id}/audio")
async def get_voice_audio(
    voice_id: int,
    user_kakao_id: Annotated[int, Depends(JwtAuth())],
    user_repo: Annotated[UserRepository, Depends(get_user_repository)],
    voice_repo: Annotated[VoiceRepository, Depends(get_voice_repository)],
):
    # find voice
    voice = voice_repo.find_by_id(voice_id)
    if voice is None:
        raise HTTPException(status_code=500, detail="voice required")

    # authorize
    # authorize: 보낸 쪽(from_user), 받는 쪽(to_user)모두 권한 있임
    user: User = user_repo.find_by_kakao_id(user_kakao_id)
    assert user is not None
    if user.id not in [voice.to_user, voice.from_user]:
        raise HTTPException(status_code=401, detail="unauthorized")

    s3_id = str(UUID(bytes=voice.s3_id))

    audio_binary: bytes = download_audio(f"{s3_id}.mp3")

    return Response(content=audio_binary, media_type="audio/mpeg")


@router.get("/voice/sent")
async def get_voice_id_list(
    user_kakao_id: Annotated[int, Depends(JwtAuth())],
    user_repo: Annotated[UserRepository, Depends(get_user_repository)],
    voice_repo: Annotated[VoiceRepository, Depends(get_voice_repository)],
) -> list[int]:
    user: User = user_repo.find_by_kakao_id(user_kakao_id)
    assert user is not None

    voice_list: list[Voice] = voice_repo.find_by_from_user_id(user.id)
    if len(voice_list) == 0:
        return []

    return list(map(lambda x: x.id, voice_list))


@router.get("/voice/received")
async def get_voice_id_list(
    user_kakao_id: Annotated[int, Depends(JwtAuth())],
    user_repo: Annotated[UserRepository, Depends(get_user_repository)],
    voice_repo: Annotated[VoiceRepository, Depends(get_voice_repository)],
) -> list[int]:
    user: User = user_repo.find_by_kakao_id(user_kakao_id)
    assert user is not None

    voice_list: list[Voice] = voice_repo.find_by_to_user_id(user.id)
    if len(voice_list) == 0:
        return []

    return list(map(lambda x: x.id, voice_list))
