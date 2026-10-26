from fastapi import APIRouter, Depends, Request

from ..config import settings
from ..schemas import MeOut
from ..telegram_auth import TelegramUser, get_current_user, local_dev_impersonation_allowed

router = APIRouter(prefix="/api", tags=["me"])


@router.get("/me", response_model=MeOut)
def get_me(request: Request, user: TelegramUser = Depends(get_current_user)) -> MeOut:
    expose_bartender_id = user.dev_mode and local_dev_impersonation_allowed(request)
    return MeOut(
        telegram_id=user.id,
        first_name=user.first_name,
        username=user.username,
        suggested_display_name=user.suggested_display_name,
        is_bartender=user.is_bartender,
        dev_mode=user.dev_mode,
        bartender_telegram_id=settings.bartender_telegram_id if expose_bartender_id else None,
    )
