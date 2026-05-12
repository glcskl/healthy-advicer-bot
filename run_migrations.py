#!/usr/bin/env python3
"""
Migration runner for Telegram Fitness Bot.
Run migrations against PostgreSQL database (Neon).

Usage:
    # Using config.py
    python run_migrations.py

    # Using environment variable
    DATABASE_URL="postgresql://..." python run_migrations.py

    # Show status
    python run_migrations.py --status

    # Rollback last migration (if down migration exists)
    python run_migrations.py --rollback-last
"""

import asyncio
import asyncpg
import os
import sys
import glob
import logging
from pathlib import Path
from typing import List, Tuple

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def get_database_url() -> str:
    """Get DATABASE_URL from environment or config.py"""
    # Сначала проверяем переменную окружения
    db_url = os.getenv('DATABASE_URL')
    if db_url:
        return db_url

    # Пытаемся импортировать из config.py
    try:
        sys.path.insert(0, str(Path(__file__).parent))
        from config import DATABASE_URL
        return DATABASE_URL
    except ImportError:
        raise ValueError(
            "DATABASE_URL not found. Set environment variable or create config.py"
        )


def get_migration_files(migrations_dir: str = "migrations") -> List[Tuple[str, str]]:
    """
    Get all migration files sorted by prefix number.
    Returns list of (filepath, migration_name) tuples.
    Only includes .sql files that don't end with .down.sql
    """
    migrations_path = Path(migrations_dir)
    if not migrations_path.exists():
        logger.error(f"Migrations directory '{migrations_dir}' not found")
        return []

    # Ищем все .sql файлы, исключая .down.sql
    migration_files = [
        str(p) for p in migrations_path.glob("*.sql") 
        if not p.name.endswith(".down.sql")
    ]

    # Филтруем только файлы с числовым префиксом (001_, 002_, etc.)
    result = []
    for filepath in migration_files:
        filename = Path(filepath).name
        # Проверяем, начинается ли имя с цифр и содержит подчёркивание
        parts = filename.split('_')
        if parts[0].isdigit():
            result.append((filepath, filename))

    # Сортируем по префиксу
    result.sort(key=lambda x: x[1])
    return result


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


async def apply_migration(conn: asyncpg.Connection, filepath: str, migration_name: str):
    """Apply a single migration file"""
    logger.info(f"Applying migration: {migration_name}")

    with open(filepath, 'r', encoding='utf-8') as f:
        sql_content = f.read()

    # Выполняем миграцию в транзакции
    async with conn.transaction():
        # Выполняем SQL
        await conn.execute(sql_content)

        # Записываем информацию о применённой миграции
        await conn.execute(
            "INSERT INTO schema_migrations (migration_name) VALUES ($1)",
            migration_name
        )

    logger.info(f"Migration applied successfully: {migration_name}")


async def run_migrations(migrations_dir: str = "migrations"):
    """Main migration runner"""
    database_url = get_database_url()
    logger.info("Starting migrations...")

    # Получаем список файлов миграций
    migration_files = get_migration_files(migrations_dir)
    if not migration_files:
        logger.warning("No migration files found")
        return

    logger.info(f"Found {len(migration_files)} migration file(s)")

    # Подключаемся к базе
    conn = await asyncpg.connect(database_url)

    try:
        # Создаём таблицу миграций, если её нет
        await ensure_migrations_table(conn)

        # Получаем список применённых миграций
        applied = await get_applied_migrations(conn)
        logger.info(f"Already applied: {len(applied)} migration(s)")

        # Применяем новые миграции
        applied_count = 0
        for filepath, migration_name in migration_files:
            if migration_name in applied:
                logger.debug(f"Skipping already applied: {migration_name}")
                continue

            await apply_migration(conn, filepath, migration_name)
            applied_count += 1

        if applied_count == 0:
            logger.info("All migrations are up to date")
        else:
            logger.info(f"Successfully applied {applied_count} migration(s)")

    except Exception as e:
        logger.error(f"Migration failed: {e}")
        raise
    finally:
        await conn.close()


async def show_status(migrations_dir: str = "migrations"):
    """Show migration status"""
    database_url = get_database_url()

    conn = await asyncpg.connect(database_url)

    try:
        await ensure_migrations_table(conn)
        applied = await get_applied_migrations(conn)
        migration_files = get_migration_files(migrations_dir)

        print("\nMigration Status:")
        print("-" * 60)
        print(f"{'Migration':<40} {'Status':<10}")
        print("-" * 60)

        for filepath, migration_name in migration_files:
            status = "Applied" if migration_name in applied else "Pending"
            print(f"{migration_name:<40} {status:<10}")

        print("-" * 60)
        print(f"Total: {len(migration_files)} | Applied: {len(applied)} | Pending: {len(migration_files) - len(applied)}")

    finally:
        await conn.close()


async def rollback_last(migrations_dir: str = "migrations"):
    """
    Rollback last migration (if down migration exists).
    Looks for file with .down.sql extension.
    """
    database_url = get_database_url()

    conn = await asyncpg.connect(database_url)

    try:
        await ensure_migrations_table(conn)

        # Получаем последнюю применённую миграцию
        row = await conn.fetchrow(
            "SELECT migration_name FROM schema_migrations ORDER BY applied_at DESC LIMIT 1"
        )

        if not row:
            logger.warning("No migrations to rollback")
            return

        last_migration = row['migration_name']
        logger.info(f"Rolling back: {last_migration}")

        # Ищем down-миграцию
        down_file = last_migration.replace('.sql', '.down.sql')
        down_path = Path(migrations_dir) / down_file

        if not down_path.exists():
            logger.error(f"Down migration file not found: {down_file}")
            logger.error("Create a down migration file or rollback manually")
            return

        # Выполняем down-миграцию
        with open(down_path, 'r', encoding='utf-8') as f:
            sql_content = f.read()

        async with conn.transaction():
            await conn.execute(sql_content)
            await conn.execute(
                "DELETE FROM schema_migrations WHERE migration_name = $1",
                last_migration
            )

        logger.info(f"Rollback successful: {last_migration}")

    finally:
        await conn.close()


def main():
    """Entry point"""
    import argparse

    parser = argparse.ArgumentParser(description='Run database migrations')
    parser.add_argument('--status', action='store_true', help='Show migration status')
    parser.add_argument('--rollback-last', action='store_true', help='Rollback last migration')
    parser.add_argument('--migrations-dir', default='migrations', help='Migrations directory')
    args = parser.parse_args()

    if args.status:
        asyncio.run(show_status(args.migrations_dir))
    elif args.rollback_last:
        asyncio.run(rollback_last(args.migrations_dir))
    else:
        asyncio.run(run_migrations(args.migrations_dir))


if __name__ == "__main__":
    main()
