"""
Inside PC — Бот + API + Портфолио.
Чистая архитектура, отложенная оплата, портфолио-админка.
"""

import asyncio
import json
import logging
import os
import tempfile

from aiogram import Bot, Dispatcher, Router, F
from aiogram.filters import CommandStart, CommandObject, Command
from aiogram.types import (
    Message, CallbackQuery, InlineKeyboardMarkup,
    InlineKeyboardButton, WebAppInfo, InputMediaPhoto,
    FSInputFile,
)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.client.default import DefaultBotProperties
from aiogram.exceptions import TelegramBadRequest

from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

import config
from database import *

log = logging.getLogger("insidepc")

STYLE_OK = True


def S(name: str) -> dict:
    return {"style": name} if STYLE_OK else {}


# ════════════════════════════════════════════════════════════
#  FASTAPI
# ════════════════════════════════════════════════════════════

app = FastAPI(title="Inside PC API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

WEB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web")
IMAGES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "images")
os.makedirs(IMAGES_DIR, exist_ok=True)


# ── Статические страницы ──────────────────────────────────

@app.get("/web")
@app.get("/web/")
@app.get("/web/index.html")
async def serve_index():
    p = os.path.join(WEB_DIR, "index.html")
    if not os.path.isfile(p):
        raise HTTPException(404)
    return FileResponse(p, media_type="text/html")


@app.get("/web/admin")
@app.get("/web/admin.html")
async def serve_admin():
    p = os.path.join(WEB_DIR, "admin.html")
    if not os.path.isfile(p):
        raise HTTPException(404)
    return FileResponse(p, media_type="text/html")


@app.get("/web/portfolio")
@app.get("/web/portfolio.html")
async def serve_portfolio_page():
    p = os.path.join(WEB_DIR, "portfolio.html")
    if not os.path.isfile(p):
        raise HTTPException(404)
    return FileResponse(p, media_type="text/html")


app.mount("/web/static", StaticFiles(directory=WEB_DIR), name="web_static")


# ── API: Заказы ───────────────────────────────────────────

class OrderIn(BaseModel):
    user_id: int
    username: str = ""
    full_name: str = ""
    service_type: str
    has_parts_list: bool = False
    parts_data: dict | None = None
    description: str = ""


@app.post("/api/order")
async def api_create_order(data: OrderIn):
    if data.service_type not in config.PRICES:
        raise HTTPException(400, "Неизвестная услуга")

    p = config.PRICES[data.service_type]
    await upsert_user(data.user_id, data.username, data.full_name)

    needs_quote = p.get("needs_quote", False)
    status = "pending_quote" if needs_quote else "pending_payment"

    oid = await create_order(
        data.user_id, data.service_type, data.has_parts_list,
        data.parts_data, data.description, p["byn"], p["rub"],
        status=status,
    )

    if needs_quote:
        try:
            await _handle_new_quote(oid, data.user_id, data.username)
        except Exception as e:
            log.error(f"quote init: {e}")

    return {
        "id": oid,
        "needs_quote": needs_quote,
        "bot_username": config.BOT_USERNAME,
    }


@app.get("/api/orders/{user_id}")
async def api_user_orders(user_id: int):
    orders = await get_user_orders(user_id)
    out = []
    for o in orders:
        p = config.PRICES.get(o["service_type"], {})
        out.append({
            "id": o["id"],
            "service": p.get("name", "?"),
            "status": o["status"],
            "status_text": STATUS_NAMES.get(o["status"], o["status"]),
            "price_byn": o["price_byn"],
            "price_rub": o["price_rub"],
            "price_prefix": p.get("prefix", ""),
            "date": o["created_at"][:16],
        })
    return out


@app.get("/api/order/{order_id}")
async def api_order_detail(order_id: int):
    order = await get_order(order_id)
    if not order:
        raise HTTPException(404)

    user = await get_user(order["user_id"])
    parts = None
    if order["parts_data"]:
        try:
            parts = json.loads(order["parts_data"])
        except Exception:
            pass

    p = config.PRICES.get(order["service_type"], {})
    return {
        "id": order["id"],
        "user_id": order["user_id"],
        "username": user["username"] if user else "",
        "full_name": user["full_name"] if user else "",
        "service": p.get("name", "?"),
        "status": order["status"],
        "status_text": STATUS_NAMES.get(order["status"], order["status"]),
        "price_byn": order["price_byn"],
        "price_rub": order["price_rub"],
        "price_prefix": p.get("prefix", ""),
        "has_parts": order["has_parts"],
        "parts": parts,
        "description": order["description"],
        "date": order["created_at"][:16],
    }


# ── API: Портфолио ────────────────────────────────────────

class PortfolioIn(BaseModel):
    title: str = ""
    description: str = ""
    specs: str = ""
    price_byn: float = 0
    price_rub: float = 0
    category: str = ""


@app.get("/api/portfolio")
async def api_portfolio():
    items = await get_portfolio_all()
    out = []
    for item in items:
        try:
            photos = json.loads(item["photo_ids"])
        except Exception:
            photos = []
        out.append({
            "id": item["id"],
            "title": item["title"],
            "description": item["description"],
            "specs": item["specs"],
            "price_byn": item["price_byn"],
            "price_rub": item["price_rub"],
            "category": item["category"],
            "photos": photos,
            "photo_count": len(photos),
            "date": item["created_at"][:16],
        })
    return out


@app.get("/api/portfolio/{pid}")
async def api_portfolio_item(pid: int):
    item = await get_portfolio_item(pid)
    if not item:
        raise HTTPException(404)
    try:
        photos = json.loads(item["photo_ids"])
    except Exception:
        photos = []
    return {
        "id": item["id"],
        "title": item["title"],
        "description": item["description"],
        "specs": item["specs"],
        "price_byn": item["price_byn"],
        "price_rub": item["price_rub"],
        "category": item["category"],
        "photos": photos,
        "is_visible": item["is_visible"],
        "date": item["created_at"][:16],
    }


@app.post("/api/portfolio")
async def api_portfolio_create(data: PortfolioIn):
    pid = await add_portfolio_item(
        data.title, data.description, data.specs,
        data.price_byn, data.price_rub, data.category,
    )
    return {"id": pid}


