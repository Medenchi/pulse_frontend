import os
import uuid
import json
import asyncio
import logging
from datetime import datetime

from dotenv import load_dotenv
from supabase import create_client, Client

from aiogram import Bot, Dispatcher, Router, F
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    WebAppInfo,
    FSInputFile,
    MenuButtonWebApp,
)
from aiogram.filters import Command, CommandStart, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.enums import ContentType

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import uvicorn

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# ==================== CONFIG ====================

BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
ADMIN_GROUP_ID = int(os.environ.get("ADMIN_GROUP_ID", "0"))
WEBAPP_URL = os.environ.get("WEBAPP_URL", "https://malinacode.is-a.dev/app")
HOST = "0.0.0.0"
PORT = int(os.environ.get("PORT", "8080"))
BOT_USERNAME = os.environ.get("BOT_USERNAME", "PulseComputersShop_bot")
ADMIN_IDS = [int(x) for x in os.environ.get("ADMIN_IDS", "0").split(",") if x.strip()]
ADMIN_PERSONAL_LINK = os.environ.get("ADMIN_PERSONAL_LINK", "https://t.me/Pulse_Gadgets1")
TAPLINK_URL = os.environ.get("TAPLINK_URL", "https://pulsegadgets.taplink.ws")
SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://qsvztyhszwauwkxfmirs.supabase.co")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")
MANAGER_DEEPLINK = f"https://t.me/{BOT_USERNAME}?start=manager"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ASSETS_PATH = os.path.join(BASE_DIR, "frontend", "assets")
FRONTEND_PATH = os.path.join(BASE_DIR, "frontend")
BOT_IMAGES_PATH = os.path.join(ASSETS_PATH, "bot_images")
DATA_PATH = os.path.join(BASE_DIR, "data")

os.makedirs(ASSETS_PATH, exist_ok=True)
os.makedirs(BOT_IMAGES_PATH, exist_ok=True)
os.makedirs(DATA_PATH, exist_ok=True)

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)
router = Router()
dp.include_router(router)

ORDER_STATUSES = {
    "processing": "В обработке",
    "delivery": "Доставка",
    "diagnostics": "Принят на диагностику",
    "in_progress": "В работе",
    "ready": "Готов к выдаче",
    "delayed": "Задерживается",
    "waiting_parts": "Ожидаем поставку комплектующих",
    "completed": "Завершен",
    "cancelled": "Отменен",
}

# ==================== JSON Data ====================

SERVICES_FILE = os.path.join(DATA_PATH, "services.json")
BUILDS_FILE = os.path.join(DATA_PATH, "builds.json")

