import asyncpg
import logging
from typing import Optional, List, Dict, Tuple
from config import DATABASE_URL, ADMIN_IDS
import asyncio
import glob
from pathlib import Path
import aiofiles
from functools import lru_cache
import time

logger = logging.getLogger(__name__)

_pool: Optional[asyncpg.Pool] = None
_cache: Dict[str, Tuple[any, float]] = {}  # Простой кэш: ключ -> (значение, timestamp)
_CACHE_TTL = 300  # 5 минут в секундах


async def init_db_pool():
    """Инициализирует пул соединений с БД с retry logic"""
    global _pool
    if _pool is not None:
        return
    
    max_retries = 3
    retry_delay = 1
    
    for attempt in range(max_retries):
        try:
            _pool = await asyncpg.create_pool(
                DATABASE_URL,
                min_size=1,
                max_size=10,
                command_timeout=30,  # Таймаут запросов 30 секунд
                max_inactive_connection_lifetime=300.0  # Закрывать неактивные соединения через 5 мин
            )
            logger.info(f"Database pool created successfully (attempt {attempt + 1})")
            return
        except Exception as e:
            logger.error(f"Failed to create database pool (attempt {attempt + 1}): {e}")
            if attempt < max_retries - 1:
                await asyncio.sleep(retry_delay)
                retry_delay *= 2  # Экспоненциальная задержка
            else:
                raise


async def close_db_pool():
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


async def get_pool() -> asyncpg.Pool:
    if _pool is None:
        raise RuntimeError("Database pool is not initialized. Call init_db_pool() first.")
    return _pool