@app.put("/api/portfolio/{pid}")
async def api_portfolio_update(pid: int, data: PortfolioIn):
    item = await get_portfolio_item(pid)
    if not item:
        raise HTTPException(404)
    await update_portfolio(
        pid,
        title=data.title,
        description=data.description,
        specs=data.specs,
        price_byn=data.price_byn,
        price_rub=data.price_rub,
        category=data.category,
    )
    return {"ok": True}


@app.delete("/api/portfolio/{pid}")
async def api_portfolio_delete(pid: int):
    await delete_portfolio(pid)
    return {"ok": True}


@app.get("/api/portfolio/{pid}/photo/{file_id}")
async def api_portfolio_photo_url(pid: int, file_id: str):
    try:
        f = await bot.get_file(file_id)
        url = f"https://api.telegram.org/file/bot{config.BOT_TOKEN}/{f.file_path}"
        return {"url": url}
    except Exception:
        raise HTTPException(404, "Фото не найдено")


@app.post("/api/portfolio/{pid}/photo")
async def api_portfolio_upload_photo(pid: int, file: UploadFile = File(...)):
    """Загрузить фото через веб-панель: файл → бот → file_id → БД."""
    item = await get_portfolio_item(pid)
    if not item:
        raise HTTPException(404, "Работа не найдена")

    content = await file.read()
    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(400, "Макс. 10 МБ")

    suffix = ".jpg"
    if file.filename:
        ext = os.path.splitext(file.filename)[1].lower()
        if ext in (".png", ".webp", ".jpeg"):
            suffix = ext

    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(content)
            tmp_path = tmp.name

        if not config.MANAGER_GROUP_ID:
            raise HTTPException(500, "MANAGER_GROUP_ID не настроен")

        photo = FSInputFile(tmp_path)
        msg = await bot.send_photo(
            config.MANAGER_GROUP_ID, photo,
            caption=f"📷 Портфолио #{pid}",
        )

        file_id = msg.photo[-1].file_id
        await add_portfolio_photo(pid, file_id)
        return {"ok": True, "file_id": file_id}

    except HTTPException:
        raise
    except Exception as e:
        log.error(f"photo upload: {e}")
        raise HTTPException(500, str(e))
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)


@app.delete("/api/portfolio/{pid}/photo/{index}")
async def api_portfolio_delete_photo(pid: int, index: int):
    item = await get_portfolio_item(pid)
    if not item:
        raise HTTPException(404)
    await remove_portfolio_photo(pid, index)
    return {"ok": True}


@app.put("/api/portfolio/{pid}/visibility")
async def api_portfolio_toggle_visibility(pid: int):
    item = await get_portfolio_item(pid)
    if not item:
        raise HTTPException(404)
    new_vis = 0 if item["is_visible"] else 1
    await update_portfolio(pid, is_visible=new_vis)
    return {"ok": True, "is_visible": new_vis}


@app.get("/api/prices")
async def api_prices():
    return config.PRICES


# ════════════════════════════════════════════════════════════
#  BOT
# ════════════════════════════════════════════════════════════

bot = Bot(
    token=config.BOT_TOKEN,
    default=DefaultBotProperties(parse_mode="HTML"),
)
dp = Dispatcher()
router = Router()
dp.include_router(router)


class States(StatesGroup):
    waiting_photo = State()
    chatting      = State()
    waiting_oid   = State()
    waiting_price = State()
    pf_title      = State()
    pf_specs      = State()
    pf_price      = State()
    pf_desc       = State()
    pf_photo      = State()


# ════════════════════════════════════════════════════════════
#  УТИЛИТЫ
# ════════════════════════════════════════════════════════════

def _base():
    url = getattr(config, "WEBAPP_URL", "")
    return url.rstrip("/") if url else ""


def _admin_url(oid):
    b = _base()
    if not b:
        return None
    if b.endswith("/web"):
        return f"{b}/admin.html?order_id={oid}"
    return f"{b}/web/admin.html?order_id={oid}"


def _portfolio_url():
    b = _base()
    if not b:
        return None
    if b.endswith("/web"):
        return f"{b}/portfolio.html"
    return f"{b}/web/portfolio.html"


def _get_image(key: str):
    """FSInputFile из images/ или None."""
    images = getattr(config, "IMAGES", {})
    path = images.get(key, "")
    if path and os.path.isfile(path):
        return FSInputFile(path)
    return None


def _is_deferred(service_type: str) -> bool:
    return config.PRICES.get(service_type, {}).get("deferred_payment", False)


def _payment_text(oid, order):
    """Текст с реквизитами для клиента."""
    return (
        f"<b>Inside PC — Заказ #{oid}</b>\n\n"
        f"<b>К оплате: {order['price_byn']} BYN / {order['price_rub']} RUB</b>\n\n"
        f"<b>Реквизиты:</b>\n"
        f"Банк: {config.PAYMENT_BANK}\n"
        f"Карта: <code>{config.PAYMENT_CARD}</code>\n"
        f"Получатель: {config.PAYMENT_HOLDER}\n\n"
        f"Переведите и отправьте скриншот чека."
    )