DEFAULT_SERVICES = [
    {"id": 1, "title": "Сборка компьютера из ваших комплектующих", "description": "Профессиональная сборка ПК с тестированием и настройкой", "price_text": "7% от стоимости комплектующих", "price_from": 0, "icon": "ph-bold ph-desktop-tower", "payment": "prepay",
     "form_fields": [
         {"id": "contact", "label": "Контакт для связи", "type": "text", "placeholder": "Телефон или @telegram", "required": True},
         {"id": "components", "label": "Список комплектующих", "type": "textarea", "placeholder": "Перечислите все комплектующие", "required": True},
         {"id": "total_cost", "label": "Общая стоимость (руб.)", "type": "number", "placeholder": "100000", "required": True},
         {"id": "notes", "label": "Пожелания", "type": "textarea", "placeholder": "Доп. пожелания", "required": False},
     ]},
    {"id": 2, "title": "Подбор комплектующих", "description": "Индивидуальный подбор компонентов под задачи и бюджет", "price_text": "500 руб.", "price_from": 500, "icon": "ph-bold ph-list-magnifying-glass", "payment": "prepay",
     "form_fields": [
         {"id": "contact", "label": "Контакт для связи", "type": "text", "placeholder": "Телефон или @telegram", "required": True},
         {"id": "budget", "label": "Бюджет (руб.)", "type": "number", "placeholder": "50000", "required": True},
         {"id": "tasks", "label": "Для каких задач", "type": "select", "options": ["Игры", "Офис", "Графика / Видеомонтаж", "Звук / Музыка", "Домашний ПК", "Стриминг", "Сервер"], "required": True},
         {"id": "notes", "label": "Пожелания", "type": "textarea", "placeholder": "Предпочтения по брендам", "required": False},
     ]},
    {"id": 3, "title": "Чистка + обслуживание ноутбуков", "description": "Полная разборка, чистка от пыли, замена термопасты", "price_text": "от 1 500 руб.", "price_from": 1500, "icon": "ph-bold ph-laptop", "payment": "postpay",
     "form_fields": [
         {"id": "contact", "label": "Контакт для связи", "type": "text", "placeholder": "Телефон или @telegram", "required": True},
         {"id": "device", "label": "Модель ноутбука", "type": "text", "placeholder": "ASUS ROG Strix G15", "required": True},
         {"id": "issue", "label": "Жалобы", "type": "textarea", "placeholder": "Перегревается, шумит", "required": True},
     ]},
    {"id": 4, "title": "Чистка + обслуживание компьютера", "description": "Чистка системного блока, замена термоинтерфейса", "price_text": "от 1 000 руб.", "price_from": 1000, "icon": "ph-bold ph-desktop", "payment": "postpay",
     "form_fields": [
         {"id": "contact", "label": "Контакт для связи", "type": "text", "placeholder": "Телефон или @telegram", "required": True},
         {"id": "device", "label": "Конфигурация", "type": "text", "placeholder": "Процессор, видеокарта...", "required": True},
         {"id": "issue", "label": "Жалобы", "type": "textarea", "placeholder": "Перегревается, шумит", "required": True},
     ]},
    {"id": 5, "title": "Чистка + обслуживание видеокарт", "description": "Разборка, чистка радиатора, замена термопасты и термопрокладок", "price_text": "от 1 000 руб.", "price_from": 1000, "icon": "ph-bold ph-graphics-card", "payment": "postpay",
     "form_fields": [
         {"id": "contact", "label": "Контакт для связи", "type": "text", "placeholder": "Телефон или @telegram", "required": True},
         {"id": "device", "label": "Модель видеокарты", "type": "text", "placeholder": "RTX 4070 Ti", "required": True},
         {"id": "issue", "label": "Жалобы", "type": "textarea", "placeholder": "Перегревается, артефакты", "required": True},
     ]},
    {"id": 6, "title": "Установка ОС под ключ", "description": "Установка Windows с драйверами и настройкой", "price_text": "2 000 руб.", "price_from": 2000, "icon": "ph-bold ph-windows-logo", "payment": "postpay",
     "form_fields": [
         {"id": "contact", "label": "Контакт для связи", "type": "text", "placeholder": "Телефон или @telegram", "required": True},
         {"id": "device", "label": "Устройство", "type": "text", "placeholder": "Модель", "required": True},
         {"id": "os_version", "label": "Версия Windows", "type": "select", "options": ["Windows 10", "Windows 11", "Windows 7", "Windows 8.1", "Другое"], "required": True},
     ]},
    {"id": 7, "title": "Установка приложений и софта", "description": "Установка и настройка ПО", "price_text": "от 200 руб.", "price_from": 200, "icon": "ph-bold ph-app-window", "payment": "postpay",
     "form_fields": [
         {"id": "contact", "label": "Контакт для связи", "type": "text", "placeholder": "Телефон или @telegram", "required": True},
         {"id": "device", "label": "Устройство", "type": "text", "placeholder": "Модель", "required": True},
         {"id": "software_list", "label": "Список программ", "type": "textarea", "placeholder": "Какие программы установить", "required": True},
     ]},
    {"id": 8, "title": "Апгрейд компьютера", "description": "Увеличение памяти, замена комплектующих", "price_text": "от 500 руб.", "price_from": 500, "icon": "ph-bold ph-cpu", "payment": "prepay",
     "form_fields": [
         {"id": "contact", "label": "Контакт для связи", "type": "text", "placeholder": "Телефон или @telegram", "required": True},
         {"id": "device", "label": "Текущая конфигурация", "type": "textarea", "placeholder": "Что стоит сейчас", "required": True},
         {"id": "upgrade_wish", "label": "Что улучшить", "type": "textarea", "placeholder": "RAM, SSD, видеокарту...", "required": True},
     ]},
    {"id": 9, "title": "Апгрейд ноутбука", "description": "RAM, SSD, модернизация", "price_text": "от 500 руб.", "price_from": 500, "icon": "ph-bold ph-arrow-circle-up", "payment": "prepay",
     "form_fields": [
         {"id": "contact", "label": "Контакт для связи", "type": "text", "placeholder": "Телефон или @telegram", "required": True},
         {"id": "device", "label": "Модель ноутбука", "type": "text", "placeholder": "Lenovo IdeaPad 5", "required": True},
         {"id": "upgrade_wish", "label": "Что улучшить", "type": "textarea", "placeholder": "RAM, SSD...", "required": True},
     ]},
    {"id": 10, "title": "Ремонт клавиатур и мышей", "description": "Диагностика и ремонт периферии", "price_text": "от 500 руб.", "price_from": 500, "icon": "ph-bold ph-keyboard", "payment": "postpay",
     "form_fields": [
         {"id": "contact", "label": "Контакт для связи", "type": "text", "placeholder": "Телефон или @telegram", "required": True},
         {"id": "device", "label": "Устройство", "type": "text", "placeholder": "Модель", "required": True},
         {"id": "issue", "label": "Проблема", "type": "textarea", "placeholder": "Что сломалось", "required": True},
     ]},
    {"id": 11, "title": "Ремонт после залития", "description": "Восстановление после попадания жидкости", "price_text": "от 2 000 руб.", "price_from": 2000, "icon": "ph-bold ph-drop", "payment": "postpay",
     "form_fields": [
         {"id": "contact", "label": "Контакт для связи", "type": "text", "placeholder": "Телефон или @telegram", "required": True},
         {"id": "device", "label": "Устройство", "type": "text", "placeholder": "Модель", "required": True},
         {"id": "liquid", "label": "Что попало", "type": "text", "placeholder": "Вода, чай...", "required": True},
         {"id": "issue", "label": "Состояние", "type": "textarea", "placeholder": "Включается ли", "required": True},
     ]},
    {"id": 12, "title": "Сложный компонентный ремонт", "description": "Пайка BGA, замена чипов, ремонт цепей питания", "price_text": "от 3 000 руб.", "price_from": 3000, "icon": "ph-bold ph-wrench", "payment": "postpay",
     "form_fields": [
         {"id": "contact", "label": "Контакт для связи", "type": "text", "placeholder": "Телефон или @telegram", "required": True},
         {"id": "device", "label": "Устройство", "type": "text", "placeholder": "Модель", "required": True},
         {"id": "issue", "label": "Проблема", "type": "textarea", "placeholder": "Подробно", "required": True},
     ]},
    {"id": 13, "title": "Лазерная гравировка", "description": "Нанесение изображений лазером", "price_text": "от 500 руб.", "price_from": 500, "icon": "ph-bold ph-pencil-line", "payment": "prepay",
     "form_fields": [
         {"id": "contact", "label": "Контакт для связи", "type": "text", "placeholder": "Телефон или @telegram", "required": True},
         {"id": "device", "label": "На чем гравировка", "type": "text", "placeholder": "Корпус, крышка...", "required": True},
         {"id": "design", "label": "Рисунок/надпись", "type": "textarea", "placeholder": "Что нанести", "required": True},
     ]},
    {"id": 14, "title": "Винилография", "description": "Оклейка виниловой пленкой с дизайном", "price_text": "от 2 000 руб.", "price_from": 2000, "icon": "ph-bold ph-paint-brush", "payment": "prepay",
     "form_fields": [
         {"id": "contact", "label": "Контакт для связи", "type": "text", "placeholder": "Телефон или @telegram", "required": True},
         {"id": "device", "label": "Что оклеиваем", "type": "text", "placeholder": "Корпус, ноутбук...", "required": True},
         {"id": "design", "label": "Дизайн", "type": "textarea", "placeholder": "Опишите", "required": True},
     ]},
]

DEFAULT_BUILDS = [
    {"id": 1, "name": "Офисный ПК", "tier": "Офис", "description": "Надежный компьютер для офиса", "price": 10000, "price_text": "от 10 000 руб.", "payment": "prepay"},
    {"id": 2, "name": "Игровой ПК", "tier": "Игры", "description": "Производительная сборка для игр", "price": 40000, "price_text": "от 40 000 руб.", "payment": "prepay"},
    {"id": 3, "name": "Рабочая станция", "tier": "Профи", "description": "Мощная система для графики и 3D", "price": 200000, "price_text": "от 200 000 руб.", "payment": "prepay"},
    {"id": 4, "name": "Сервер", "tier": "Сервер", "description": "Серверные решения для бизнеса", "price": 50000, "price_text": "от 50 000 руб.", "payment": "prepay"},
    {"id": 5, "name": "Индивидуальный проект", "tier": "Кастом", "description": "Фулл кастом, моддинг, подсветка", "price": 250000, "price_text": "от 250 000 руб.", "payment": "prepay"},
]


def load_json(path, default):
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            pass
    save_json(path, default)
    return default


