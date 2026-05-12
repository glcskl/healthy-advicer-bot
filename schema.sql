-- =============================================
-- Telegram Fitness Bot Database Schema
-- PostgreSQL 17 - Optimized for Neon
-- =============================================

-- Enable necessary extensions
CREATE EXTENSION IF NOT EXISTS pg_trgm; -- For text search optimization

-- =============================================
-- Function for automatic updated_at timestamp
-- =============================================
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

-- =============================================
-- Table: users
-- =============================================
CREATE TABLE IF NOT EXISTS users (
    id BIGSERIAL PRIMARY KEY,
    telegram_id BIGINT UNIQUE NOT NULL,
    username TEXT,
    role TEXT DEFAULT 'user' CHECK (role IN ('user', 'admin')),
    registered_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    last_active_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

COMMENT ON TABLE users IS 'Telegram bot users';
COMMENT ON COLUMN users.id IS 'Primary key, auto-incrementing';
COMMENT ON COLUMN users.telegram_id IS 'Unique Telegram user ID (BIGINT for future-proofing)';
COMMENT ON COLUMN users.username IS 'Telegram username (without @)';
COMMENT ON COLUMN users.role IS 'User role: user or admin';
COMMENT ON COLUMN users.registered_at IS 'When the user first interacted with the bot';
COMMENT ON COLUMN users.last_active_at IS 'Last activity timestamp for analytics';

-- =============================================
-- Table: categories
-- =============================================
CREATE TABLE IF NOT EXISTS categories (
    id BIGSERIAL PRIMARY KEY,
    name TEXT UNIQUE NOT NULL,
    display_name TEXT NOT NULL,
    type_filter TEXT[] NOT NULL DEFAULT '{}',
    sort_order INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

COMMENT ON TABLE categories IS 'Content categories with flexible type filtering';
COMMENT ON COLUMN categories.id IS 'Primary key';
COMMENT ON COLUMN categories.name IS 'Internal category name (unique identifier)';
COMMENT ON COLUMN categories.display_name IS 'Human-readable name for buttons/UI';
COMMENT ON COLUMN categories.type_filter IS 'Array of content types this category applies to (e.g., {nutrition_plan, workout_program})';
COMMENT ON COLUMN categories.sort_order IS 'Display order for categories';

-- =============================================
-- Table: content
-- =============================================
CREATE TABLE IF NOT EXISTS content (
    id BIGSERIAL PRIMARY KEY,
    type TEXT NOT NULL CHECK (type IN ('nutrition_plan', 'workout_program', 'training_video')),
    title TEXT NOT NULL,
    description TEXT,
    price INTEGER NOT NULL DEFAULT 0 CHECK (price >= 0),
    category_id BIGINT REFERENCES categories(id) ON DELETE RESTRICT,
    is_paid BOOLEAN GENERATED ALWAYS AS (price > 0) STORED,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_content_category FOREIGN KEY (category_id) REFERENCES categories(id)
);

COMMENT ON TABLE content IS 'Content items: nutrition plans, workout programs, training videos';
COMMENT ON COLUMN content.id IS 'Primary key';
COMMENT ON COLUMN content.type IS 'Content type: nutrition_plan, workout_program, or training_video';
COMMENT ON COLUMN content.title IS 'Content title';
COMMENT ON COLUMN content.description IS 'Content description (supports markdown)';
COMMENT ON COLUMN content.price IS 'Price in smallest units (kopeks for RUB, stars for XTR)';
COMMENT ON COLUMN content.category_id IS 'Reference to categories table';
COMMENT ON COLUMN content.is_paid IS 'Computed field: true if price > 0';
COMMENT ON COLUMN content.created_at IS 'Creation timestamp';
COMMENT ON COLUMN content.updated_at IS 'Last update timestamp (auto-updated)';

-- Trigger for updated_at on content
CREATE TRIGGER update_content_updated_at BEFORE UPDATE ON content
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- =============================================
-- Table: content_files
-- =============================================
CREATE TABLE IF NOT EXISTS content_files (
    id BIGSERIAL PRIMARY KEY,
    content_id BIGINT NOT NULL REFERENCES content(id) ON DELETE CASCADE,
    file_path TEXT NOT NULL,
    file_type TEXT CHECK (file_type IN ('document', 'video', 'photo', 'archive')),
    file_name TEXT,
    file_size INTEGER,
    sort_order INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

COMMENT ON TABLE content_files IS 'Multiple files associated with content items';
COMMENT ON COLUMN content_files.content_id IS 'Reference to parent content';
COMMENT ON COLUMN content_files.file_path IS 'File path or Telegram file_id';
COMMENT ON COLUMN content_files.file_type IS 'Type of file for proper handling';
COMMENT ON COLUMN content_files.sort_order IS 'Order of files within content';

-- =============================================
-- Table: payments
-- =============================================
CREATE TABLE IF NOT EXISTS payments (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    external_id TEXT UNIQUE,
    amount INTEGER NOT NULL CHECK (amount >= 0),
    currency TEXT DEFAULT 'XTR',
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'succeeded', 'failed', 'refunded')),
    payment_method TEXT NOT NULL DEFAULT 'stars' CHECK (payment_method IN ('stars', 'card', 'sbp')),
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMPTZ
);

COMMENT ON TABLE payments IS 'Payment transactions from various payment systems';
COMMENT ON COLUMN payments.user_id IS 'User who made the payment';
COMMENT ON COLUMN payments.external_id IS 'External payment ID from payment system (e.g., Telegram Stars transaction)';
COMMENT ON COLUMN payments.amount IS 'Payment amount in smallest units';
COMMENT ON COLUMN payments.currency IS 'Currency code (XTR for Telegram Stars, RUB for rubles)';
COMMENT ON COLUMN payments.status IS 'Payment status: pending, succeeded, failed, refunded';
COMMENT ON COLUMN payments.payment_method IS 'Payment method: stars, card, sbp';
COMMENT ON COLUMN payments.metadata IS 'Additional payment data (JSON)';
COMMENT ON COLUMN payments.completed_at IS 'When payment was completed (succeeded or failed)';

-- =============================================
-- Table: purchases
-- =============================================
CREATE TABLE IF NOT EXISTS purchases (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    content_id BIGINT NOT NULL REFERENCES content(id) ON DELETE CASCADE,
    payment_id BIGINT REFERENCES payments(id) ON DELETE SET NULL,
    purchased_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, content_id)
);

