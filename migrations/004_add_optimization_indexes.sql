-- =============================================
-- Migration 004: Add performance optimization indexes
-- =============================================

-- Composite index for optimized JOIN queries in get_content_with_purchase_status
-- This index speeds up queries that filter by content_id AND user_id simultaneously
CREATE INDEX IF NOT EXISTS idx_purchases_content_user ON purchases(content_id, user_id);

-- Additional index for payments status + payment_id lookup (used in has_purchased query)
CREATE INDEX IF NOT EXISTS idx_payments_status_id ON payments(status, id);

-- Log migration application
DO $$
BEGIN
    RAISE NOTICE 'Migration 004: Performance indexes added successfully';
END $$;