def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def get_services():
    return load_json(SERVICES_FILE, DEFAULT_SERVICES)


def save_services(data):
    save_json(SERVICES_FILE, data)


def get_builds():
    return load_json(BUILDS_FILE, DEFAULT_BUILDS)


def save_builds(data):
    save_json(BUILDS_FILE, data)


def next_id(items):
    if not items:
        return 1
    return max(i.get("id", 0) for i in items) + 1


IMAGE_KEYS = {
    "welcome": "Приветственное сообщение",
    "order_created": "Заявка создана",
    "order_status": "Статус обновлен",
    "support_received": "Сообщение в поддержку",
}


# ==================== FSM ====================

class PortfolioAdd(StatesGroup):
    waiting_photo = State()
    waiting_title = State()
    waiting_description = State()
    waiting_category = State()


class PortfolioDelete(StatesGroup):
    waiting_id = State()


class OrderStatusChange(StatesGroup):
    waiting_order_id = State()


class BroadcastStates(StatesGroup):
    waiting_message = State()
    waiting_confirmation = State()


class SetImageStates(StatesGroup):
    waiting_image_file = State()


class ManagerQuestion(StatesGroup):
    waiting_message = State()


# ==================== Helpers ====================

async def send_bot_message(chat_id, text, image_key, reply_markup=None, reply_to_message_id=None):
    image_path = None
    for ext in ["png", "jpg", "jpeg", "webp"]:
        p = os.path.join(BOT_IMAGES_PATH, f"{image_key}.{ext}")
        if os.path.exists(p):
            image_path = p
            break
    if image_path:
        return await bot.send_photo(
            chat_id=chat_id, photo=FSInputFile(image_path), caption=text,
            reply_markup=reply_markup, reply_to_message_id=reply_to_message_id,
        )
    else:
        return await bot.send_message(
            chat_id=chat_id, text=text,
            reply_markup=reply_markup, reply_to_message_id=reply_to_message_id,
        )


# ==================== Database (Supabase) ====================

async def get_user(user_id):
    try:
        r = supabase.table("users").select("*").eq("user_id", user_id).execute()
        return r.data[0] if r.data else None
    except Exception as e:
        logger.error(f"get_user error: {e}")
        return None


async def create_user(user_id, username, full_name, topic_id):
    try:
        existing = await get_user(user_id)
        if existing:
            supabase.table("users").update({
                "username": username,
                "full_name": full_name,
                "topic_id": topic_id,
                "last_active": datetime.utcnow().isoformat(),
            }).eq("user_id", user_id).execute()
        else:
            supabase.table("users").insert({
                "user_id": user_id,
                "username": username,
                "full_name": full_name,
                "topic_id": topic_id,
                "is_blocked": 0,
                "message_count": 0,
                "created_at": datetime.utcnow().isoformat(),
                "last_active": datetime.utcnow().isoformat(),
            }).execute()
    except Exception as e:
        logger.error(f"create_user error: {e}")


async def update_user_activity(user_id):
    try:
        user = await get_user(user_id)
        cnt = (user.get("message_count") or 0) + 1 if user else 1
        supabase.table("users").update({
            "message_count": cnt,
            "last_active": datetime.utcnow().isoformat(),
        }).eq("user_id", user_id).execute()
    except Exception as e:
        logger.error(f"update_user_activity error: {e}")


async def get_user_by_topic(topic_id):
    try:
        r = supabase.table("users").select("*").eq("topic_id", topic_id).execute()
        return r.data[0] if r.data else None
    except Exception as e:
        logger.error(f"get_user_by_topic error: {e}")
        return None


async def get_all_users():
    try:
        r = supabase.table("users").select("*").eq("is_blocked", 0).order("last_active", desc=True).execute()
        return r.data or []
    except Exception as e:
        logger.error(f"get_all_users error: {e}")
        return []


async def get_users_count():
    try:
        r = supabase.table("users").select("user_id", count="exact").execute()
        return r.count or 0
    except Exception as e:
        logger.error(f"get_users_count error: {e}")
        return 0


async def add_portfolio_item(filename, title, description, category, added_by):
    try:
        r = supabase.table("portfolio").insert({
            "filename": filename,
            "title": title,
            "description": description,
            "category": category,
            "added_by": added_by,
            "created_at": datetime.utcnow().isoformat(),
        }).execute()
        return r.data[0]["id"] if r.data else None
    except Exception as e:
        logger.error(f"add_portfolio_item error: {e}")
        return None


async def get_portfolio_items():
    try:
        r = supabase.table("portfolio").select("*").order("created_at", desc=True).execute()
        return r.data or []
    except Exception as e:
        logger.error(f"get_portfolio_items error: {e}")
        return []


async def get_portfolio_item(item_id):
    try:
        r = supabase.table("portfolio").select("*").eq("id", item_id).execute()
        return r.data[0] if r.data else None
    except Exception as e:
        logger.error(f"get_portfolio_item error: {e}")
        return None


async def delete_portfolio_item(item_id):
    try:
        item = await get_portfolio_item(item_id)
        if item:
            fp = os.path.join(ASSETS_PATH, item["filename"])
            if os.path.exists(fp):
                os.remove(fp)
            supabase.table("portfolio").delete().eq("id", item_id).execute()
            return True
        return False
    except Exception as e:
        logger.error(f"delete_portfolio_item error: {e}")
        return False


async def create_order(user_id, order_type, payment_type, details, total_price, contact_info="", delivery_info=""):
    try:
        r = supabase.table("orders").insert({
            "user_id": user_id,
            "order_type": order_type,
            "payment_type": payment_type,
            "details": details,
            "total_price": total_price,
            "contact_info": contact_info,
            "delivery_info": delivery_info,
            "status": "processing",
            "admin_note": "",
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
        }).execute()
        return r.data[0]["id"] if r.data else None
    except Exception as e:
        logger.error(f"create_order error: {e}")
        return None


async def get_orders_by_user(user_id):
    try:
        r = supabase.table("orders").select("*").eq("user_id", user_id).order("created_at", desc=True).execute()
        return r.data or []
    except Exception as e:
        logger.error(f"get_orders_by_user error: {e}")
        return []


async def get_all_orders(status_filter=None):
    try:
        q = supabase.table("orders").select("*").order("created_at", desc=True)
        if status_filter:
            q = q.eq("status", status_filter)
        r = q.execute()
        return r.data or []
    except Exception as e:
        logger.error(f"get_all_orders error: {e}")
        return []


async def get_order_by_id(order_id):
    try:
        r = supabase.table("orders").select("*").eq("id", order_id).execute()
        return r.data[0] if r.data else None
    except Exception as e:
        logger.error(f"get_order_by_id error: {e}")
        return None