COMMENT ON TABLE purchases IS 'User purchases linking users to content via payments';
COMMENT ON COLUMN purchases.user_id IS 'User who made the purchase';
COMMENT ON COLUMN purchases.content_id IS 'Purchased content';
COMMENT ON COLUMN purchases.payment_id IS 'Associated payment record';
COMMENT ON COLUMN purchases.purchased_at IS 'Purchase timestamp';

-- =============================================
-- Indexes for performance
-- =============================================

-- Users indexes
CREATE INDEX IF NOT EXISTS idx_users_telegram_id ON users(telegram_id);
CREATE INDEX IF NOT EXISTS idx_users_role ON users(role);
CREATE INDEX IF NOT EXISTS idx_users_last_active ON users(last_active_at DESC);

-- Categories indexes
CREATE INDEX IF NOT EXISTS idx_categories_name ON categories(name);
CREATE INDEX IF NOT EXISTS idx_categories_type_filter ON categories USING GIN(type_filter);

-- Content indexes
CREATE INDEX IF NOT EXISTS idx_content_type ON content(type);
CREATE INDEX IF NOT EXISTS idx_content_category_id ON content(category_id);
CREATE INDEX IF NOT EXISTS idx_content_price ON content(price);
CREATE INDEX IF NOT EXISTS idx_content_is_paid ON content(is_paid);
CREATE INDEX IF NOT EXISTS idx_content_type_category ON content(type, category_id);

-- Full-text search index for content
CREATE INDEX IF NOT EXISTS idx_content_search ON content USING GIN(
    to_tsvector('russian', COALESCE(title, '') || ' ' || COALESCE(description, ''))
);

-- Content files indexes
CREATE INDEX IF NOT EXISTS idx_content_files_content_id ON content_files(content_id);

-- Payments indexes
CREATE INDEX IF NOT EXISTS idx_payments_user_id ON payments(user_id);
CREATE INDEX IF NOT EXISTS idx_payments_status ON payments(status);
CREATE INDEX IF NOT EXISTS idx_payments_external_id ON payments(external_id);
CREATE INDEX IF NOT EXISTS idx_payments_created_at ON payments(created_at DESC);

-- Purchases indexes
CREATE INDEX IF NOT EXISTS idx_purchases_user_id ON purchases(user_id);
CREATE INDEX IF NOT EXISTS idx_purchases_content_id ON purchases(content_id);
CREATE INDEX IF NOT EXISTS idx_purchases_payment_id ON purchases(payment_id);
CREATE INDEX IF NOT EXISTS idx_purchases_user_content ON purchases(user_id, content_id);

-- =============================================
-- View: active_purchases
-- =============================================
CREATE OR REPLACE VIEW v_active_purchases AS
SELECT 
    p.id AS purchase_id,
    p.purchased_at,
    u.id AS user_db_id,
    u.telegram_id,
    u.username,
    c.id AS content_id,
    c.type AS content_type,
    c.title AS content_title,
    c.description AS content_description,
    c.price,
    cat.name AS category_name,
    cat.display_name AS category_display_name,
    pay.status AS payment_status,
    pay.payment_method,
    pay.amount AS paid_amount
FROM purchases p
JOIN users u ON p.user_id = u.id
JOIN content c ON p.content_id = c.id
LEFT JOIN categories cat ON c.category_id = cat.id
LEFT JOIN payments pay ON p.payment_id = pay.id
WHERE pay.status = 'succeeded' OR pay.status IS NULL;

COMMENT ON VIEW v_active_purchases IS 'View showing successful purchases with full content and user details';

-- =============================================
-- Initial data: Default categories
-- =============================================
INSERT INTO categories (name, display_name, type_filter, sort_order) VALUES
    ('mass_gainer', 'Набор массы', '{workout_program,nutrition_plan}', 10), 
    ('cutting', 'Сушка', '{workout_program,nutrition_plan}', 20),
    ('maintenance', 'Поддержание', '{workout_program,nutrition_plan}', 30),
    ('beginner', 'Для новичков', '{workout_program,nutrition_plan,training_video}', 40),
    ('advanced', 'Продвинутые', '{workout_program,nutrition_plan}', 50),
    ('home_workout', 'Домашние тренировки', '{workout_program,training_video}', 60),
    ('gym_workout', 'Тренировки в зале', '{workout_program,training_video}', 70),
    ('meal_prep', 'Приготовление еды', '{nutrition_plan}', 80),
    ('supplements', 'Спортивное питание', '{nutrition_plan}', 90),
    ('stretching', 'Растяжка', '{training_video}', 100),
    ('technique', 'Техника упражнений', '{training_video}', 110)
ON CONFLICT (name) DO NOTHING;