async def ensure_migrations_table(conn: asyncpg.Connection):
    """Create schema_migrations table if it doesn't exist"""
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS schema_migrations (
            id SERIAL PRIMARY KEY,
            migration_name TEXT UNIQUE NOT NULL,
            applied_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
        )
    """)


async def get_applied_migrations(conn: asyncpg.Connection) -> set:
    """Get set of already applied migration names"""
    rows = await conn.fetch("SELECT migration_name FROM schema_migrations")
    return {row['migration_name'] for row in rows}


def get_migration_files(migrations_dir: str = "migrations") -> List[Tuple[str, str]]:
    """Get all migration files sorted by numeric prefix (supports both sync and async contexts)"""
    migrations_path = Path(migrations_dir)
    if not migrations_path.exists():
        return []

    migration_files = glob.glob(str(migrations_path / "*.sql"))
    result = []

    for filepath in migration_files:
        filename = Path(filepath).name
        if filename.split('_')[0].isdigit():
            # Извлекаем числовой префикс для корректной сортировки
            prefix = int(filename.split('_')[0])
            result.append((filepath, filename, prefix))

    # Сортируем по числовому префиксу, затем по имени
    result.sort(key=lambda x: (x[2], x[1]))
    return [(filepath, filename) for filepath, filename, _ in result]


async def apply_migrations(migrations_dir: str = "migrations"):
    """
    Apply pending migrations using async file I/O.
    This function is idempotent - safe to call multiple times.
    """
    pool = await get_pool()

    migration_files = get_migration_files(migrations_dir)
    if not migration_files:
        logger.info("No migration files found")
        return

    async with pool.acquire() as conn:
        await ensure_migrations_table(conn)
        applied = await get_applied_migrations(conn)

        applied_count = 0
        for filepath, migration_name in migration_files:
            if migration_name in applied:
                continue

            logger.info(f"Applying migration: {migration_name}")

            # Асинхронное чтение файла
            try:
                async with aiofiles.open(filepath, 'r', encoding='utf-8') as f:
                    sql_content = await f.read()
            except Exception as e:
                logger.error(f"Failed to read migration file {filepath}: {e}")
                raise

            async with conn.transaction():
                await conn.execute(sql_content)
                await conn.execute(
                    "INSERT INTO schema_migrations (migration_name) VALUES ($1)",
                    migration_name
                )

            applied_count += 1

        if applied_count == 0:
            logger.info("All migrations are up to date")
        else:
            logger.info(f"Applied {applied_count} migration(s)")


async def init_db():
    """
    Initialize database with migrations.
    Call this on bot startup.
    """
    await init_db_pool()
    await apply_migrations()


async def register_user(telegram_id: int, username: Optional[str] = None) -> Optional[Dict]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        user = await conn.fetchrow("SELECT * FROM users WHERE telegram_id = $1", telegram_id)

        if not user:
            role = 'admin' if telegram_id in ADMIN_IDS else 'user'
            await conn.execute(
                "INSERT INTO users (telegram_id, username, role) VALUES ($1, $2, $3)",
                telegram_id, username, role
            )
            user = await conn.fetchrow("SELECT * FROM users WHERE telegram_id = $1", telegram_id)
        else:
            await conn.execute(
                "UPDATE users SET last_active_at = CURRENT_TIMESTAMP WHERE id = $1",
                user['id']
            )
            user = await conn.fetchrow("SELECT * FROM users WHERE telegram_id = $1", telegram_id)
    return dict(user) if user else None


async def get_user_by_telegram(telegram_id: int) -> Optional[Dict]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        user = await conn.fetchrow("SELECT * FROM users WHERE telegram_id = $1", telegram_id)
    return dict(user) if user else None


async def get_user_by_id(user_id: int) -> Optional[Dict]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        user = await conn.fetchrow("SELECT * FROM users WHERE id = $1", user_id)
    return dict(user) if user else None


async def update_user_active(telegram_id: int):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE users SET last_active_at = CURRENT_TIMESTAMP WHERE telegram_id = $1",
            telegram_id
        )


async def is_admin(telegram_id: int) -> bool:
    user = await get_user_by_telegram(telegram_id)
    return bool(user and user.get('role') == 'admin')


async def add_content(content_type: str, title: str, description: str,
                      price: int, category_name: str) -> int:
    pool = await get_pool()
    async with pool.acquire() as conn:
        category = await conn.fetchrow("SELECT id FROM categories WHERE name = $1", category_name)
        if not category:
            raise ValueError(f"Category '{category_name}' not found")

        content_id = await conn.fetchval(
            """INSERT INTO content (type, title, description, price, category_id) 
               VALUES ($1, $2, $3, $4, $5) RETURNING id""",
            content_type, title, description, price, category['id']
        )
    return content_id or 0


async def add_content_file(content_id: int, telegram_file_id: str, file_type: str = 'document',
                           file_name: str = None, file_size: int = None, mime_type: str = None) -> int:
    pool = await get_pool()
    async with pool.acquire() as conn:
        file_id = await conn.fetchval(
            """INSERT INTO content_files (content_id, telegram_file_id, file_type, file_name, file_size, mime_type) 
               VALUES ($1, $2, $3, $4, $5, $6) RETURNING id""",
            content_id, telegram_file_id, file_type, file_name, file_size, mime_type
        )
    return file_id or 0


async def get_content_by_id(content_id: int) -> Optional[Dict]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        content = await conn.fetchrow("SELECT * FROM content WHERE id = $1", content_id)
        if content:
            files = await conn.fetch(
                "SELECT * FROM content_files WHERE content_id = $1 ORDER BY sort_order", 
                content_id
            )
            result = dict(content)
            result['files'] = [dict(f) for f in files]
            return result
    return None


async def get_content_by_filters(content_type: str, category_name: str = None) -> List[Dict]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        if category_name:
            rows = await conn.fetch("""
                SELECT c.* FROM content c
                JOIN categories cat ON c.category_id = cat.id
                WHERE c.type = $1 AND cat.name = $2
                ORDER BY c.created_at DESC
            """, content_type, category_name)
        else:
            rows = await conn.fetch("SELECT * FROM content WHERE type = $1 ORDER BY created_at DESC", content_type)
    return [dict(row) for row in rows]


async def get_all_content() -> List[Dict]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT * FROM content ORDER BY id DESC")
    return [dict(row) for row in rows]


async def get_content_with_files(content_id: int) -> Optional[Dict]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        content = await conn.fetchrow("SELECT * FROM content WHERE id = $1", content_id)
        if not content:
            return None
        files = await conn.fetch("SELECT * FROM content_files WHERE content_id = $1 ORDER BY sort_order", content_id)
        result = dict(content)
        result['files'] = [dict(f) for f in files]
        return result


# ==================== OPTIMIZED FUNCTIONS (N+1 FIX) ====================

async def get_content_by_filters_with_purchase_status(
    content_type: str,
    category_name: str = None,
    user_id: int = None
) -> List[Dict]:
    """
    Оптимизированный запрос: получает контент с категориями и статусом покупки за один JOIN.
    Решает N+1 проблему для category_callback.
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        if category_name:
            query = """
                SELECT
                    c.*,
                    cat.name as category_name,
                    cat.display_name as category_display_name,
                    CASE
                        WHEN p.user_id IS NOT NULL AND pay.status = 'succeeded' THEN true
                        ELSE false
                    END as has_purchased
                FROM content c
                JOIN categories cat ON c.category_id = cat.id
                LEFT JOIN purchases p ON p.content_id = c.id AND p.user_id = $3
                LEFT JOIN payments pay ON p.payment_id = pay.id
                WHERE c.type = $1 AND cat.name = $2
                ORDER BY c.created_at DESC
            """
            rows = await conn.fetch(query, content_type, category_name, user_id or 0)
        else:
            query = """
                SELECT
                    c.*,
                    cat.name as category_name,
                    cat.display_name as category_display_name,
                    CASE
                        WHEN p.user_id IS NOT NULL AND pay.status = 'succeeded' THEN true
                        ELSE false
                    END as has_purchased
                FROM content c
                LEFT JOIN categories cat ON c.category_id = cat.id
                LEFT JOIN purchases p ON p.content_id = c.id AND p.user_id = $2
                LEFT JOIN payments pay ON p.payment_id = pay.id
                WHERE c.type = $1
                ORDER BY c.created_at DESC
            """
            rows = await conn.fetch(query, content_type, user_id or 0)
    
    result = []
    for row in rows:
        item = dict(row)
        result.append(item)
    return result


