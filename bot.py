import logging
import asyncio
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.storage.redis import RedisStorage
from handlers import router
from database import init_db_pool, close_db_pool, init_db
from config import BOT_TOKEN
import os

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")

bot = Bot(token=BOT_TOKEN)

# Используем RedisStorage если доступен REDIS_URL, иначе MemoryStorage (временно)
redis_url = os.getenv("REDIS_URL")
if redis_url:
    from aiogram.fsm.storage.redis import RedisStorage
    storage = RedisStorage.from_url(redis_url)
else:
    storage = MemoryStorage()
    logging.warning("REDIS_URL not set, using MemoryStorage. State will be lost on restart!")

dp = Dispatcher(storage=storage)
dp.include_router(router)


if __name__ == "__main__":
    async def main():
        try:
            await init_db_pool()
            await init_db()
            logging.info("Starting bot in polling mode...")
            await dp.start_polling(bot, skip_updates=True)  # skip_updates для избежания накопления обновлений
        except Exception as e:
            logging.error(f"Bot crashed: {e}", exc_info=True)
            raise

    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logging.info("Bot stopped by user")
    except Exception as e:
        logging.error(f"Fatal error: {e}", exc_info=True)
    finally:
        try:
            asyncio.run(close_db_pool())
            logging.info("Database pool closed")
        except Exception as e:
            logging.error(f"Error closing database pool: {e}")
