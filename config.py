import os
import logging
from dotenv import load_dotenv

# Инициализируем логгер до использования
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

load_dotenv()

# Обязательные переменные
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN не установлен в переменных окружения!")

# Опциональные переменные с валидацией
admin_ids_str = os.getenv("ADMIN_IDS", "").strip()
if admin_ids_str:
    try:
        ADMIN_IDS = [int(x.strip()) for x in admin_ids_str.split(",") if x.strip()]
    except ValueError as e:
        logger.warning(f"Invalid ADMIN_IDS format: {e}. Using empty list.")
        ADMIN_IDS = []
else:
    ADMIN_IDS = []

DATABASE_URL = os.getenv("DATABASE_URL", "")
if not DATABASE_URL:
    raise ValueError("DATABASE_URL не установлен в переменных окружения!")

WEBHOOK_URL = os.getenv("WEBHOOK_URL", "")
REDIS_URL = os.getenv("REDIS_URL", "")  # Для персистентного хранения FSM
UPLOADS_DIR = os.getenv("UPLOADS_DIR", "uploads")
PAYMENT_PROVIDER_TOKEN = os.getenv("PAYMENT_PROVIDER_TOKEN", "")

# Настройки безопасности
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50 МБ
MAX_TITLE_LENGTH = 200
MAX_DESCRIPTION_LENGTH = 4000
MAX_PRICE = 10000

ALLOWED_EXTENSIONS = {
    "nutrition_plan": [".xlsx"],
    "workout_program": [".xlsx"],
    "training_video": [".mp4", ".avi", ".mov", ".mkv"],
}

ALLOWED_PHOTO_EXTENSIONS = [".jpg", ".jpeg", ".png", ".webp"]

CURRENCY_SYMBOL = "XTR"

# Логирование конфигурации
logger.info(f"Config loaded: BOT_TOKEN={'***' if BOT_TOKEN else 'MISSING'}, REDIS_URL={'***' if REDIS_URL else 'not set'}")