async def update_order_status(order_id, status):
    try:
        supabase.table("orders").update({
            "status": status,
            "updated_at": datetime.utcnow().isoformat(),
        }).eq("id", order_id).execute()
    except Exception as e:
        logger.error(f"update_order_status error: {e}")


async def log_message(user_id, direction, content_type, message_text):
    try:
        supabase.table("message_log").insert({
            "user_id": user_id,
            "direction": direction,
            "content_type": content_type,
            "message_text": (message_text or "")[:500],
            "created_at": datetime.utcnow().isoformat(),
        }).execute()
    except Exception as e:
        logger.error(f"log_message error: {e}")


async def get_stats():
    try:
        results = {}
        users_r = supabase.table("users").select("user_id", count="exact").execute()
        results["total_users"] = users_r.count or 0
        orders_r = supabase.table("orders").select("id", count="exact").execute()
        results["total_orders"] = orders_r.count or 0
        for status in ["processing", "diagnostics", "in_progress", "ready", "delayed", "waiting_parts", "delivery", "completed", "cancelled"]:
            r = supabase.table("orders").select("id", count="exact").eq("status", status).execute()
            results[status] = r.count or 0
        results["delivery_count"] = results.pop("delivery", 0)
        portfolio_r = supabase.table("portfolio").select("id", count="exact").execute()
        results["portfolio_count"] = portfolio_r.count or 0
        messages_r = supabase.table("message_log").select("id", count="exact").execute()
        results["total_messages"] = messages_r.count or 0
        from datetime import timedelta
        day_ago = (datetime.utcnow() - timedelta(days=1)).isoformat()
        active_r = supabase.table("users").select("user_id", count="exact").gte("last_active", day_ago).execute()
        results["active_today"] = active_r.count or 0
        return results
    except Exception as e:
        logger.error(f"get_stats error: {e}")
        return {}


async def ensure_topic(user_id, username, full_name):
    user = await get_user(user_id)
    if user and user.get("topic_id"):
        return user["topic_id"]
    topic_name = f"{full_name} [{user_id}]"
    try:
        topic = await bot.create_forum_topic(chat_id=ADMIN_GROUP_ID, name=topic_name[:128])
        topic_id = topic.message_thread_id
    except Exception as e:
        logger.error(f"Topic create fail {user_id}: {e}")
        raise
    await create_user(user_id, username, full_name, topic_id)
    await bot.send_message(
        chat_id=ADMIN_GROUP_ID,
        message_thread_id=topic_id,
        text=f"Новый тикет\n{full_name}\n@{username}\nID: {user_id}\n{datetime.now().strftime('%d.%m.%Y %H:%M')}",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="Профиль", url=f"tg://user?id={user_id}")]]
        ),
    )
    return topic_id


async def setup_menu_button():
    try:
        await bot.set_chat_menu_button(
            menu_button=MenuButtonWebApp(text="Pulse Computers", web_app=WebAppInfo(url=WEBAPP_URL))
        )
        logger.info(f"Menu button: {WEBAPP_URL}")
    except Exception as e:
        logger.error(f"Menu button fail: {e}")


# ==================== Keyboards ====================

def get_start_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=" Открыть Pulse Computers", web_app=WebAppInfo(url=WEBAPP_URL))],
        [InlineKeyboardButton(text=" Написать менеджеру", url=MANAGER_DEEPLINK)],
    ])


def get_admin_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Статистика", callback_data="admin_stats"),
         InlineKeyboardButton(text="Заказы", callback_data="admin_orders")],
        [InlineKeyboardButton(text="Портфолио +", callback_data="admin_portfolio_add"),
         InlineKeyboardButton(text="Портфолио -", callback_data="admin_portfolio_del")],
        [InlineKeyboardButton(text="Рассылка", callback_data="admin_broadcast")],
        [InlineKeyboardButton(text="Картинки бота", callback_data="admin_set_image")],
    ])


def get_back_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="Назад", callback_data="admin_panel")]]
    )


def get_cancel_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="Отмена", callback_data="cancel_action")]]
    )


def get_status_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="В обработке", callback_data="set_status_processing"),
         InlineKeyboardButton(text="Доставка", callback_data="set_status_delivery")],
        [InlineKeyboardButton(text="Диагностика", callback_data="set_status_diagnostics"),
         InlineKeyboardButton(text="В работе", callback_data="set_status_in_progress")],
        [InlineKeyboardButton(text="Готов", callback_data="set_status_ready"),
         InlineKeyboardButton(text="Завершен", callback_data="set_status_completed")],
        [InlineKeyboardButton(text="Задержка", callback_data="set_status_delayed"),
         InlineKeyboardButton(text="Ожидание", callback_data="set_status_waiting_parts")],
        [InlineKeyboardButton(text="Отменен", callback_data="set_status_cancelled")],
        [InlineKeyboardButton(text="Отмена", callback_data="cancel_action")],
    ])


def get_orders_filter_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Все", callback_data="orders_filter_all"),
         InlineKeyboardButton(text="В обработке", callback_data="orders_filter_processing")],
        [InlineKeyboardButton(text="В работе", callback_data="orders_filter_in_progress"),
         InlineKeyboardButton(text="Готов", callback_data="orders_filter_ready")],
        [InlineKeyboardButton(text="Завершенные", callback_data="orders_filter_completed")],
        [InlineKeyboardButton(text="Назад", callback_data="admin_panel")],
    ])


def get_image_keys_keyboard():
    kb = []
    for key, label in IMAGE_KEYS.items():
        has = any(os.path.exists(os.path.join(BOT_IMAGES_PATH, f"{key}.{e}")) for e in ["png", "jpg", "jpeg", "webp"])
        mark = "V" if has else "X"
        kb.append([InlineKeyboardButton(text=f"[{mark}] {label}", callback_data=f"setimg_{key}")])
    kb.append([InlineKeyboardButton(text="Назад", callback_data="admin_panel")])
    return InlineKeyboardMarkup(inline_keyboard=kb)


# ==================== Bot Handlers ====================

@router.message(CommandStart(), F.chat.type == "private")
async def cmd_start(message: Message, state: FSMContext, command: CommandObject = None):
    await state.clear()
    await ensure_topic(message.from_user.id, message.from_user.username or "no_username", message.from_user.full_name)
    args = command.args if command else None
    if args == "manager":
        await state.set_state(ManagerQuestion.waiting_message)
        await message.answer(
            "Напишите ваше сообщение менеджеру.\nМы ответим в ближайшее время.",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text="Отмена", callback_data="cancel_manager")]]
            ),
        )
        return
    welcome_text = (
        "Добро пожаловать в Pulse Computers!\n\n"
        "Сборка, ремонт и обслуживание компьютерной техники.\n"
        "Скупка б/у устройств.\n"
        "Индивидуальные проекты и кастомизация.\n\n"
        "Нажмите кнопку ниже или используйте меню."
    )
    await send_bot_message(
        chat_id=message.chat.id,
        text=welcome_text,
        image_key="welcome",
        reply_markup=get_start_keyboard(),
    )
    await log_message(message.from_user.id, "incoming", "command", "/start")


