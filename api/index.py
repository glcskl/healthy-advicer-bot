from fastapi import FastAPI, Request, Response, HTTPException
from aiogram.types import Update
import logging
import datetime
import asyncpg

from bot import bot, dp
from database import init_db_pool, close_db_pool, init_db, get_pool, _cache, _CACHE_TTL
from config import WEBHOOK_URL, ADMIN_IDS

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


@app.get("/performance")
async def performance_metrics(request: Request):
    """
    Endpoint для мониторинга производительности бота.
    Показывает: размер кэша, статистику запросов, состояние БД.
    Доступен только администраторам.
    """
    # Простая проверка админа через заголовок (в продакшене используйте более безопасный метод)
    admin_id = request.headers.get("X-Admin-ID")
    if admin_id and int(admin_id) in ADMIN_IDS:
        # Получаем статистику кэша
        cache_info = {
            "cache_size": len(_cache),
            "cache_ttl": _CACHE_TTL,
            "cached_categories": list(_cache.keys())
        }

        # Получаем статистику БД
        pool = await get_pool()
        async with pool.acquire() as conn:
            # Размеры таблиц
            sizes = await conn.fetch("""
                SELECT relname as table_name, pg_size_pretty(pg_total_relation_size(relid)) as size
                FROM pg_catalog.pg_statio_user_tables
                ORDER BY pg_total_relation_size(relid) DESC
            """)

            # Количество записей
            counts = await conn.fetch("""
                SELECT
                    (SELECT COUNT(*) FROM users) as users_count,
                    (SELECT COUNT(*) FROM content) as content_count,
                    (SELECT COUNT(*) FROM purchases) as purchases_count,
                    (SELECT COUNT(*) FROM payments) as payments_count,
                    (SELECT COUNT(*) FROM categories) as categories_count
            """)

            # Статус индексов (проверяем наличие ключевых индексов)
            indexes = await conn.fetch("""
                SELECT indexname, tablename
                FROM pg_indexes
                WHERE tablename IN ('purchases', 'payments', 'content', 'users')
                AND indexname LIKE 'idx_%'
                ORDER BY tablename, indexname
            """)

        return {
            "timestamp": datetime.datetime.now().isoformat(),
            "cache": cache_info,
            "database": {
                "sizes": [{"table": row['table_name'], "size": row['size']} for row in sizes],
                "counts": {
                    "users": counts[0]['users_count'],
                    "content": counts[0]['content_count'],
                    "purchases": counts[0]['purchases_count'],
                    "payments": counts[0]['payments_count'],
                    "categories": counts[0]['categories_count']
                },
                "indexes": [{"table": row['tablename'], "index": row['indexname']} for row in indexes]
            },
            "bot_info": {
                "webhook_url": (await bot.get_webhook_info()).url or "not set",
                "pending_updates": (await bot.get_webhook_info()).pending_update_count
            }
        }

    return {"error": "Unauthorized. Provide valid admin ID in X-Admin-ID header"}


@app.get("/slow-queries")
async def slow_queries(request: Request):
    """
    Показывает медленные запросы из pg_stat_statements (если включен).
    Только для администраторов.
    """
    admin_id = request.headers.get("X-Admin-ID")
    if not admin_id or int(admin_id) not in ADMIN_IDS:
        return {"error": "Unauthorized"}

    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            # Проверяем, включен ли pg_stat_statements
            enabled = await conn.fetchval("SELECT COUNT(*) FROM pg_extension WHERE extname = 'pg_stat_statements'")
            if not enabled:
                return {"error": "pg_stat_statements extension not enabled"}

            # Получаем топ-10 медленных запросов
            rows = await conn.fetch("""
                SELECT
                    query,
                    calls,
                    total_exec_time,
                    mean_exec_time,
                    rows,
                    100.0 * shared_blks_hit / nullif(shared_blks_hit + shared_blks_read, 0) AS hit_percent
                FROM pg_stat_statements
                WHERE query LIKE '%healthy_advicer_bot%'
                   OR query LIKE '%content%'
                   OR query LIKE '%purchases%'
                   OR query LIKE '%payments%'
                ORDER BY total_exec_time DESC
                LIMIT 10;
            """)

            return {
                "slow_queries": [
                    {
                        "query": row['query'][:200],
                        "calls": row['calls'],
                        "total_time_ms": round(row['total_exec_time'], 2),
                        "mean_time_ms": round(row['mean_exec_time'], 2),
                        "rows": row['rows'],
                        "cache_hit_percent": round(row['hit_percent'], 2) if row['hit_percent'] else None
                    }
                    for row in rows
                ]
            }
    except Exception as e:
        return {"error": str(e)}
