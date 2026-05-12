from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder


def get_main_menu_reply(user_role: str) -> ReplyKeyboardMarkup:
    """Persistent reply keyboard with main menu buttons."""
    builder = ReplyKeyboardBuilder()
    builder.row(KeyboardButton(text="🥗 Планы питания"))
    builder.row(KeyboardButton(text="💪 Программы тренировок"))
    builder.row(KeyboardButton(text="🎬 Обучающие видео"))
    builder.row(KeyboardButton(text="📦 Мои покупки"))
    if user_role == 'admin':
        builder.row(KeyboardButton(text="🔧 Админ-панель"))
    return builder.as_markup(resize_keyboard=True)


def main_menu_keyboard(is_admin: bool = False) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🥗 Планы питания", callback_data="menu:nutrition_plan"))
    builder.row(InlineKeyboardButton(text="💪 Программы тренировок", callback_data="menu:workout_program"))
    builder.row(InlineKeyboardButton(text="🎬 Обучающие видео", callback_data="menu:training_video"))
    builder.row(InlineKeyboardButton(text="📦 Мои покупки", callback_data="menu:my_purchases"))
    if is_admin:
        builder.row(InlineKeyboardButton(text="🔧 Админ-панель", callback_data="admin:panel"))
    return builder.as_markup()


def category_filter_keyboard(content_type: str, categories: list) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for cat in categories:
        # cat теперь dict с полями name, display_name
        display = cat.get('display_name', cat.get('name', 'Категория'))
        builder.row(InlineKeyboardButton(text=display, callback_data=f"category:{content_type}:{cat['name']}"))
    builder.row(InlineKeyboardButton(text="◀️ Назад", callback_data="menu:back"))
    return builder.as_markup()


def content_list_keyboard(contents: list, user_id: int, has_purchased_ids: set) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for content in contents:
        cid = content['id']
        if content['is_paid'] and cid not in has_purchased_ids:
            builder.row(InlineKeyboardButton(
                text=f"{content['title']} — {content['price']}⭐️",
                callback_data=f"content:preview:{cid}"
            ))
        else:
            status = "✅" if cid in has_purchased_ids else "🆓"
            builder.row(InlineKeyboardButton(
                text=f"{status} {content['title']}",
                callback_data=f"content:view:{cid}"
            ))
    builder.row(InlineKeyboardButton(text="◀️ Назад", callback_data="menu:back"))
    return builder.as_markup()


def purchase_keyboard(content_id: int, price: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text=f"Купить за {price}⭐️", callback_data=f"content:buy:{content_id}"))
    builder.row(InlineKeyboardButton(text="◀️ Назад", callback_data="menu:back"))
    return builder.as_markup()


def content_view_keyboard(content_id: int, content_type: str, is_paid: bool, has_purchased: bool) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if not is_paid or has_purchased:
        if content_type == "training_video":
            builder.row(InlineKeyboardButton(text="▶️ Смотреть видео", callback_data=f"content:watch:{content_id}"))
        elif content_type in ("nutrition_plan", "workout_program"):
            builder.row(InlineKeyboardButton(text="📥 Скачать файл", callback_data=f"content:download:{content_id}"))
    builder.row(InlineKeyboardButton(text="◀️ Назад", callback_data="menu:back"))
    return builder.as_markup()


def admin_panel_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="➕ Загрузить контент", callback_data="admin:upload"))
    builder.row(InlineKeyboardButton(text="📋 Список контента", callback_data="admin:list"))
    builder.row(InlineKeyboardButton(text="◀️ Назад", callback_data="menu:back"))
    return builder.as_markup()


def admin_upload_type_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🥗 План питания", callback_data="admin:type:nutrition_plan"))
    builder.row(InlineKeyboardButton(text="💪 Программа тренировок", callback_data="admin:type:workout_program"))
    builder.row(InlineKeyboardButton(text="🎬 Обучающее видео", callback_data="admin:type:training_video"))
    builder.row(InlineKeyboardButton(text="◀️ Назад", callback_data="admin:panel"))
    return builder.as_markup()


def admin_category_keyboard(content_type: str, categories: list = None) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    
    # Если категории не переданы, получаем их из БД через вызов функции
    # (передаём пустой список, чтобы вызывающий код сам получил категории)
    if categories is None:
        categories = []
    
    # Генерируем кнопки динамически из списка категорий
    for cat in categories:
        # cat может быть dict с полями name, display_name
        name = cat.get('name', '') if isinstance(cat, dict) else str(cat)
        display = cat.get('display_name', name) if isinstance(cat, dict) else str(cat)
        builder.row(InlineKeyboardButton(text=display, callback_data=f"admin:category:{name}"))
    
    builder.row(InlineKeyboardButton(text="◀️ Назад", callback_data="admin:upload"))
    return builder.as_markup()


def admin_content_list_keyboard(contents: list) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for content in contents:
        builder.row(InlineKeyboardButton(
            text=f"🗑 {content['title']} (ID:{content['id']})",
            callback_data=f"admin:delete:{content['id']}"
        ))
    builder.row(InlineKeyboardButton(text="◀️ Назад", callback_data="admin:panel"))
    return builder.as_markup()


def confirm_delete_keyboard(content_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="✅ Удалить", callback_data=f"admin:confirm_delete:{content_id}"),
        InlineKeyboardButton(text="❌ Отмена", callback_data="admin:list")
    )
    return builder.as_markup()
