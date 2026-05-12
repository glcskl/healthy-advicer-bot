-- =============================================
-- Migration 003: Add all missing categories
-- =============================================

-- Добавляем все категории с ON CONFLICT DO NOTHING для избежания ошибок
INSERT INTO categories (name, display_name, type_filter, sort_order) VALUES
    -- Universal categories
    ('beginner', '🌱 Новичок', '{nutrition_plan,workout_program,training_video}', 10),
    ('intermediate', '⚡ Средний', '{nutrition_plan,workout_program,training_video}', 20),
    ('advanced', '🔥 Продвинутый', '{nutrition_plan,workout_program,training_video}', 30),
    
    -- Workout & Video categories  
    ('strength', '🏋️ Силовые', '{workout_program,training_video}', 40),
    ('cardio', '🏃 Кардио', '{workout_program,training_video}', 50),
    ('yoga', '🧘 Йога', '{workout_program,training_video}', 60),
    ('crossfit', '🤸 Кроссфит', '{workout_program,training_video}', 70),
    ('home_workout', '🏠 Домашние тренировки', '{workout_program,training_video}', 80),
    ('gym_workout', '🏋️‍♂️ Тренировки в зале', '{workout_program,training_video}', 90),
    ('stretching', '🧘‍♀️ Растяжка', '{workout_program,training_video}', 100),
    ('technique', '📐 Техника упражнений', '{training_video}', 110),
    ('endurance', '🫀 Выносливость', '{workout_program,training_video}', 120),
    
    -- Nutrition categories
    ('mass_gainer', '💪 Набор массы', '{nutrition_plan}', 130),
    ('cutting', '🔥 Сушка', '{nutrition_plan}', 140),
    ('maintenance', '⚖️ Поддержание', '{nutrition_plan}', 150),
    ('meal_prep', '🍳 Приготовление еды', '{nutrition_plan}', 160),
    ('weight_loss', '📉 Похудение', '{nutrition_plan,workout_program}', 170),
    ('muscle_gain', '📈 Набор мышечной массы', '{nutrition_plan,workout_program}', 180),
    ('supplements', '💊 Спортивное питание', '{nutrition_plan}', 190)
ON CONFLICT (name) DO NOTHING;

-- Проверяем, сколько категорий теперь в базе
DO $$
DECLARE
    cat_count integer;
BEGIN
    SELECT COUNT(*) INTO cat_count FROM categories;
    RAISE NOTICE 'Total categories after migration: %', cat_count;
END $$;
