#!/usr/bin/env python3
"""
Performance Audit Script - Проверка индексов и производительности БД
Использование: python check_indexes.py
"""

import asyncio
import asyncpg
import os
from dotenv import load_dotenv
from config import DATABASE_URL

load_dotenv()


async def check_indexes():
    """Проверяет наличие всех необходимых индексов и их использование"""
    pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=1)
    async with pool.acquire() as conn:
        print("=" * 60)
        print("ПРОВЕРКА ИНДЕКСОВ БАЗЫ ДАННЫХ")
        print("=" * 60)

        # Список ожидаемых индексов
        expected_indexes = {
            'users': [
                'idx_users_telegram_id',
                'idx_users_role',
                'idx_users_last_active',
            ],
            'categories': [
                'idx_categories_name',
                'idx_categories_type_filter',
            ],
            'content': [
                'idx_content_type',
                'idx_content_category_id',
                'idx_content_price',
                'idx_content_is_paid',
                'idx_content_type_category',
                'idx_content_search',
            ],
            'content_files': [
                'idx_content_files_content_id',
            ],
            'payments': [
                'idx_payments_user_id',
                'idx_payments_status',
                'idx_payments_external_id',
                'idx_payments_created_at',
                'idx_payments_status_id',  # Новый индекс
            ],
            'purchases': [
                'idx_purchases_user_id',
                'idx_purchases_content_id',
                'idx_purchases_payment_id',
                'idx_purchases_user_content',
                'idx_purchases_content_user',  # Новый индекс
            ],
        }

        for table, indexes in expected_indexes.items():
            print(f"\n📋 Таблица: {table}")
            # Получаем фактические индексы
            query = """
                SELECT indexname, indexdef
                FROM pg_indexes
                WHERE tablename = $1
                ORDER BY indexname;
            """
            rows = await conn.fetch(query, table)

            actual_indexes = {row['indexname'] for row in rows}
            expected_set = set(indexes)

            missing = expected_set - actual_indexes
            extra = actual_indexes - expected_set

            if missing:
                print(f"   ❌ Отсутствуют индексы: {', '.join(missing)}")
            if extra:
                print(f"   ℹ️  Дополнительные индексы: {', '.join(extra)}")

            if not missing and not extra:
                print(f"   ✅ Все индексы на месте ({len(indexes)} шт.)")

            # Показываем фактические индексы
            for row in rows:
                print(f"   • {row['indexname']}")

        # Проверяем размеры таблиц (для оценки роста)
        print("\n" + "=" * 60)
        print("РАЗМЕРЫ ТАБЛИЦ")
        print("=" * 60)

        size_query = """
            SELECT
                relname as table_name,
                pg_size_pretty(pg_total_relation_size(relid)) as total_size,
                pg_size_pretty(pg_relation_size(relid)) as data_size,
                pg_size_pretty(pg_total_relation_size(relid) - pg_relation_size(relid)) as indexes_size
            FROM pg_catalog.pg_statio_user_tables
            ORDER BY pg_total_relation_size(relid) DESC;
        """
        rows = await conn.fetch(size_query)
        for row in rows:
            print(f"   {row['table_name']}: total={row['total_size']}, data={row['data_size']}, indexes={row['indexes_size']}")

        # Проверяем статистику по запросам (если pg_stat_statements установлен)
        print("\n" + "=" * 60)
        print("СТАТИСТИКА ЗАПРОСОВ (если pg_stat_statements доступен)")
        print("=" * 60)

        try:
            stats_query = """
                SELECT
                    query,
                    calls,
                    total_exec_time,
                    mean_exec_time,
                    rows
                FROM pg_stat_statements
                WHERE query LIKE '%healthy_advicer_bot%'
                   OR query LIKE '%content%'
                   OR query LIKE '%purchases%'
                ORDER BY total_exec_time DESC
                LIMIT 10;
            """
            rows = await conn.fetch(stats_query)
            if rows:
                for row in rows:
                    print(f"\n   Запрос: {row['query'][:100]}...")
                    print(f"   Вызовов: {row['calls']}, Среднее время: {row['mean_exec_time']:.2f}ms, Строк: {row['rows']}")
            else:
                print("   ℹ️  pg_stat_statements не активен или нет статистики")
        except Exception as e:
            print(f"   ⚠️  Не удалось получить статистику: {e}")

    await pool.close()
    print("\n✅ Проверка завершена")


if __name__ == "__main__":
    asyncio.run(check_indexes())
