from datetime import datetime

from pydantic import BaseModel, Field


class MeOut(BaseModel):
    telegram_id: int
    first_name: str
    username: str | None
    suggested_display_name: str
    is_bartender: bool
    dev_mode: bool
    bartender_telegram_id: int | None = None


class CocktailOut(BaseModel):
    id: int
    name: str
    description: str
    photo_url: str | None
    available: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class OrderCreate(BaseModel):
    cocktail_id: int
    display_name: str = Field(min_length=1, max_length=80)


class OrderStatusPatch(BaseModel):
    status: str


class OrderOut(BaseModel):
    id: int
    cocktail_id: int | None
    cocktail_name: str
    guest_telegram_id: int
    guest_username: str | None
    display_name: str
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}