@router.callback_query(F.data == "cancel_manager")
async def cb_cancel_manager(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("Отменено.")
    await callback.answer()


@router.message(ManagerQuestion.waiting_message, F.chat.type == "private")
async def manager_question(message: Message, state: FSMContext):
    await state.clear()
    uid = message.from_user.id
    topic_id = await ensure_topic(uid, message.from_user.username or "no_username", message.from_user.full_name)
    await update_user_activity(uid)
    tag = "#вопрос_менеджеру"
    try:
        ct = message.content_type
        if ct == ContentType.TEXT:
            await bot.send_message(chat_id=ADMIN_GROUP_ID, message_thread_id=topic_id, text=f"{tag}\n\n{message.text}")
        elif ct == ContentType.PHOTO:
            await bot.send_photo(chat_id=ADMIN_GROUP_ID, message_thread_id=topic_id, photo=message.photo[-1].file_id, caption=f"{tag}\n\n{message.caption or ''}")
        elif ct == ContentType.VOICE:
            await bot.send_voice(chat_id=ADMIN_GROUP_ID, message_thread_id=topic_id, voice=message.voice.file_id)
            await bot.send_message(chat_id=ADMIN_GROUP_ID, message_thread_id=topic_id, text=tag)
        else:
            await bot.send_message(chat_id=ADMIN_GROUP_ID, message_thread_id=topic_id, text=f"{tag}\n\n[{ct}]")
    except Exception as e:
        logger.error(f"Manager q error: {e}")
    await send_bot_message(
        chat_id=message.chat.id,
        text="Сообщение передано менеджеру!",
        image_key="support_received",
        reply_to_message_id=message.message_id,
    )


@router.message(Command("admin"), F.chat.type == "private")
async def cmd_admin_private(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Админ-панель:", reply_markup=get_admin_keyboard())


@router.message(Command("admin"), F.chat.id == ADMIN_GROUP_ID)
async def cmd_admin_group(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Админ-панель:", reply_markup=get_admin_keyboard())


@router.callback_query(F.data == "admin_panel")
async def cb_admin_panel(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    try:
        await callback.message.edit_text("Админ-панель:", reply_markup=get_admin_keyboard())
    except:
        pass
    await callback.answer()


@router.callback_query(F.data == "cancel_action")
async def cb_cancel(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    try:
        await callback.message.edit_text("Отменено.", reply_markup=get_admin_keyboard())
    except:
        pass
    await callback.answer()


@router.callback_query(F.data == "admin_stats")
async def cb_stats(callback: CallbackQuery):
    s = await get_stats()
    t = (
        f"Статистика\n\n"
        f"Пользователи: {s.get('total_users', 0)}\nАктивны 24ч: {s.get('active_today', 0)}\n\n"
        f"Заказы: {s.get('total_orders', 0)}\nВ обработке: {s.get('processing', 0)}\n"
        f"В работе: {s.get('in_progress', 0)}\nГотовы: {s.get('ready', 0)}\n"
        f"Завершены: {s.get('completed', 0)}\n\n"
        f"Портфолио: {s.get('portfolio_count', 0)}\nСообщений: {s.get('total_messages', 0)}"
    )
    try:
        await callback.message.edit_text(t, reply_markup=get_back_keyboard())
    except:
        pass
    await callback.answer()


@router.callback_query(F.data == "admin_orders")
async def cb_orders(callback: CallbackQuery):
    try:
        await callback.message.edit_text("Фильтр:", reply_markup=get_orders_filter_keyboard())
    except:
        pass
    await callback.answer()


@router.callback_query(F.data.startswith("orders_filter_"))
async def cb_orders_filter(callback: CallbackQuery):
    ft = callback.data.replace("orders_filter_", "")
    orders = await get_all_orders() if ft == "all" else await get_all_orders(ft)
    if not orders:
        try:
            await callback.message.edit_text("Заказов нет.", reply_markup=get_back_keyboard())
        except:
            pass
        await callback.answer()
        return
    tl = {"repair": "Ремонт", "build": "Сборка", "buyout": "Скупка", "service": "Услуга"}
    parts = [f"Заказы ({len(orders)})\n"]
    for o in orders[:20]:
        u = await get_user(o["user_id"])
        nm = u["full_name"] if u else str(o["user_id"])
        parts.append(
            f"\n#{o['id']} {tl.get(o['order_type'], o['order_type'])}\n"
            f"{nm} | {ORDER_STATUSES.get(o['status'], o['status'])}"
        )
    try:
        await callback.message.edit_text("\n".join(parts)[:4000], reply_markup=get_back_keyboard())
    except:
        pass
    await callback.answer()


@router.callback_query(F.data == "admin_portfolio_add")
async def cb_pa(callback: CallbackQuery, state: FSMContext):
    await state.set_state(PortfolioAdd.waiting_photo)
    try:
        await callback.message.edit_text("Отправьте фото:", reply_markup=get_cancel_keyboard())
    except:
        pass
    await callback.answer()


@router.message(PortfolioAdd.waiting_photo, F.photo)
async def pa_photo(message: Message, state: FSMContext):
    photo = message.photo[-1]
    f = await bot.get_file(photo.file_id)
    fn = f"portfolio_{uuid.uuid4().hex[:12]}.jpg"
    await bot.download_file(f.file_path, os.path.join(ASSETS_PATH, fn))
    await state.update_data(filename=fn)
    await state.set_state(PortfolioAdd.waiting_title)
    await message.answer("Название:")


@router.message(PortfolioAdd.waiting_photo)
async def pa_photo_inv(message: Message):
    await message.answer("Отправьте фото:")


@router.message(PortfolioAdd.waiting_title)
async def pa_title(message: Message, state: FSMContext):
    await state.update_data(title=message.text.strip())
    await state.set_state(PortfolioAdd.waiting_description)
    await message.answer("Описание (. чтобы пропустить):")


@router.message(PortfolioAdd.waiting_description)
async def pa_desc(message: Message, state: FSMContext):
    d = message.text.strip()
    await state.update_data(description="" if d == "." else d)
    await state.set_state(PortfolioAdd.waiting_category)
    await message.answer(
        "Категория:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Сборка", callback_data="pcat_build"),
             InlineKeyboardButton(text="Ремонт", callback_data="pcat_repair")],
            [InlineKeyboardButton(text="Апгрейд", callback_data="pcat_upgrade"),
             InlineKeyboardButton(text="Кастом", callback_data="pcat_custom")],
            [InlineKeyboardButton(text="Другое", callback_data="pcat_general")],
        ]),
    )


@router.callback_query(F.data.startswith("pcat_"), PortfolioAdd.waiting_category)
async def pa_cat(callback: CallbackQuery, state: FSMContext):
    cm = {"pcat_build": "build", "pcat_repair": "repair", "pcat_upgrade": "upgrade", "pcat_custom": "custom", "pcat_general": "general"}
    cat = cm.get(callback.data, "general")
    data = await state.get_data()
    iid = await add_portfolio_item(data["filename"], data["title"], data.get("description", ""), cat, callback.from_user.id)
    await state.clear()
    try:
        await callback.message.edit_text(f"Добавлено ID:{iid}", reply_markup=get_back_keyboard())
    except:
        pass
    await callback.answer()


@router.callback_query(F.data == "admin_portfolio_del")
async def cb_pd(callback: CallbackQuery, state: FSMContext):
    items = await get_portfolio_items()
    if not items:
        try:
            await callback.message.edit_text("Пусто.", reply_markup=get_back_keyboard())
        except:
            pass
        await callback.answer()
        return
    await state.set_state(PortfolioDelete.waiting_id)
    lines = ["Введите ID:\n"] + [f"ID:{i['id']} - {i['title']}" for i in items]
    try:
        await callback.message.edit_text("\n".join(lines)[:4000], reply_markup=get_cancel_keyboard())
    except:
        pass
    await callback.answer()


@router.message(PortfolioDelete.waiting_id)
async def pd_process(message: Message, state: FSMContext):
    if not message.text or not message.text.strip().isdigit():
        return
    iid = int(message.text.strip())
    await delete_portfolio_item(iid)
    await state.clear()
    await message.answer(f"Удалено ID:{iid}", reply_markup=get_back_keyboard())


@router.callback_query(F.data == "admin_broadcast")
async def cb_bc(callback: CallbackQuery, state: FSMContext):
    await state.set_state(BroadcastStates.waiting_message)
    try:
        await callback.message.edit_text("Текст рассылки:", reply_markup=get_cancel_keyboard())
    except:
        pass
    await callback.answer()


@router.message(BroadcastStates.waiting_message)
async def bc_text(message: Message, state: FSMContext):
    cnt = await get_users_count()
    await state.update_data(broadcast_text=message.text)
    await state.set_state(BroadcastStates.waiting_confirmation)
    await message.answer(
        f"Текст:\n{message.text}\n\nПолучателей: {cnt}\nОтправить?",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Да", callback_data="broadcast_confirm"),
             InlineKeyboardButton(text="Нет", callback_data="cancel_action")]
        ]),
    )


