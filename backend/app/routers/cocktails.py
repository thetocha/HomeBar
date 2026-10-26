from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Cocktail
from ..photos import cocktail_photo_url, delete_photo, save_photo
from ..schemas import CocktailOut
from ..telegram_auth import TelegramUser, get_current_user, require_bartender

router = APIRouter(prefix="/api/cocktails", tags=["cocktails"])

NAME_MAX = 120
DESCRIPTION_MAX = 4000


def _validated_name(name: str) -> str:
    name = name.strip()
    if not name:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Name is required")
    if len(name) > NAME_MAX:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Name is too long")
    return name


def _validated_description(description: str) -> str:
    description = description.strip()
    if len(description) > DESCRIPTION_MAX:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Description is too long")
    return description


def to_out(cocktail: Cocktail) -> CocktailOut:
    return CocktailOut(
        id=cocktail.id,
        name=cocktail.name,
        description=cocktail.description,
        photo_url=cocktail_photo_url(cocktail.photo_filename),
        available=cocktail.available,
        created_at=cocktail.created_at,
    )


@router.get("", response_model=list[CocktailOut])
def list_cocktails(
    user: TelegramUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[CocktailOut]:
    query = db.query(Cocktail).order_by(Cocktail.name.asc())
    if not user.is_bartender:
        query = query.filter(Cocktail.available.is_(True))
    return [to_out(row) for row in query.all()]


@router.get("/{cocktail_id}", response_model=CocktailOut)
def get_cocktail(
    cocktail_id: int,
    user: TelegramUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CocktailOut:
    cocktail = db.get(Cocktail, cocktail_id)
    if cocktail is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Cocktail not found")
    if not cocktail.available and not user.is_bartender:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Cocktail not found")
    return to_out(cocktail)


@router.post("", response_model=CocktailOut, status_code=status.HTTP_201_CREATED)
async def create_cocktail(
    name: str = Form(...),
    description: str = Form(""),
    available: bool = Form(True),
    photo: UploadFile | None = File(None),
    _: TelegramUser = Depends(require_bartender),
    db: Session = Depends(get_db),
) -> CocktailOut:
    name = _validated_name(name)
    description = _validated_description(description)
    filename = await save_photo(photo) if photo and photo.filename else None
    cocktail = Cocktail(
        name=name,
        description=description,
        photo_filename=filename,
        available=available,
    )
    db.add(cocktail)
    db.commit()
    db.refresh(cocktail)
    return to_out(cocktail)


@router.patch("/{cocktail_id}", response_model=CocktailOut)
async def update_cocktail(
    cocktail_id: int,
    name: str | None = Form(None),
    description: str | None = Form(None),
    available: bool | None = Form(None),
    photo: UploadFile | None = File(None),
    _: TelegramUser = Depends(require_bartender),
    db: Session = Depends(get_db),
) -> CocktailOut:
    cocktail = db.get(Cocktail, cocktail_id)
    if cocktail is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Cocktail not found")
    if name is not None:
        cocktail.name = _validated_name(name)
    if description is not None:
        cocktail.description = _validated_description(description)
    if available is not None:
        cocktail.available = available
    if photo and photo.filename:
        old = cocktail.photo_filename
        cocktail.photo_filename = await save_photo(photo)
        delete_photo(old)
    db.commit()
    db.refresh(cocktail)
    return to_out(cocktail)


@router.delete("/{cocktail_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_cocktail(
    cocktail_id: int,
    _: TelegramUser = Depends(require_bartender),
    db: Session = Depends(get_db),
) -> None:
    cocktail = db.get(Cocktail, cocktail_id)
    if cocktail is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Cocktail not found")
    delete_photo(cocktail.photo_filename)
    db.delete(cocktail)
    db.commit()