def _payment_kb(oid):
    """Кнопка «Загрузить скриншот» для клиента."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="Загрузить скриншот",
            url=f"https://t.me/{config.BOT_USERNAME}?start=pay_{oid}",
        )],
    ])


# ════════════════════════════════════════════════════════════
#  SAFE SEND (откат стилей)
# ════════════════════════════════════════════════════════════

def _strip(mk):
    if not mk or not hasattr(mk, "inline_keyboard"):
        return mk
    rows = []
    for row in mk.inline_keyboard:
        nr = []
        for b in row:
            d = b.model_dump(exclude_none=True)
            d.pop("style", None)
            nr.append(InlineKeyboardButton(**d))
        rows.append(nr)
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def _retry(factory):
    global STYLE_OK
    try:
        return await factory(True)
    except TelegramBadRequest as e:
        if "invalid button style" in str(e).lower():
            STYLE_OK = False
            return await factory(False)
        raise


async def safe_send(cid, text, reply_markup=None, **kw):
    async def do(ok):
        mk = reply_markup if ok else _strip(reply_markup)
        return await bot.send_message(cid, text, reply_markup=mk, **kw)
    return await _retry(do)


async def safe_answer(msg, text, reply_markup=None, **kw):
    async def do(ok):
        mk = reply_markup if ok else _strip(reply_markup)
        return await msg.answer(text, reply_markup=mk, **kw)
    return await _retry(do)


async def safe_edit(msg, text, reply_markup=None, **kw):
    async def do(ok):
        mk = reply_markup if ok else _strip(reply_markup)
        return await msg.edit_text(text, reply_markup=mk, **kw)
    return await _retry(do)


async def safe_photo(cid, photo, caption=None, reply_markup=None, **kw):
    async def do(ok):
        mk = reply_markup if ok else _strip(reply_markup)
        return await bot.send_photo(cid, photo, caption=caption, reply_markup=mk, **kw)
    return await _retry(do)


async def _send_with_image(cid, img_key, text, reply_markup=None, **kw):
    """Отправить фото-заглушку + текст, или просто текст."""
    img = _get_image(img_key)
    if img:
        try:
            return await safe_photo(cid, img, caption=text, reply_markup=reply_markup, **kw)
        except Exception:
            pass
    return await safe_send(cid, text, reply_markup=reply_markup, **kw)


# ════════════════════════════════════════════════════════════
#  КЛАВИАТУРЫ
# ════════════════════════════════════════════════════════════

def kb_start():
    b = _base()
    rows = []
    if b:
        rows.append([InlineKeyboardButton(
            text="Оформить заявку", web_app=WebAppInfo(url=b))])
    rows.append([InlineKeyboardButton(
        text="Мои заказы", callback_data="my_orders", **S("primary"))])
    rows.append([InlineKeyboardButton(
        text="Проверить статус", callback_data="check_status")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def kb_orders(orders):
    rows = []
    for o in orders[:10]:
        s = STATUS_NAMES.get(o["status"], o["status"])
        n = config.PRICES.get(o["service_type"], {}).get("name", "?")
        st = {}
        if o["status"] in ("payment_confirmed", "completed"):
            st = S("success")
        elif o["status"] == "cancelled":
            st = S("danger")
        elif o["status"] == "in_progress":
            st = S("primary")
        rows.append([InlineKeyboardButton(
            text=f"#{o['id']}  {n}  {s}",
            callback_data=f"view:{o['id']}", **st)])
    rows.append([InlineKeyboardButton(text="Назад", callback_data="home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def kb_admin_pay(oid):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="✅ Подтвердить", callback_data=f"cpay:{oid}", **S("success"))],
        [InlineKeyboardButton(
            text="❌ Отклонить", callback_data=f"rpay:{oid}", **S("danger"))],
    ])


def kb_admin_manage(oid):
    rows = [
        [
            InlineKeyboardButton(
                text="В работу", callback_data=f"ss:{oid}:in_progress", **S("primary")),
            InlineKeyboardButton(
                text="Завершить", callback_data=f"ss:{oid}:completed", **S("success")),
        ],
        [InlineKeyboardButton(
            text="Отменить", callback_data=f"ss:{oid}:cancelled", **S("danger"))],
    ]
    link = _admin_url(oid)
    if link:
        rows.append([InlineKeyboardButton(text="Детали", url=link)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def kb_quote(oid):
    rows = [
        [InlineKeyboardButton(
            text="Назначить цену", callback_data=f"quote:{oid}", **S("primary"))],
        [InlineKeyboardButton(
            text="Отменить", callback_data=f"ss:{oid}:cancelled", **S("danger"))],
    ]
    link = _admin_url(oid)
    if link:
        rows.append([InlineKeyboardButton(text="Детали", url=link)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def kb_back():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Назад", callback_data="my_orders")]])


def kb_cancel():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Отмена", callback_data="home", **S("danger"))]])


def kb_pf_item(pid):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Название", callback_data=f"pf:title:{pid}"),
         InlineKeyboardButton(text="Характеристики", callback_data=f"pf:specs:{pid}")],
        [InlineKeyboardButton(text="Цена", callback_data=f"pf:price:{pid}"),
         InlineKeyboardButton(text="Описание", callback_data=f"pf:desc:{pid}")],
        [InlineKeyboardButton(
            text="Добавить фото", callback_data=f"pf:photo:{pid}", **S("primary"))],
        [InlineKeyboardButton(
            text="Удалить работу", callback_data=f"pf:del:{pid}", **S("danger"))],
        [InlineKeyboardButton(text="Назад к списку", callback_data="pf:list")],
    ])


def kb_pf_manage():
    url = _portfolio_url()
    rows = [
        [InlineKeyboardButton(
            text="➕ Добавить работу", callback_data="pf:new", **S("success"))],
        [InlineKeyboardButton(
            text="📋 Список работ", callback_data="pf:list", **S("primary"))],
    ]
    if url:
        rows.append([InlineKeyboardButton(text="🌐 Веб-панель", url=url)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


# ════════════════════════════════════════════════════════════
#  ТЕКСТ ЗАКАЗА (для группы менеджеров)
# ════════════════════════════════════════════════════════════

def _order_text(oid, order, uname, is_quote=False):
    sn = config.PRICES.get(order["service_type"], {}).get("name", "?")
    prefix = config.PRICES.get(order["service_type"], {}).get("prefix", "")

    if is_quote:
        label = "📋 ЗАЯВКА НА ОЦЕНКУ"
    else:
        label = "📋 НОВАЯ ЗАЯВКА"

    text = f"<b>{label} #{oid}</b>\n\nКлиент: {uname}\nУслуга: {sn}\n"

    if is_quote:
        text += (
            f"Мин. стоимость: {prefix}{order['price_byn']} BYN / "
            f"{prefix}{order['price_rub']} RUB\n\n"
            f"<b>Назначьте цену кнопкой ниже.</b>"
        )
    else:
        text += f"Стоимость: {order['price_byn']} BYN / {order['price_rub']} RUB"

    if order["has_parts"] and order["parts_data"]:
        try:
            parts = json.loads(order["parts_data"])
            lines = "".join(f"  — {k}: {v}\n" for k, v in parts.items() if v)
            if lines:
                text += f"\n\n<b>Комплектующие:</b>\n{lines}"
        except Exception:
            pass

    if order["description"]:
        text += f"\n\n<b>Описание:</b>\n{order['description']}"

    return text


# ════════════════════════════════════════════════════════════
#  ТОПИКИ
# ════════════════════════════════════════════════════════════

async def _create_topic(oid, uid, username=""):
    """Создать обычный топик для заказа."""
    if not config.MANAGER_GROUP_ID:
        return None

    order = await get_order(oid)
    if not order:
        return None

    sn = config.PRICES.get(order["service_type"], {}).get("name", "?")
    uname = f"@{username}" if username else f"ID:{uid}"

    try:
        t = await bot.create_forum_topic(
            chat_id=config.MANAGER_GROUP_ID,
            name=f"{uname} | {sn}",
        )
        tid = t.message_thread_id
        await save_topic(tid, oid, uid)
    except Exception as e:
        log.error(f"topic create: {e}")
        return None

    # Первое сообщение — информация о заказе
    text = _order_text(oid, order, uname)
    try:
        await safe_send(
            config.MANAGER_GROUP_ID, text,
            reply_markup=kb_admin_manage(oid),
            message_thread_id=tid,
        )
    except Exception as e:
        log.error(f"topic msg: {e}")

    # Второе сообщение — предупреждение об отложенной оплате
    if _is_deferred(order["service_type"]):
        try:
            await safe_send(
                config.MANAGER_GROUP_ID,
                "⚠️ <b>Внимание!</b> Услуга с отложенной оплатой.\n\n"
                "После согласования напишите в чат слово <b>оплата</b> — "
                "бот отправит клиенту реквизиты.",
                message_thread_id=tid,
            )
        except Exception as e:
            log.error(f"deferred notice: {e}")

    return tid


async def _handle_new_quote(oid, uid, username=""):
    """Создать топик для заказа с оценкой (сборка/апгрейд)."""
    if not config.MANAGER_GROUP_ID:
        return

    order = await get_order(oid)
    if not order:
        return

    sn = config.PRICES.get(order["service_type"], {}).get("name", "?")
    uname = f"@{username}" if username else f"ID:{uid}"

    try:
        t = await bot.create_forum_topic(
            chat_id=config.MANAGER_GROUP_ID,
            name=f"{uname} | {sn}",
            icon_color=7322096,
        )
        tid = t.message_thread_id
        await save_topic(tid, oid, uid)
    except Exception as e:
        log.error(f"quote topic: {e}")
        return

    # Первое сообщение
    text = _order_text(oid, order, uname, is_quote=True)
    try:
        await safe_send(
            config.MANAGER_GROUP_ID, text,
            reply_markup=kb_quote(oid),
            message_thread_id=tid,
        )
    except Exception as e:
        log.error(f"quote msg: {e}")

    # Второе сообщение — предупреждение
    if _is_deferred(order["service_type"]):
        try:
            await safe_send(
                config.MANAGER_GROUP_ID,
                "⚠️ <b>Внимание!</b> Услуга с отложенной оплатой.\n\n"
                "После согласования напишите в чат слово <b>оплата</b> — "
                "бот отправит клиенту реквизиты.",
                message_thread_id=tid,
            )
        except Exception as e:
            log.error(f"deferred notice: {e}")

    # Уведомление клиенту
    try:
        await bot.send_message(
            uid,
            f"<b>Inside PC — Заявка #{oid}</b>\n\n"
            f"Заявка на {sn.lower()} отправлена менеджеру.\n"
            f"Мы рассчитаем стоимость и отправим реквизиты.",
        )
    except Exception as e:
        log.error(f"quote user notify: {e}")


# ════════════════════════════════════════════════════════════
#  ПЕРЕСЫЛКА СООБЩЕНИЙ
# ════════════════════════════════════════════════════════════

async def relay_to_topic(msg: Message, oid: int) -> bool:
    """Клиент → топик менеджера."""
    link = await get_topic_by_order(oid)
    if not link:
        return False

    tid = link["topic_id"]
    kw = {"message_thread_id": tid}

    try:
        if msg.photo:
            await bot.send_photo(
                config.MANAGER_GROUP_ID, msg.photo[-1].file_id,
                caption=f"<b>Клиент:</b>\n{msg.caption or ''}", **kw)
        elif msg.video:
            await bot.send_video(
                config.MANAGER_GROUP_ID, msg.video.file_id,
                caption=f"<b>Клиент:</b>\n{msg.caption or ''}", **kw)
        elif msg.document:
            await bot.send_document(
                config.MANAGER_GROUP_ID, msg.document.file_id,
                caption=f"<b>Клиент:</b>\n{msg.caption or ''}", **kw)
        elif msg.voice:
            await bot.send_voice(
                config.MANAGER_GROUP_ID, msg.voice.file_id,
                caption="<b>Клиент</b>", **kw)
        elif msg.video_note:
            await bot.send_video_note(
                config.MANAGER_GROUP_ID, msg.video_note.file_id, **kw)
        elif msg.sticker:
            await bot.send_sticker(
                config.MANAGER_GROUP_ID, msg.sticker.file_id, **kw)
        elif msg.text:
            await bot.send_message(
                config.MANAGER_GROUP_ID,
                f"<b>Клиент:</b>\n\n{msg.text}", **kw)
        else:
            await bot.forward_message(
                config.MANAGER_GROUP_ID, msg.chat.id, msg.message_id, **kw)
        return True
    except Exception as e:
        log.error(f"relay→topic: {e}")
        return False


async def relay_to_user(msg: Message, uid: int) -> bool:
    """Топик менеджера → клиент."""
    try:
        if msg.photo:
            await bot.send_photo(
                uid, msg.photo[-1].file_id,
                caption=f"<b>Inside PC:</b>\n{msg.caption or ''}")
        elif msg.video:
            await bot.send_video(
                uid, msg.video.file_id,
                caption=f"<b>Inside PC:</b>\n{msg.caption or ''}")
        elif msg.document:
            await bot.send_document(
                uid, msg.document.file_id,
                caption=f"<b>Inside PC:</b>\n{msg.caption or ''}")
        elif msg.voice:
            await bot.send_voice(
                uid, msg.voice.file_id, caption="<b>Inside PC:</b>")
        elif msg.video_note:
            await bot.send_video_note(uid, msg.video_note.file_id)
        elif msg.sticker:
            await bot.send_sticker(uid, msg.sticker.file_id)
        elif msg.text:
            await bot.send_message(uid, f"<b>Inside PC:</b>\n\n{msg.text}")
        else:
            await bot.forward_message(uid, msg.chat.id, msg.message_id)
        return True
    except Exception as e:
        log.error(f"relay→user: {e}")
        return False


# ════════════════════════════════════════════════════════════
#  ХЭНДЛЕРЫ: СТАРТ / СТОП
# ════════════════════════════════════════════════════════════

@router.message(CommandStart())
async def cmd_start(msg: Message, state: FSMContext, command: CommandObject):
    await upsert_user(
        msg.from_user.id,
        msg.from_user.username or "",
        msg.from_user.full_name or "",
    )

    args = command.args

    # Диплинк оплаты: /start pay_ID
    if args and args.startswith("pay_"):
        try:
            oid = int(args[4:])
            order = await get_order(oid)
            if order and order["user_id"] == msg.from_user.id:
                if order["status"] == "pending_payment":
                    await state.set_state(States.waiting_photo)
                    await state.update_data(order_id=oid)
                    await _send_with_image(
                        msg.chat.id, "payment",
                        _payment_text(oid, order),
                        reply_markup=kb_cancel(),
                    )
                    return
                elif order["status"] == "pending_quote":
                    await safe_answer(
                        msg,
                        f"<b>Заказ #{oid}</b>\n\nОжидает оценки менеджером.",
                        reply_markup=kb_start(),
                    )
                    return
        except (ValueError, TypeError):
            pass

    await state.clear()

    # Проверяем активный заказ
    active = await get_active_order(msg.from_user.id)
    if active:
        order = await get_order(active)
        if order and order["status"] in ("in_progress", "payment_confirmed"):
            await safe_answer(
                msg,
                f"<b>Inside PC</b>\n\n"
                f"Активный заказ #{active}.\n"
                f"Все сообщения пересылаются менеджеру.\n"
                f"/stop — выйти из чата.",
                reply_markup=kb_start(),
            )
            return

    await _send_with_image(
        msg.chat.id, "start",
        "<b>Inside PC</b>\n\n"
        "Сборка, апгрейд и консультации по компьютерам.\n"
        "Нажмите <b>Оформить заявку</b> чтобы начать.",
        reply_markup=kb_start(),
    )


@router.message(Command("stop"))
async def cmd_stop(msg: Message, state: FSMContext):
    await state.clear()
    await set_active_order(msg.from_user.id, 0)
    await safe_answer(
        msg,
        "<b>Inside PC</b>\n\nВы вышли из чата с менеджером.",
        reply_markup=kb_start(),
    )


# ════════════════════════════════════════════════════════════
#  ХЭНДЛЕРЫ: /portfolio (меню вместо топика)
# ════════════════════════════════════════════════════════════

@router.message(Command("portfolio"))
async def cmd_portfolio(msg: Message):
    if msg.chat.id == config.MANAGER_GROUP_ID:
        await safe_answer(
            msg,
            "📸 <b>Управление портфолио</b>\n\n"
            "Добавляйте и редактируйте работы.",
            reply_markup=kb_pf_manage(),
        )


# ════════════════════════════════════════════════════════════
#  ХЭНДЛЕРЫ: НАВИГАЦИЯ
# ════════════════════════════════════════════════════════════

@router.callback_query(F.data == "home")
async def go_home(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    try:
        await safe_edit(
            cb.message,
            "<b>Inside PC</b>\n\nВыберите действие:",
            reply_markup=kb_start(),
        )
    except Exception:
        await safe_answer(
            cb.message,
            "<b>Inside PC</b>\n\nВыберите действие:",
            reply_markup=kb_start(),
        )
    await cb.answer()


@router.callback_query(F.data == "my_orders")
async def my_orders(cb: CallbackQuery):
    orders = await get_user_orders(cb.from_user.id)
    text = "<b>Ваши заказы:</b>" if orders else "Заказов пока нет."
    kb = kb_orders(orders) if orders else kb_start()
    try:
        await safe_edit(cb.message, text, reply_markup=kb)
    except Exception:
        await safe_answer(cb.message, text, reply_markup=kb)
    await cb.answer()


# ════════════════════════════════════════════════════════════
#  ХЭНДЛЕРЫ: ПРОСМОТР ЗАКАЗА
# ════════════════════════════════════════════════════════════

@router.callback_query(F.data.startswith("view:"))
async def view_order(cb: CallbackQuery, state: FSMContext):
    oid = int(cb.data.split(":")[1])
    order = await get_order(oid)
    if not order:
        await cb.answer("Не найден", show_alert=True)
        return

    p = config.PRICES.get(order["service_type"], {})
    st = STATUS_NAMES.get(order["status"], order["status"])
    pfx = p.get("prefix", "")

    text = (
        f"<b>Заказ #{oid}</b>\n\n"
        f"Услуга: {p.get('name', '?')}\n"
        f"Стоимость: {pfx}{order['price_byn']} BYN / {pfx}{order['price_rub']} RUB\n"
        f"Статус: {st}"
    )

    if order["status"] == "pending_payment":
        text += (
            f"\n\nКарта: <code>{config.PAYMENT_CARD}</code>\n"
            f"Отправьте скриншот оплаты."
        )
        await state.set_state(States.waiting_photo)
        await state.update_data(order_id=oid)
    elif order["status"] in ("payment_confirmed", "in_progress"):
        text += "\n\nВсе сообщения пересылаются менеджеру."
        await state.set_state(States.chatting)
        await state.update_data(order_id=oid)

    try:
        await cb.message.edit_text(text, reply_markup=kb_back())
    except Exception:
        await cb.message.answer(text, reply_markup=kb_back())
    await cb.answer()


@router.callback_query(F.data == "check_status")
async def ask_oid(cb: CallbackQuery, state: FSMContext):
    try:
        await cb.message.edit_text("Введите номер заказа:")
    except Exception:
        await cb.message.answer("Введите номер заказа:")
    await state.set_state(States.waiting_oid)
    await cb.answer()


@router.message(States.waiting_oid, F.text)
async def process_oid(msg: Message, state: FSMContext):
    try:
        oid = int(msg.text.strip().replace("#", ""))
    except ValueError:
        await msg.answer("Введите число.")
        return

    order = await get_order(oid)
    if not order or order["user_id"] != msg.from_user.id:
        await safe_answer(msg, "Заказ не найден.", reply_markup=kb_start())
        await state.clear()
        return

    st = STATUS_NAMES.get(order["status"], order["status"])
    await safe_answer(
        msg,
        f"<b>Заказ #{oid}</b>\nСтатус: {st}",
        reply_markup=kb_start(),
    )
    await state.clear()


# ════════════════════════════════════════════════════════════
#  ХЭНДЛЕРЫ: ОПЛАТА (фото чека)
# ════════════════════════════════════════════════════════════

@router.message(States.waiting_photo, F.photo)
async def recv_photo(msg: Message, state: FSMContext):
    data = await state.get_data()
    oid = data.get("order_id")

    if not oid:
        p = await get_latest_pending_order(msg.from_user.id)
        oid = p["id"] if p else None

    if not oid:
        await safe_answer(msg, "Нет активных заказов.", reply_markup=kb_start())
        await state.clear()
        return

    fid = msg.photo[-1].file_id
    await save_payment_photo(oid, fid)

    user = await get_user(msg.from_user.id)
    existing = await get_topic_by_order(oid)
    tid = existing["topic_id"] if existing else None

    if not tid:
        tid = await _create_topic(
            oid, msg.from_user.id,
            user["username"] if user else "",
        )

    if config.MANAGER_GROUP_ID and tid:
        try:
            await safe_photo(
                config.MANAGER_GROUP_ID, fid,
                caption=f"💳 <b>Фото оплаты #{oid}</b>",
                reply_markup=kb_admin_pay(oid),
                message_thread_id=tid,
            )
        except Exception as e:
            log.error(f"photo→mgr: {e}")

    await safe_answer(
        msg,
        f"<b>Скриншот получен</b>\n"
        f"Заказ #{oid} — ожидайте подтверждения.",
        reply_markup=kb_start(),
    )
    await state.clear()


# ════════════════════════════════════════════════════════════
#  ХЭНДЛЕРЫ: НАЗНАЧЕНИЕ ЦЕНЫ (QUOTE)
# ════════════════════════════════════════════════════════════

@router.callback_query(F.data.startswith("quote:"))
async def quote_start(cb: CallbackQuery, state: FSMContext):
    oid = int(cb.data.split(":")[1])
    order = await get_order(oid)
    if not order or order["status"] != "pending_quote":
        await cb.answer("Уже оценён", show_alert=True)
        return

    await state.set_state(States.waiting_price)
    await state.update_data(
        quote_oid=oid,
        quote_tid=getattr(cb.message, "message_thread_id", None),
    )

    # cb.message.answer сам подставит message_thread_id
    await cb.message.answer(
        f"<b>Цена для #{oid}</b>\n\n"
        f"Введите: <code>BYN RUB</code>\n"
        f"Пример: <code>150 4000</code>",
    )
    await cb.answer()


@router.message(States.waiting_price, F.text)
async def quote_process(msg: Message, state: FSMContext):
    data = await state.get_data()
    oid = data.get("quote_oid")
    tid = data.get("quote_tid")

    if not oid:
        await state.clear()
        return

    if msg.text.strip().lower() in ("отмена", "cancel"):
        await state.clear()
        await msg.answer("Отменено.")
        return

    parts = msg.text.strip().replace(",", " ").replace("/", " ").split()
    if len(parts) != 2:
        await msg.answer("Формат: <code>BYN RUB</code>")
        return

    try:
        byn, rub = float(parts[0]), float(parts[1])
    except ValueError:
        await msg.answer("Введите два числа.")
        return

    if byn <= 0 or rub <= 0:
        await msg.answer("Цена должна быть больше 0.")
        return

    await set_order_price(oid, byn, rub)
    order = await get_order(oid)

    # Уведомляем клиента
    try:
        await bot.send_message(
            order["user_id"],
            f"<b>Inside PC — Заказ #{oid}</b>\n\n"
            f"Менеджер рассчитал стоимость:\n"
            f"<b>{byn} BYN / {rub} RUB</b>\n\n"
            f"<b>Реквизиты:</b>\n"
            f"Банк: {config.PAYMENT_BANK}\n"
            f"Карта: <code>{config.PAYMENT_CARD}</code>\n"
            f"Получатель: {config.PAYMENT_HOLDER}\n\n"
            f"Переведите и нажмите кнопку ниже.",
            reply_markup=_payment_kb(oid),
        )
    except Exception as e:
        log.error(f"quote→user: {e}")

    # Подтверждение в топике
    extra = {"message_thread_id": tid} if tid else {}
    try:
        await safe_send(
            config.MANAGER_GROUP_ID,
            f"✅ <b>Цена #{oid}:</b> {byn} BYN / {rub} RUB\n"
            f"Клиент уведомлён.",
            reply_markup=kb_admin_manage(oid),
            **extra,
        )
    except Exception as e:
        log.error(f"quote→grp: {e}")

    await msg.answer(f"Цена назначена для заказа #{oid}.")
    await state.clear()


# ════════════════════════════════════════════════════════════
#  ХЭНДЛЕРЫ: ПОРТФОЛИО (бот-сторона)
# ════════════════════════════════════════════════════════════

@router.callback_query(F.data == "pf:new")
async def pf_new(cb: CallbackQuery, state: FSMContext):
    pid = await add_portfolio_item()
    await state.set_state(States.pf_title)
    await state.update_data(pf_id=pid)
    await cb.message.answer(f"<b>Новая работа #{pid}</b>\n\nВведите название:")
    await cb.answer()


@router.callback_query(F.data == "pf:list")
async def pf_list(cb: CallbackQuery):
    items = await get_portfolio_all()
    if not items:
        await cb.message.answer(
            "Портфолио пусто. Нажмите <b>Добавить работу</b>.",
            reply_markup=kb_pf_manage(),
        )
        await cb.answer()
        return

    rows = []
    for item in items:
        title = item["title"] or f"Без названия #{item['id']}"
        try:
            pc = len(json.loads(item["photo_ids"]))
        except Exception:
            pc = 0
        rows.append([InlineKeyboardButton(
            text=f"#{item['id']}  {title}  ({pc} фото)",
            callback_data=f"pf:edit:{item['id']}",
        )])

    rows.append([InlineKeyboardButton(
        text="➕ Добавить работу", callback_data="pf:new", **S("success"))])

    await cb.message.answer(
        "<b>📸 Портфолио:</b>",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
    )
    await cb.answer()


@router.callback_query(F.data.startswith("pf:edit:"))
async def pf_edit(cb: CallbackQuery):
    pid = int(cb.data.split(":")[2])
    item = await get_portfolio_item(pid)
    if not item:
        await cb.answer("Не найдено", show_alert=True)
        return

    try:
        photos = json.loads(item["photo_ids"])
    except Exception:
        photos = []

    text = (
        f"<b>Работа #{pid}</b>\n\n"
        f"<b>Название:</b> {item['title'] or '—'}\n"
        f"<b>Характеристики:</b> {item['specs'] or '—'}\n"
        f"<b>Цена:</b> {item['price_byn']} BYN / {item['price_rub']} RUB\n"
        f"<b>Описание:</b> {item['description'] or '—'}\n"
        f"<b>Фото:</b> {len(photos)} шт."
    )
    await cb.message.answer(text, reply_markup=kb_pf_item(pid))
    await cb.answer()


@router.callback_query(F.data.startswith("pf:title:"))
async def pf_set_title(cb: CallbackQuery, state: FSMContext):
    pid = int(cb.data.split(":")[2])
    await state.set_state(States.pf_title)
    await state.update_data(pf_id=pid)
    await cb.message.answer("Введите название:")
    await cb.answer()


@router.message(States.pf_title, F.text)
async def pf_title_input(msg: Message, state: FSMContext):
    data = await state.get_data()
    pid = data["pf_id"]
    await update_portfolio(pid, title=msg.text.strip())
    await msg.answer("Название обновлено.", reply_markup=kb_pf_item(pid))
    await state.clear()


@router.callback_query(F.data.startswith("pf:specs:"))
async def pf_set_specs(cb: CallbackQuery, state: FSMContext):
    pid = int(cb.data.split(":")[2])
    await state.set_state(States.pf_specs)
    await state.update_data(pf_id=pid)
    await cb.message.answer(
        "Введите характеристики:\n"
        "<i>Каждая строка — отдельная характеристика</i>",
    )
    await cb.answer()


@router.message(States.pf_specs, F.text)
async def pf_specs_input(msg: Message, state: FSMContext):
    data = await state.get_data()
    pid = data["pf_id"]
    await update_portfolio(pid, specs=msg.text.strip())
    await msg.answer("Характеристики обновлены.", reply_markup=kb_pf_item(pid))
    await state.clear()


@router.callback_query(F.data.startswith("pf:price:"))
async def pf_set_price(cb: CallbackQuery, state: FSMContext):
    pid = int(cb.data.split(":")[2])
    await state.set_state(States.pf_price)
    await state.update_data(pf_id=pid)
    await cb.message.answer(
        "Цена: <code>BYN RUB</code>\nПример: <code>3000 80000</code>")
    await cb.answer()


@router.message(States.pf_price, F.text)
async def pf_price_input(msg: Message, state: FSMContext):
    data = await state.get_data()
    pid = data["pf_id"]
    parts = msg.text.strip().replace(",", " ").replace("/", " ").split()
    if len(parts) != 2:
        await msg.answer("Формат: <code>BYN RUB</code>")
        return
    try:
        byn, rub = float(parts[0]), float(parts[1])
    except ValueError:
        await msg.answer("Введите два числа.")
        return
    await update_portfolio(pid, price_byn=byn, price_rub=rub)
    await msg.answer("Цена обновлена.", reply_markup=kb_pf_item(pid))
    await state.clear()


@router.callback_query(F.data.startswith("pf:desc:"))
async def pf_set_desc(cb: CallbackQuery, state: FSMContext):
    pid = int(cb.data.split(":")[2])
    await state.set_state(States.pf_desc)
    await state.update_data(pf_id=pid)
    await cb.message.answer("Введите описание:")
    await cb.answer()


@router.message(States.pf_desc, F.text)
async def pf_desc_input(msg: Message, state: FSMContext):
    data = await state.get_data()
    pid = data["pf_id"]
    await update_portfolio(pid, description=msg.text.strip())
    await msg.answer("Описание обновлено.", reply_markup=kb_pf_item(pid))
    await state.clear()


@router.callback_query(F.data.startswith("pf:photo:"))
async def pf_add_photo(cb: CallbackQuery, state: FSMContext):
    pid = int(cb.data.split(":")[2])
    await state.set_state(States.pf_photo)
    await state.update_data(pf_id=pid)
    await cb.message.answer(
        "Отправьте фото (можно несколько).\n"
        "Когда закончите — напишите <b>готово</b>.",
    )
    await cb.answer()


@router.message(States.pf_photo, F.photo)
async def pf_photo_input(msg: Message, state: FSMContext):
    data = await state.get_data()
    pid = data["pf_id"]
    fid = msg.photo[-1].file_id
    await add_portfolio_photo(pid, fid)
    item = await get_portfolio_item(pid)
    try:
        cnt = len(json.loads(item["photo_ids"]))
    except Exception:
        cnt = 0
    await msg.answer(f"Фото добавлено. Всего: {cnt}. Ещё или <b>готово</b>.")


@router.message(States.pf_photo, F.text)
async def pf_photo_done(msg: Message, state: FSMContext):
    if msg.text.strip().lower() in ("готово", "done", "стоп"):
        data = await state.get_data()
        pid = data["pf_id"]
        await state.clear()
        await msg.answer("Фото сохранены.", reply_markup=kb_pf_item(pid))
    else:
        await msg.answer("Отправьте фото или напишите <b>готово</b>.")


@router.callback_query(F.data.startswith("pf:del:"))
async def pf_delete(cb: CallbackQuery):
    pid = int(cb.data.split(":")[2])
    await delete_portfolio(pid)
    await cb.message.answer(
        f"Работа #{pid} удалена.", reply_markup=kb_pf_manage())
    await cb.answer()


# ════════════════════════════════════════════════════════════
#  ХЭНДЛЕРЫ: ЧАТ / ПЕРЕСЫЛКА
# ════════════════════════════════════════════════════════════

@router.message(States.chatting, F.chat.type == "private")
async def chat_any(msg: Message, state: FSMContext):
    data = await state.get_data()
    oid = data.get("order_id")
    if oid and await relay_to_topic(msg, oid):
        await msg.answer("Отправлено.")


@router.message(F.chat.type == "private", ~F.text.startswith("/"))
async def auto_relay(msg: Message, state: FSMContext):
    if await state.get_state():
        return
    oid = await get_active_order(msg.from_user.id)
    if oid:
        await relay_to_topic(msg, oid)


@router.message(F.message_thread_id)
async def mgr_any(msg: Message):
    """Сообщения в топиках группы менеджеров.
    Если слово 'оплата' — отправить реквизиты клиенту.
    Иначе — переслать клиенту."""
    if msg.chat.id != config.MANAGER_GROUP_ID:
        return
    if msg.from_user.is_bot:
        return

    link = await get_topic_link(msg.message_thread_id)
    if not link:
        return

    # ── Команда «оплата» ──
    if msg.text and msg.text.strip().lower() == "оплата":
        oid = link["order_id"]
        uid = link["user_id"]
        order = await get_order(oid)
        if not order:
            return

        try:
            await bot.send_message(
                uid,
                f"<b>Inside PC — Заказ #{oid}</b>\n\n"
                f"<b>К оплате: {order['price_byn']} BYN / {order['price_rub']} RUB</b>\n\n"
                f"<b>Реквизиты:</b>\n"
                f"Банк: {config.PAYMENT_BANK}\n"
                f"Карта: <code>{config.PAYMENT_CARD}</code>\n"
                f"Получатель: {config.PAYMENT_HOLDER}\n\n"
                f"Переведите и нажмите кнопку ниже.",
                reply_markup=_payment_kb(oid),
            )
        except Exception as e:
            log.error(f"оплата→user: {e}")

        try:
            await bot.send_message(
                config.MANAGER_GROUP_ID,
                f"✅ Реквизиты для заказа #{oid} отправлены клиенту.",
                message_thread_id=msg.message_thread_id,
            )
        except Exception as e:
            log.error(f"оплата confirm: {e}")
        return

    # ── Обычная пересылка ──
    await relay_to_user(msg, link["user_id"])


# ════════════════════════════════════════════════════════════
#  ХЭНДЛЕРЫ: ПОДТВЕРЖДЕНИЕ / ОТКЛОНЕНИЕ ОПЛАТЫ
# ════════════════════════════════════════════════════════════

@router.callback_query(F.data.startswith("cpay:"))
async def confirm_pay(cb: CallbackQuery):
    oid = int(cb.data.split(":")[1])
    await update_status(oid, "payment_confirmed")
    order = await get_order(oid)

    try:
        await bot.send_message(
            order["user_id"],
            f"<b>Inside PC — Заказ #{oid}</b>\n\nОплата подтверждена.",
        )
    except Exception:
        pass

    try:
        await cb.message.edit_caption(
            caption=f"✅ <b>#{oid} — ОПЛАТА ПОДТВЕРЖДЕНА</b>")
    except Exception:
        try:
            await cb.message.edit_text(
                f"✅ <b>#{oid} — ОПЛАТА ПОДТВЕРЖДЕНА</b>")
        except Exception:
            pass

    await cb.answer("Подтверждено")


@router.callback_query(F.data.startswith("rpay:"))
async def reject_pay(cb: CallbackQuery):
    oid = int(cb.data.split(":")[1])
    await update_status(oid, "pending_payment")
    order = await get_order(oid)

    try:
        await bot.send_message(
            order["user_id"],
            f"<b>Inside PC — Заказ #{oid}</b>\n\n"
            f"Оплата отклонена. Проверьте реквизиты и отправьте повторно.",
        )
    except Exception:
        pass

    try:
        await cb.message.edit_caption(
            caption=f"❌ <b>#{oid} — ОПЛАТА ОТКЛОНЕНА</b>")
    except Exception:
        try:
            await cb.message.edit_text(
                f"❌ <b>#{oid} — ОПЛАТА ОТКЛОНЕНА</b>")
        except Exception:
            pass

    await cb.answer("Отклонено")


# ════════════════════════════════════════════════════════════
#  ХЭНДЛЕРЫ: УПРАВЛЕНИЕ СТАТУСАМИ
# ════════════════════════════════════════════════════════════

@router.callback_query(F.data.startswith("ss:"))
async def set_status(cb: CallbackQuery):
    p = cb.data.split(":")
    oid, new_status = int(p[1]), p[2]

    await update_status(oid, new_status)
    order = await get_order(oid)
    st = STATUS_NAMES.get(new_status, new_status)

    # Уведомление клиенту
    if new_status == "in_progress":
        await set_active_order(order["user_id"], oid)
        try:
            await bot.send_message(
                order["user_id"],
                f"<b>Inside PC — Заказ #{oid}</b>\n\n"
                f"Заказ принят в работу.\n"
                f"Все сообщения пересылаются менеджеру.\n"
                f"/stop — выйти из чата.",
            )
        except Exception:
            pass

    elif new_status in ("completed", "cancelled"):
        await set_active_order(order["user_id"], 0)
        try:
            await bot.send_message(
                order["user_id"],
                f"<b>Inside PC — Заказ #{oid}</b>\n\nСтатус: {st}",
            )
        except Exception:
            pass

    # Сообщение в топике
    tid = getattr(cb.message, "message_thread_id", None)
    extra = {"message_thread_id": tid} if tid else {}
    try:
        await safe_send(
            config.MANAGER_GROUP_ID,
            f"📌 #{oid}: {st}",
            reply_markup=kb_admin_manage(oid),
            **extra,
        )
    except Exception:
        pass

    await cb.answer(st)