@router.callback_query(F.data == "broadcast_confirm", BroadcastStates.waiting_confirmation)
async def bc_confirm(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    txt = data.get("broadcast_text", "")
    await state.clear()
    users = await get_all_users()
    sent = 0
    fail = 0
    for u in users:
        try:
            await bot.send_message(chat_id=u["user_id"], text=txt)
            sent += 1
        except:
            fail += 1
        await asyncio.sleep(0.05)
    try:
        await callback.message.edit_text(f"Отправлено: {sent} | Ошибок: {fail}", reply_markup=get_back_keyboard())
    except:
        pass
    await callback.answer()


@router.callback_query(F.data == "admin_set_image")
async def cb_si(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    try:
        await callback.message.edit_text("Картинки бота:", reply_markup=get_image_keys_keyboard())
    except:
        pass
    await callback.answer()


@router.callback_query(F.data.startswith("setimg_"))
async def cb_sik(callback: CallbackQuery, state: FSMContext):
    key = callback.data.replace("setimg_", "")
    if key not in IMAGE_KEYS:
        await callback.answer()
        return
    await state.set_state(SetImageStates.waiting_image_file)
    await state.update_data(image_key=key)
    try:
        await callback.message.edit_text(
            f"{IMAGE_KEYS[key]}\nОтправьте фото:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="Удалить", callback_data=f"delimg_{key}")],
                [InlineKeyboardButton(text="Назад", callback_data="admin_set_image")],
            ]),
        )
    except:
        pass
    await callback.answer()


@router.callback_query(F.data.startswith("delimg_"))
async def cb_di(callback: CallbackQuery, state: FSMContext):
    key = callback.data.replace("delimg_", "")
    for e in ["png", "jpg", "jpeg", "webp"]:
        p = os.path.join(BOT_IMAGES_PATH, f"{key}.{e}")
        if os.path.exists(p):
            os.remove(p)
    await state.clear()
    try:
        await callback.message.edit_text("Удалено.", reply_markup=get_image_keys_keyboard())
    except:
        pass
    await callback.answer()


@router.message(SetImageStates.waiting_image_file, F.photo)
async def si_photo(message: Message, state: FSMContext):
    data = await state.get_data()
    key = data.get("image_key")
    if not key:
        await state.clear()
        return
    for e in ["png", "jpg", "jpeg", "webp"]:
        p = os.path.join(BOT_IMAGES_PATH, f"{key}.{e}")
        if os.path.exists(p):
            os.remove(p)
    photo = message.photo[-1]
    f = await bot.get_file(photo.file_id)
    await bot.download_file(f.file_path, os.path.join(BOT_IMAGES_PATH, f"{key}.jpg"))
    await state.clear()
    await message.answer(f"Установлено: {IMAGE_KEYS.get(key, key)}", reply_markup=get_image_keys_keyboard())


@router.message(Command("addwork"), F.chat.id == ADMIN_GROUP_ID)
async def cmd_addwork(message: Message, state: FSMContext):
    await state.set_state(PortfolioAdd.waiting_photo)
    await message.answer("Отправьте фото:", reply_markup=get_cancel_keyboard())