async def get_all_content_with_details(limit: int = 50, offset: int = 0) -> List[Dict]:
    """
    Оптимизированный запрос для админ-панели с пагинацией.
    Решает проблему загрузки всего контента сразу.
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        query = """
            SELECT
                c.*,
                cat.name as category_name,
                cat.display_name as category_display_name,
                COUNT(DISTINCT p.id) as purchase_count
            FROM content c
            LEFT JOIN categories cat ON c.category_id = cat.id
            LEFT JOIN purchases p ON c.id = p.content_id
            GROUP BY c.id, cat.name, cat.display_name
            ORDER BY c.id DESC
            LIMIT $1 OFFSET $2
        """
        rows = await conn.fetch(query, limit, offset)
    return [dict(row) for row in rows]


async def get_content_count_by_type(content_type: str = None) -> int:
    """Получить общее количество контента для пагинации"""
    pool = await get_pool()
    async with pool.acquire() as conn:
        if content_type:
            count = await conn.fetchval(
                "SELECT COUNT(*) FROM content WHERE type = $1",
                content_type
            )
        else:
            count = await conn.fetchval("SELECT COUNT(*) FROM content")
    return count or 0


# ==================== CATEGORY CACHING ====================

@lru_cache(maxsize=128)
def _get_cached_categories(cache_key: str) -> List[Dict]:
    """Внутренняя кэширующая функция (синхронная)"""
    # Эта функция будет вызываться из асинхронного контекста
    # Результат кэшируется в памяти процесса
    pass  # Заглушка, реальная реализация ниже


async def get_content_categories_cached(content_type: str, use_cache: bool = True) -> List[Dict]:
    """
    Кэшированный запрос категорий (TTL 5 минут).
    Решает проблему частых запросов категорий, которые редко меняются.
    """
    cache_key = f"categories_{content_type}"
    
    # Проверяем кэш в памяти
    if use_cache and cache_key in _cache:
        value, timestamp = _cache[cache_key]
        if time.time() - timestamp < _CACHE_TTL:
            return value
    
    # Если нет в кэше или устарел - запрашиваем из БД
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT c.name, c.display_name, c.sort_order
            FROM categories c
            WHERE $1 = ANY(c.type_filter)
            ORDER BY c.sort_order
        """, content_type)
    result = [dict(row) for row in rows]
    
    # Сохраняем в кэш
    _cache[cache_key] = (result, time.time())
    return result


async def invalidate_category_cache():
    """Инвалидировать кэш категорий (вызывать после изменения категорий)"""
    _cache.clear()


async def delete_content(content_id: int) -> bool:
    pool = await get_pool()
    async with pool.acquire() as conn:
        result = await conn.execute("DELETE FROM content WHERE id = $1", content_id)
    return "DELETE" in result


async def create_payment(user_id: int, amount: int, currency: str = 'XTR',
                         payment_method: str = 'stars', external_id: str = None) -> int:
    pool = await get_pool()
    async with pool.acquire() as conn:
        payment_id = await conn.fetchval(
            """INSERT INTO payments (user_id, amount, currency, payment_method, external_id) 
               VALUES ($1, $2, $3, $4, $5) RETURNING id""",
            user_id, amount, currency, payment_method, external_id
        )
    return payment_id or 0


async def update_payment_status(payment_id: int, status: str, completed_at: bool = False):
    pool = await get_pool()
    async with pool.acquire() as conn:
        if completed_at:
            await conn.execute(
                "UPDATE payments SET status = $1, completed_at = CURRENT_TIMESTAMP WHERE id = $2",
                status, payment_id
            )
        else:
            await conn.execute(
                "UPDATE payments SET status = $1 WHERE id = $2",
                status, payment_id
            )


