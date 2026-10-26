from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..bot import notify_bartender, notify_guest_status
from ..database import get_db
from ..models import NEXT_STATUS, ORDER_STATUSES, STATUS_LABEL_RU, Cocktail, Order
from ..schemas import OrderCreate, OrderOut, OrderStatusPatch
from ..telegram_auth import TelegramUser, get_current_user, require_bartender

router = APIRouter(prefix="/api/orders", tags=["orders"])


@router.get("", response_model=list[OrderOut])
def list_orders(
    user: TelegramUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[Order]:
    query = db.query(Order).order_by(Order.created_at.desc())
    if user.is_bartender:
        return query.all()
    return query.filter(Order.guest_telegram_id == user.id).all()


@router.post("", response_model=OrderOut, status_code=status.HTTP_201_CREATED)
async def create_order(
    payload: OrderCreate,
    user: TelegramUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Order:
    cocktail = db.get(Cocktail, payload.cocktail_id, with_for_update=True)
    if cocktail is None or not cocktail.available:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Этого напитка нет в меню")
    display_name = payload.display_name.strip()
    if not display_name:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Нужно имя")
    order = Order(
        cocktail_id=cocktail.id,
        cocktail_name=cocktail.name,
        guest_telegram_id=user.id,
        guest_username=user.username,
        display_name=display_name,
        status="pending",
    )
    db.add(order)
    db.flush()
    db.refresh(cocktail)
    if not cocktail.available:
        db.rollback()
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Этого напитка нет в меню")
    db.commit()
    db.refresh(order)
    await notify_bartender(
        cocktail_name=order.cocktail_name,
        display_name=order.display_name,
        guest_username=order.guest_username,
        order_id=order.id,
    )
    await notify_guest_status(
        chat_id=order.guest_telegram_id,
        order_id=order.id,
        cocktail_name=order.cocktail_name,
        status=order.status,
    )
    return order


@router.patch("/{order_id}/status", response_model=OrderOut)
async def patch_status(
    order_id: int,
    payload: OrderStatusPatch,
    _: TelegramUser = Depends(require_bartender),
    db: Session = Depends(get_db),
) -> Order:
    order = db.get(Order, order_id)
    if order is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Заказ не найден")
    next_status = payload.status.strip()
    if next_status not in ORDER_STATUSES:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Неизвестный статус")
    if next_status == order.status:
        return order
    expected = NEXT_STATUS.get(order.status)
    if next_status != expected:
        current = STATUS_LABEL_RU.get(order.status, order.status)
        target = STATUS_LABEL_RU.get(next_status, next_status)
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"Нельзя сменить статус с «{current}» на «{target}»",
        )
    order.status = next_status
    db.commit()
    db.refresh(order)
    await notify_guest_status(
        chat_id=order.guest_telegram_id,
        order_id=order.id,
        cocktail_name=order.cocktail_name,
        status=order.status,
    )
    return order