@router.message(F.chat.type == "private")
async def forward_user(message: Message, state: FSMContext):
    cs = await state.get_state()
    if cs is not None:
        return
    if message.text and message.text.startswith("/"):
        return
    if message.web_app_data:
        return
    topic_id = await ensure_topic(
        message.from_user.id,
        message.from_user.username or "no_username",
        message.from_user.full_name,
    )
    await update_user_activity(message.from_user.id)
    try:
        ct = message.content_type
        if ct == ContentType.TEXT:
            await bot.send_message(chat_id=ADMIN_GROUP_ID, message_thread_id=topic_id, text=message.text)
        elif ct == ContentType.PHOTO:
            await bot.send_photo(chat_id=ADMIN_GROUP_ID, message_thread_id=topic_id, photo=message.photo[-1].file_id, caption=message.caption or "")
        elif ct == ContentType.DOCUMENT:
            await bot.send_document(chat_id=ADMIN_GROUP_ID, message_thread_id=topic_id, document=message.document.file_id, caption=message.caption or "")
        elif ct == ContentType.VIDEO:
            await bot.send_video(chat_id=ADMIN_GROUP_ID, message_thread_id=topic_id, video=message.video.file_id, caption=message.caption or "")
        elif ct == ContentType.VOICE:
            await bot.send_voice(chat_id=ADMIN_GROUP_ID, message_thread_id=topic_id, voice=message.voice.file_id)
        elif ct == ContentType.VIDEO_NOTE:
            await bot.send_video_note(chat_id=ADMIN_GROUP_ID, message_thread_id=topic_id, video_note=message.video_note.file_id)
        elif ct == ContentType.STICKER:
            await bot.send_sticker(chat_id=ADMIN_GROUP_ID, message_thread_id=topic_id, sticker=message.sticker.file_id)
        elif ct == ContentType.ANIMATION:
            await bot.send_animation(chat_id=ADMIN_GROUP_ID, message_thread_id=topic_id, animation=message.animation.file_id, caption=message.caption or "")
        elif ct == ContentType.AUDIO:
            await bot.send_audio(chat_id=ADMIN_GROUP_ID, message_thread_id=topic_id, audio=message.audio.file_id, caption=message.caption or "")
        else:
            await bot.send_message(chat_id=ADMIN_GROUP_ID, message_thread_id=topic_id, text=f"[{ct}]")
        await log_message(message.from_user.id, "incoming", str(ct), message.text or message.caption or "")
        await send_bot_message(
            chat_id=message.chat.id,
            text="Сообщение передано в поддержку.",
            image_key="support_received",
            reply_to_message_id=message.message_id,
        )
    except Exception as e:
        logger.error(f"Forward error: {e}")
        await message.reply("Ошибка.")


@router.message(F.chat.id == ADMIN_GROUP_ID, F.message_thread_id)
async def forward_admin(message: Message):
    if message.from_user.is_bot:
        return
    if message.text and message.text.startswith("/"):
        return
    user = await get_user_by_topic(message.message_thread_id)
    if not user:
        return
    uid = user["user_id"]
    try:
        ct = message.content_type
        if ct == ContentType.TEXT:
            await bot.send_message(chat_id=uid, text=message.text)
        elif ct == ContentType.PHOTO:
            await bot.send_photo(chat_id=uid, photo=message.photo[-1].file_id, caption=message.caption or "")
        elif ct == ContentType.DOCUMENT:
            await bot.send_document(chat_id=uid, document=message.document.file_id, caption=message.caption or "")
        elif ct == ContentType.VIDEO:
            await bot.send_video(chat_id=uid, video=message.video.file_id, caption=message.caption or "")
        elif ct == ContentType.VOICE:
            await bot.send_voice(chat_id=uid, voice=message.voice.file_id)
        elif ct == ContentType.STICKER:
            await bot.send_sticker(chat_id=uid, sticker=message.sticker.file_id)
        elif ct == ContentType.ANIMATION:
            await bot.send_animation(chat_id=uid, animation=message.animation.file_id, caption=message.caption or "")
    except Exception as e:
        logger.error(f"Forward to {uid}: {e}")
        await message.reply("Не удалось отправить.")


# ==================== FastAPI ====================

@asynccontextmanager
async def lifespan(app: FastAPI):
    await setup_menu_button()
    get_services()
    get_builds()
    polling_task = asyncio.create_task(dp.start_polling(bot))
    logger.info("Bot started")
    yield
    polling_task.cancel()
    try:
        await polling_task
    except asyncio.CancelledError:
        pass
    await bot.session.close()


app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

if os.path.exists(ASSETS_PATH):
    app.mount("/assets", StaticFiles(directory=ASSETS_PATH), name="assets")

css_p = os.path.join(FRONTEND_PATH, "css")
if os.path.exists(css_p):
    app.mount("/css", StaticFiles(directory=css_p), name="css")

js_p = os.path.join(FRONTEND_PATH, "js")
if os.path.exists(js_p):
    app.mount("/js", StaticFiles(directory=js_p), name="js")


@app.get("/app")
async def serve_miniapp():
    ip = os.path.join(FRONTEND_PATH, "index.html")
    if os.path.exists(ip):
        return FileResponse(ip, media_type="text/html")
    return HTMLResponse("<h1>App not found</h1>")


@app.get("/")
async def serve_root():
    return HTMLResponse(
        "<html><head><meta charset='utf-8'><title>Pulse Computers</title></head>"
        "<body style='background:#050507;color:#fff;font-family:sans-serif;"
        "display:flex;align-items:center;justify-content:center;height:100vh;'>"
        "<div style='text-align:center;'>"
        "<h1>Pulse Computers</h1>"
        "<p><a href='/app' style='color:#6c5ce7;'>Open App</a></p>"
        "</div></body></html>"
    )


@app.get("/api/health")
async def health():
    return JSONResponse({"status": "ok"})


@app.get("/api/config")
async def api_config():
    return JSONResponse({
        "bot_username": BOT_USERNAME,
        "manager_deeplink": MANAGER_DEEPLINK,
        "admin_personal_link": ADMIN_PERSONAL_LINK,
        "taplink_url": TAPLINK_URL,
        "admin_ids": ADMIN_IDS,
        "webapp_url": WEBAPP_URL,
    })


@app.get("/api/services")
async def api_services():
    return JSONResponse(get_services())


@app.get("/api/builds")
async def api_builds():
    return JSONResponse(get_builds())


@app.get("/api/portfolio")
async def api_portfolio():
    items = await get_portfolio_items()
    for i in items:
        i["url"] = f"/assets/{i['filename']}"
    return JSONResponse(items)


@app.get("/api/orders/{user_id}")
async def api_user_orders(user_id: int):
    orders = await get_orders_by_user(user_id)
    for o in orders:
        o["status_label"] = ORDER_STATUSES.get(o["status"], o["status"])
    return JSONResponse(orders)


@app.get("/api/statuses")
async def api_statuses():
    return JSONResponse(ORDER_STATUSES)