async def get_payment_by_external_id(external_id: str) -> Optional[Dict]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        payment = await conn.fetchrow("SELECT * FROM payments WHERE external_id = $1", external_id)
    return dict(payment) if payment else None


async def add_purchase(user_id: int, content_id: int, payment_id: int = None) -> int:
    pool = await get_pool()
    async with pool.acquire() as conn:
        try:
            purchase_id = await conn.fetchval(
                """INSERT INTO purchases (user_id, content_id, payment_id) 
                   VALUES ($1, $2, $3) RETURNING id""",
                user_id, content_id, payment_id
            )
            return purchase_id or 0
        except asyncpg.UniqueViolationError:
            return 0


async def has_purchased(user_id: int, content_id: int) -> bool:
    pool = await get_pool()
    async with pool.acquire() as conn:
        result = await conn.fetchrow(
            """SELECT p.id FROM purchases p
               JOIN payments pay ON p.payment_id = pay.id
               WHERE p.user_id = $1 AND p.content_id = $2 AND pay.status = 'succeeded'""",
            user_id, content_id
        )
        if result:
            return True
        result2 = await conn.fetchrow(
            "SELECT id FROM purchases WHERE user_id = $1 AND content_id = $2 AND payment_id IS NULL",
            user_id, content_id
        )
        return result2 is not None


async def get_content_categories(content_type: str) -> List[Dict]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT c.name, c.display_name, c.sort_order 
            FROM categories c
            WHERE $1 = ANY(c.type_filter)
            ORDER BY c.sort_order
        """, content_type)
    return [dict(row) for row in rows]


async def get_user_purchases(user_id: int) -> List[Dict]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT c.*, p.purchased_at, pay.payment_method 
            FROM content c
            JOIN purchases p ON c.id = p.content_id
            LEFT JOIN payments pay ON p.payment_id = pay.id
            WHERE p.user_id = $1 AND (pay.status = 'succeeded' OR pay.status IS NULL)
            ORDER BY p.purchased_at DESC
        """, user_id)
    return [dict(row) for row in rows]


async def search_content(search_query: str, content_type: str = None) -> List[Dict]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        if content_type:
            rows = await conn.fetch("""
                SELECT *, ts_rank(search_vector, plainto_tsquery('russian', $1)) as rank
                FROM (
                    SELECT c.*, to_tsvector('russian', COALESCE(c.title, '') || ' ' || COALESCE(c.description, '')) as search_vector
                    FROM content c
                    WHERE c.type = $2
                ) as sub
                WHERE search_vector @@ plainto_tsquery('russian', $1)
                ORDER BY rank DESC
            """, search_query, content_type)
        else:
            rows = await conn.fetch("""
                SELECT *, ts_rank(search_vector, plainto_tsquery('russian', $1)) as rank
                FROM (
                    SELECT c.*, to_tsvector('russian', COALESCE(c.title, '') || ' ' || COALESCE(c.description, '')) as search_vector
                    FROM content c
                ) as sub
                WHERE search_vector @@ plainto_tsquery('russian', $1)
                ORDER BY rank DESC
            """, search_query)
    return [dict(row) for row in rows]


async def get_all_categories() -> List[Dict]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT * FROM categories ORDER BY sort_order")
    return [dict(row) for row in rows]


async def add_category(name: str, display_name: str, type_filter: List[str], sort_order: int = 0) -> int:
    pool = await get_pool()
    async with pool.acquire() as conn:
        category_id = await conn.fetchval(
            """INSERT INTO categories (name, display_name, type_filter, sort_order) 
               VALUES ($1, $2, $3, $4) RETURNING id""",
            name, display_name, type_filter, sort_order
        )
    return category_id or 0


async def get_category_by_id(category_id: int) -> Optional[Dict]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        category = await conn.fetchrow("SELECT * FROM categories WHERE id = $1", category_id)
    return dict(category) if category else None


async def get_migration_status() -> Dict:
    """Get migration status for monitoring"""
    pool = await get_pool()
    async with pool.acquire() as conn:
        await ensure_migrations_table(conn)
        applied = await get_applied_migrations(conn)
        migration_files = get_migration_files()

        return {
            'total': len(migration_files),
            'applied': len(applied),
            'pending': len(migration_files) - len(applied),
            'applied_list': list(applied),
            'pending_list': [name for _, name in migration_files if name not in applied]
        }
