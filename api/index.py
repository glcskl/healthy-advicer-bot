from fastapi import FastAPI, Request, Response
from aiogram.types import Update
import logging
import datetime

from bot import bot, dp
from database import init_db_pool, close_db_pool, init_db, get_pool
from config import WEBHOOK_URL

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(title="Telegram Bot Webhook")


@app.on_event("startup")
async def on_startup():
    await init_db_pool()
    await init_db()
    logger.info("Database initialized")

    if WEBHOOK_URL:
        await bot.set_webhook(url=WEBHOOK_URL)
        logger.info(f"Webhook set to {WEBHOOK_URL}")
        webhook_info = await bot.get_webhook_info()
        if webhook_info.url:
            logger.info(f"Webhook is active: {webhook_info.url}")
        else:
            logger.error("Failed to set webhook")
    else:
        logger.warning("WEBHOOK_URL not set, skipping webhook setup")


@app.on_event("shutdown")
async def on_shutdown():
    await bot.delete_webhook()
    await close_db_pool()
    logger.info("Webhook removed and database pool closed")


@app.post("/webhook")
async def webhook(request: Request):
    try:
        update_data = await request.json()
        update = Update(**update_data)
        await dp.feed_update(bot, update)
        return Response(status_code=200)
    except Exception as e:
        logger.error(f"Error processing update: {e}")
        return Response(status_code=500)


@app.get("/")
async def root():
    return {"status": "ok", "message": "Bot is running"}


@app.get("/health")
async def health_check():
    """Health check endpoint for monitoring and load balancers"""
    try:
        # Проверяем подключение к БД
        pool = await db.get_pool()
        if pool is None:
            return {"status": "error", "database": "disconnected", "message": "Database pool not initialized"}
        
        # Пробуем простой запрос
        async with pool.acquire() as conn:
            await conn.fetchval("SELECT 1")
        
        # Проверяем вебхук
        webhook_info = await bot.get_webhook_info()
        
        return {
            "status": "ok",
            "database": "connected",
            "webhook_url": webhook_info.url or "not set",
            "pending_updates": webhook_info.pending_update_count,
            "timestamp": datetime.datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return {"status": "error", "database": "disconnected", "error": str(e)}


@app.get("/set-webhook")
async def set_webhook_manual():
    if WEBHOOK_URL:
        await bot.set_webhook(url=WEBHOOK_URL)
        return {"status": "ok", "webhook_url": WEBHOOK_URL}
    return {"status": "error", "message": "WEBHOOK_URL not set"}


@app.get("/delete-webhook")
async def delete_webhook_manual():
    await bot.delete_webhook()
    return {"status": "ok", "message": "Webhook deleted"}


@app.get("/webhook-info")
async def webhook_info():
    info = await bot.get_webhook_info()
    return {
        "url": info.url,
        "has_custom_certificate": info.has_custom_certificate,
        "pending_update_count": info.pending_update_count,
        "last_error_date": info.last_error_date.isoformat() if info.last_error_date else None,
        "last_error_message": info.last_error_message,
    }