@app.post("/api/orders")
async def api_create_order(request: Request):
    data = await request.json()
    uid = data.get("user_id", 0)
    oid = await create_order(
        uid,
        data.get("order_type", ""),
        data.get("payment_type", ""),
        data.get("details", ""),
        data.get("total_price", 0),
        data.get("contact_info", ""),
        data.get("delivery_info", ""),
    )
    user = await get_user(uid)
    tl = {"repair": "Ремонт", "build": "Сборка", "buyout": "Скупка", "service": "Услуга"}
    if user and user.get("topic_id"):
        try:
            await bot.send_message(
                chat_id=ADMIN_GROUP_ID,
                message_thread_id=user["topic_id"],
                text=f"Заявка #{oid}\nТип: {tl.get(data.get('order_type',''),data.get('order_type',''))}\nКонтакт: {data.get('contact_info','')}\nСумма: {data.get('total_price',0)} руб.\nДетали: {data.get('details','')[:500]}",
            )
        except Exception as e:
            logger.error(f"Admin notify: {e}")
    if uid:
        try:
            await send_bot_message(
                chat_id=uid,
                text=f"Заявка #{oid} создана\nТип: {tl.get(data.get('order_type',''),data.get('order_type',''))}\nСумма: {data.get('total_price',0)} руб.\n\nМы свяжемся с вами.",
                image_key="order_created",
            )
        except Exception as e:
            logger.error(f"User notify: {e}")
    return JSONResponse({"order_id": oid, "status": "created"})


@app.get("/api/admin/stats")
async def api_admin_stats():
    s = await get_stats()
    s["services_count"] = len(get_services())
    s["builds_count"] = len(get_builds())
    return JSONResponse(s)


@app.get("/api/admin/orders")
async def api_admin_orders():
    orders = await get_all_orders()
    for o in orders:
        o["status_label"] = ORDER_STATUSES.get(o["status"], o["status"])
        u = await get_user(o["user_id"])
        o["user_name"] = u["full_name"] if u else str(o["user_id"])
    return JSONResponse(orders)


@app.put("/api/admin/orders/{order_id}/status")
async def api_admin_order_status(order_id: int, request: Request):
    data = await request.json()
    status = data.get("status", "")
    if status not in ORDER_STATUSES:
        return JSONResponse({"error": "bad status"}, status_code=400)
    await update_order_status(order_id, status)
    order = await get_order_by_id(order_id)
    if order:
        tl = {"repair": "Ремонт", "build": "Сборка", "buyout": "Скупка", "service": "Услуга"}
        try:
            await send_bot_message(
                chat_id=order["user_id"],
                text=f"Статус заказа #{order_id} обновлен\nТип: {tl.get(order['order_type'],order['order_type'])}\nСтатус: {ORDER_STATUSES[status]}",
                image_key="order_status",
            )
        except Exception as e:
            logger.error(f"Status notify: {e}")
    return JSONResponse({"ok": True})


@app.get("/api/admin/users")
async def api_admin_users():
    return JSONResponse(await get_all_users())


@app.post("/api/admin/services")
async def api_svc_create(request: Request):
    data = await request.json()
    svcs = get_services()
    new = {
        "id": next_id(svcs),
        "title": data.get("title", ""),
        "description": data.get("description", ""),
        "price_text": data.get("price_text", ""),
        "price_from": data.get("price_from", 0),
        "icon": "ph-bold ph-wrench",
        "payment": data.get("payment", "postpay"),
        "form_fields": [
            {"id": "contact", "label": "Контакт для связи", "type": "text", "placeholder": "Телефон или @telegram", "required": True},
            {"id": "device", "label": "Устройство", "type": "text", "placeholder": "Модель", "required": True},
            {"id": "issue", "label": "Описание", "type": "textarea", "placeholder": "Подробно", "required": True},
        ],
    }
    svcs.append(new)
    save_services(svcs)
    return JSONResponse({"ok": True, "id": new["id"]})


@app.put("/api/admin/services/{svc_id}")
async def api_svc_update(svc_id: int, request: Request):
    data = await request.json()
    svcs = get_services()
    for s in svcs:
        if s["id"] == svc_id:
            for k in ["title", "description", "price_text", "price_from", "payment"]:
                if k in data:
                    s[k] = data[k]
            break
    save_services(svcs)
    return JSONResponse({"ok": True})


@app.delete("/api/admin/services/{svc_id}")
async def api_svc_delete(svc_id: int):
    svcs = [s for s in get_services() if s["id"] != svc_id]
    save_services(svcs)
    return JSONResponse({"ok": True})


@app.post("/api/admin/builds")
async def api_bld_create(request: Request):
    data = await request.json()
    blds = get_builds()
    new = {
        "id": next_id(blds),
        "name": data.get("name", ""),
        "tier": data.get("tier", ""),
        "description": data.get("description", ""),
        "price": data.get("price", 0),
        "price_text": data.get("price_text", ""),
        "payment": "prepay",
    }
    blds.append(new)
    save_builds(blds)
    return JSONResponse({"ok": True, "id": new["id"]})


@app.put("/api/admin/builds/{bld_id}")
async def api_bld_update(bld_id: int, request: Request):
    data = await request.json()
    blds = get_builds()
    for b in blds:
        if b["id"] == bld_id:
            for k in ["name", "tier", "description", "price", "price_text"]:
                if k in data:
                    b[k] = data[k]
            break
    save_builds(blds)
    return JSONResponse({"ok": True})


@app.delete("/api/admin/builds/{bld_id}")
async def api_bld_delete(bld_id: int):
    blds = [b for b in get_builds() if b["id"] != bld_id]
    save_builds(blds)
    return JSONResponse({"ok": True})


@app.delete("/api/admin/portfolio/{item_id}")
async def api_portfolio_delete(item_id: int):
    result = await delete_portfolio_item(item_id)
    return JSONResponse({"ok": result})

@app.get("/dev/get-files")
async def download_frontend():
    import zipfile
    zip_path = "/tmp/frontend.zip"
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for root, dirs, files in os.walk(FRONTEND_PATH):
            for file in files:
                file_path = os.path.join(root, file)
                arcname = os.path.relpath(file_path, FRONTEND_PATH)
                zipf.write(file_path, arcname)
    return FileResponse(
        zip_path,
        media_type="application/zip",
        filename="frontend.zip"
    )
@app.get("/dev/get-files-secret123")
async def download_frontend():
    import zipfile
    zip_path = "/tmp/frontend.zip"
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for root, dirs, files in os.walk(FRONTEND_PATH):
            for file in files:
                file_path = os.path.join(root, file)
                arcname = os.path.relpath(file_path, FRONTEND_PATH)
                zipf.write(file_path, arcname)
    return FileResponse(
        zip_path,
        media_type="application/zip",
        filename="frontend.zip"
    )

# ==================== Start ====================

if __name__ == "__main__":
    uvicorn.run("bot:app", host=HOST, port=PORT, reload=False)