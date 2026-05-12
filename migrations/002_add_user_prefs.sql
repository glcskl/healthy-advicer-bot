-- =============================================
-- Migration 002: Add user preferences and content stats
-- =============================================

-- Добавляем поле для настроек пользователя
ALTER TABLE users ADD COLUMN IF NOT EXISTS preferences JSONB DEFAULT '{}';
COMMENT ON COLUMN users.preferences IS 'User preferences (language, notifications, etc.)';

-- Добавляем статистику просмотров контента
ALTER TABLE content ADD COLUMN IF NOT EXISTS view_count INTEGER DEFAULT 0;
ALTER TABLE content ADD COLUMN IF NOT EXISTS download_count INTEGER DEFAULT 0;
COMMENT ON COLUMN content.view_count IS 'Number of times content was viewed';
COMMENT ON COLUMN content.download_count IS 'Number of times content was downloaded';

-- Индекс для статистики
CREATE INDEX IF NOT EXISTS idx_content_views ON content(view_count DESC);
CREATE INDEX IF NOT EXISTS idx_content_downloads ON content(download_count DESC);

-- Таблица для логирования активности пользователей (опционально)
CREATE TABLE IF NOT EXISTS user_activity_log (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    activity_type TEXT NOT NULL,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

COMMENT ON TABLE user_activity_log IS 'Log of user activities for analytics';

CREATE INDEX IF NOT EXISTS idx_activity_user_id ON user_activity_log(user_id);
CREATE INDEX IF NOT EXISTS idx_activity_type ON user_activity_log(activity_type);
CREATE INDEX IF NOT EXISTS idx_activity_created_at ON user_activity_log(created_at DESC);
