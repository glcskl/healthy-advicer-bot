import logging
from aiogram import Router, F, types
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.filters import Command
from aiogram.types import LabeledPrice, ReplyKeyboardRemove
import database as db
from keyboards import (
    main_menu_keyboard, category_filter_keyboard, content_list_keyboard,
    purchase_keyboard, content_view_keyboard, admin_panel_keyboard,
    admin_upload_type_keyboard, admin_category_keyboard,
    admin_content_list_keyboard, confirm_delete_keyboard,
    get_main_menu_reply
)
from config import ADMIN_IDS, CURRENCY_SYMBOL

logger = logging.getLogger(__name__)

router = Router()


class AdminUploadState(StatesGroup):
    waiting_for_type = State()
    waiting_for_title = State()
    waiting_for_description = State()
    waiting_for_category = State()
    waiting_for_price = State()
    waiting_for_file = State()


class UserState(StatesGroup):
    pending_content_type = State()
    pending_category = State()


async def show_content_categories(target, content_type: str, label: str, is_callback: bool = False):
    """Common function to show category selection for a content type with cached categories."""
    user = await db.get_user_by_telegram(target.from_user.id)
    if not user:
        msg = "Пользователь не найден"
        if is_callback:
            await target.answer(msg, show_alert=True)
        else:
            await target.answer(msg)
        return
    
    # Используем кэшированные категории для уменьшения нагрузки на БД
    categories = await db.get_content_categories_cached(content_type)
    if not categories:
        msg = f"В разделе «{label}» пока нет материалов."
        if is_callback:
            await target.message.edit_text(msg)
            await target.answer()
        else:
            await target.answer(msg)
        return
    
    text = f"{label}\n\nВыберите категорию:"
    markup = category_filter_keyboard(content_type, categories)
    if is_callback:
        await target.message.edit_text(text, reply_markup=markup)
        await target.answer()
    else:
        await target.answer(text, reply_markup=markup)


@router.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    user = await db.register_user(
        telegram_id=message.from_user.id,
        username=message.from_user.username
    )
    user_role = user['role'] if user else 'user'
    await message.answer(
        "🏋️ Добро пожаловать в Фитнес-Бот!\n\n"
        "Здесь вы найдёте:\n"
        "🥗 Планы питания\n"
        "💪 Программы тренировок\n"
        "🎬 Обучающие видео\n\n"
        "Выберите раздел:",
        reply_markup=get_main_menu_reply(user_role)
    )


@router.message(Command("admin"))
async def cmd_admin(message: types.Message):
    if not await db.is_admin(message.from_user.id):
        await message.answer("❌ У вас нет прав администратора.")
        return
    await message.answer(
        "🔧 Админ-панель",
        reply_markup=admin_panel_keyboard()
    )


@router.callback_query(F.data == "menu:back")
async def back_to_menu(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    user = await db.get_user_by_telegram(callback.from_user.id)
    is_admin = user and user.get('role') == 'admin'
    # Отправляем новое сообщение с reply-клавиатурой
    await callback.message.answer(
        "🏋️ Главное меню",
        reply_markup=get_main_menu_reply(user['role'] if user else 'user')
    )
    # Удаляем или редактируем старое сообщение (убираем inline-кнопки)
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    await callback.answer()


@router.callback_query(F.data.startswith("menu:"))
async def menu_callback(callback: types.CallbackQuery):
    action = callback.data.split(":")[1]
    content_map = {
        "nutrition_plan": ("🥗 Планы питания", "nutrition_plan"),
        "workout_program": ("💪 Программы тренировок", "workout_program"),
        "training_video": ("🎬 Обучающие видео", "training_video"),
    }
    if action == "my_purchases":
        await show_my_purchases(callback)
        return
    if action in content_map:
        label, content_type = content_map[action]
        await show_content_categories(callback, content_type, label, is_callback=True)
        return
    await callback.answer()


@router.message(F.text == "🥗 Планы питания")
async def text_nutrition_plan(message: types.Message):
    await show_content_categories(message, "nutrition_plan", "🥗 Планы питания", is_callback=False)


@router.message(F.text == "💪 Программы тренировок")
async def text_workout_program(message: types.Message):
    await show_content_categories(message, "workout_program", "💪 Программы тренировок", is_callback=False)


@router.message(F.text == "🎬 Обучающие видео")
async def text_training_video(message: types.Message):
    await show_content_categories(message, "training_video", "🎬 Обучающие видео", is_callback=False)


@router.message(F.text == "📦 Мои покупки")
async def text_my_purchases(message: types.Message):
    user = await db.get_user_by_telegram(message.from_user.id)
    if not user:
        await message.answer("Пользователь не найден")
        return
    purchases = await db.get_user_purchases(user['id'])
    if not purchases:
        await message.answer("📦 У вас пока нет покупок.")
        return
    builder = types.InlineKeyboardMarkup(inline_keyboard=[])
    for p in purchases:
        builder.inline_keyboard.append([
            types.InlineKeyboardButton(
                text=f"{p['title']}",
                callback_data=f"content:view:{p['id']}"
            )
        ])
    builder.inline_keyboard.append([
        types.InlineKeyboardButton(text="◀️ Назад", callback_data="menu:back")
    ])
    await message.answer("📦 Ваши покупки:", reply_markup=builder)


@router.message(F.text == "🔧 Админ-панель")
async def text_admin_panel(message: types.Message):
    if not await db.is_admin(message.from_user.id):
        await message.answer("❌ У вас нет прав администратора.")
        return
    await message.answer(
        "🔧 Админ-панель",
        reply_markup=admin_panel_keyboard()
    )


async def show_my_purchases(callback: types.CallbackQuery):
    user = await db.get_user_by_telegram(callback.from_user.id)
    if not user:
        await callback.answer("Пользователь не найден", show_alert=True)
        return
    purchases = await db.get_user_purchases(user['id'])
    if not purchases:
        await callback.message.edit_text("📦 У вас пока нет покупок.")
        await callback.answer()
        return
    builder = types.InlineKeyboardMarkup(inline_keyboard=[])
    for p in purchases:
        builder.inline_keyboard.append([
            types.InlineKeyboardButton(
                text=f"{p['title']}",
                callback_data=f"content:view:{p['id']}"
            )
        ])
    builder.inline_keyboard.append([
        types.InlineKeyboardButton(text="◀️ Назад", callback_data="menu:back")
    ])
    await callback.message.edit_text("📦 Ваши покупки:", reply_markup=builder)
    await callback.answer()


@router.callback_query(F.data.startswith("category:"))
async def category_callback(callback: types.CallbackQuery):
    """Оптимизированный: один запрос вместо N+1"""
    _, content_type, category = callback.data.split(":", 2)
    user = await db.get_user_by_telegram(callback.from_user.id)
    if not user:
        await callback.answer("Пользователь не найден", show_alert=True)
        return
    
    # Используем оптимизированный запрос с JOIN, который возвращает has_purchased
    contents = await db.get_content_by_filters_with_purchase_status(
        content_type,
        category_name=category,
        user_id=user['id']
    )
    
    if not contents:
        await callback.message.edit_text("В этой категории пока нет материалов.")
        await callback.answer()
        return
    
    # Собираем ID купленных контентов (уже в результате запроса)
    purchased_ids = {c['id'] for c in contents if c.get('has_purchased')}
    
    await callback.message.edit_text(
        f"📂 Результаты по категории:",
        reply_markup=content_list_keyboard(contents, user['id'], purchased_ids)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("content:preview:"))
async def content_preview_callback(callback: types.CallbackQuery):
    """
    Оптимизировано: один запрос вместо трех (get_content_by_id + get_user_by_telegram + has_purchased).
    """
    content_id = int(callback.data.split(":")[2])
    user = await db.get_user_by_telegram(callback.from_user.id)
    if not user:
        await callback.answer("Пользователь не найден", show_alert=True)
        return
    
    # Один запрос: получаем контент + статус покупки
    content = await db.get_content_with_purchase_status(content_id, user['id'])
    if not content:
        await callback.answer("Контент не найден", show_alert=True)
        return
    
    text = f"📌 {content['title']}\n\n{content['description'] or 'Описание отсутствует'}\n\n💰 Цена: {content['price']}⭐️"
    # Получаем telegram_file_id из списка files
    telegram_file_id = None
    if content.get('files') and len(content['files']) > 0:
        telegram_file_id = content['files'][0].get('telegram_file_id')
    
    if content['type'] == 'training_video' and telegram_file_id:
        try:
            await callback.message.answer_video(telegram_file_id, caption=text)
        except Exception as e:
            logger.error(f"Error sending video: {e}")
            await callback.message.edit_text(text, reply_markup=purchase_keyboard(content_id, content['price']))
    else:
        await callback.message.edit_text(text, reply_markup=purchase_keyboard(content_id, content['price']))
    await callback.answer()


@router.callback_query(F.data.startswith("content:view:"))
async def content_view_callback(callback: types.CallbackQuery):
    """
    Оптимизировано: один запрос вместо трех (get_content_by_id + get_user_by_telegram + has_purchased).
    """
    content_id = int(callback.data.split(":")[2])
    user = await db.get_user_by_telegram(callback.from_user.id)
    if not user:
        await callback.answer("Пользователь не найден", show_alert=True)
        return
    
    # Один запрос: получаем контент + статус покупки
    content = await db.get_content_with_purchase_status(content_id, user['id'])
    if not content:
        await callback.answer("Контент не найден", show_alert=True)
        return
    
    has_purchased = content.get('has_purchased', False)
    
    if content['is_paid'] and not has_purchased:
        await callback.message.edit_text(
            f"📌 {content['title']}\n\n{content['description'] or ''}\n\n💰 Цена: {content['price']}⭐️",
            reply_markup=purchase_keyboard(content_id, content['price'])
        )
        await callback.answer()
        return
    text = f"📌 {content['title']}\n\n{content['description'] or 'Описание отсутствует'}"
    await callback.message.edit_text(text, reply_markup=content_view_keyboard(
        content_id, content['type'], content['is_paid'], has_purchased
    ))
    await callback.answer()


@router.callback_query(F.data.startswith("content:watch:"))
async def content_watch_callback(callback: types.CallbackQuery):
    content_id = int(callback.data.split(":")[2])
    content = await db.get_content_by_id(content_id)
    if not content:
        await callback.answer("Контент не найден", show_alert=True)
        return
    telegram_file_id = None
    if content.get('files') and len(content['files']) > 0:
        telegram_file_id = content['files'][0].get('telegram_file_id')
    if not telegram_file_id:
        await callback.answer("Видео не найдено", show_alert=True)
        return
    await callback.message.answer_video(telegram_file_id, caption=content['title'])
    await callback.answer()


@router.callback_query(F.data.startswith("content:download:"))
async def content_download_callback(callback: types.CallbackQuery):
    content_id = int(callback.data.split(":")[2])
    content = await db.get_content_by_id(content_id)
    if not content:
        await callback.answer("Контент не найден", show_alert=True)
        return
    telegram_file_id = None
    mime_type = None
    if content.get('files') and len(content['files']) > 0:
        telegram_file_id = content['files'][0].get('telegram_file_id')
        mime_type = content['files'][0].get('mime_type')
    if not telegram_file_id:
        await callback.answer("Файл не найден", show_alert=True)
        return
    # Отправляем файл напрямую через file_id
    await callback.message.answer_document(telegram_file_id, caption=content['title'])
    await callback.answer()


@router.callback_query(F.data.startswith("content:buy:"))
async def content_buy_callback(callback: types.CallbackQuery):
    content_id = int(callback.data.split(":")[2])
    content = await db.get_content_by_id(content_id)
    if not content:
        await callback.answer("Контент не найден", show_alert=True)
        return
    user = await db.get_user_by_telegram(callback.from_user.id)
    if await db.has_purchased(user['id'], content_id):
        await callback.answer("Вы уже купили этот контент", show_alert=True)
        return
    prices = [LabeledPrice(label=content['title'], amount=content['price'])]
    await callback.bot.send_invoice(
        chat_id=callback.from_user.id,
        title=content['title'],
        description=content['description'] or content['title'],
        payload=f"content_buy:{content_id}:{user['id']}",
        provider_token="",
        currency=CURRENCY_SYMBOL,
        prices=prices
    )
    await callback.answer()


@router.pre_checkout_query()
async def pre_checkout_handler(pre_checkout_query: types.PreCheckoutQuery):
    await pre_checkout_query.answer(ok=True)


@router.message(F.successful_payment)
async def successful_payment(message: types.Message):
    payload = message.successful_payment.invoice_payload
    try:
        _, content_id_str, user_id_str = payload.split(":")
        content_id = int(content_id_str)
        user_id = int(user_id_str)
        await db.add_purchase(user_id, content_id)
        user = await db.get_user_by_id(user_id)
        user_role = user['role'] if user else 'user'
        content = await db.get_content_by_id(content_id)
        await message.answer(
            f"✅ Оплата прошла успешно!\n\n"
            f"📌 {content['title']}\n\n{content['description'] or ''}",
            reply_markup=content_view_keyboard(content_id, content['type'], True, True)
        )
        # Отправляем новое сообщение с reply-клавиатурой
        await message.answer(
            "Вы можете скачать файл или вернуться в главное меню:",
            reply_markup=get_main_menu_reply(user_role)
        )
    except Exception as e:
        logger.error(f"Error processing payment: {e}")
        await message.answer("Произошла ошибка при обработке платежа. Обратитесь к администратору.")


# ==================== ADMIN HANDLERS ====================

@router.callback_query(F.data == "admin:panel")
async def admin_panel_callback(callback: types.CallbackQuery):
    if not await db.is_admin(callback.from_user.id):
        await callback.answer("Нет прав", show_alert=True)
        return
    await callback.message.edit_text("🔧 Админ-панель", reply_markup=admin_panel_keyboard())
    await callback.answer()


@router.callback_query(F.data == "admin:upload")
async def admin_upload_callback(callback: types.CallbackQuery, state: FSMContext):
    if not await db.is_admin(callback.from_user.id):
        await callback.answer("Нет прав", show_alert=True)
        return
    await state.set_state(AdminUploadState.waiting_for_type)
    await callback.message.edit_text("Выберите тип контента:", reply_markup=admin_upload_type_keyboard())
    await callback.answer()


@router.callback_query(F.data.startswith("admin:type:"))
async def admin_type_callback(callback: types.CallbackQuery, state: FSMContext):
    content_type = callback.data.split(":")[2]
    await state.update_data(content_type=content_type)
    await state.set_state(AdminUploadState.waiting_for_title)
    await callback.message.answer("Введите заголовок:", reply_markup=ReplyKeyboardRemove())
    await callback.answer()


@router.message(AdminUploadState.waiting_for_title)
async def admin_title_handler(message: types.Message, state: FSMContext):
    """Валидация заголовка: не пустой, не длиннее 200 символов"""
    title = message.text.strip()
    if not title:
        await message.answer("❌ Заголовок не может быть пустым. Введите заново:")
        return
    if len(title) > 200:
        await message.answer("❌ Заголовок слишком длинный (макс. 200 символов). Введите заново:")
        return
    
    await state.update_data(title=title)
    await state.set_state(AdminUploadState.waiting_for_description)
    await message.answer("Введите описание:", reply_markup=ReplyKeyboardRemove())


@router.message(AdminUploadState.waiting_for_description)
async def admin_description_handler(message: types.Message, state: FSMContext):
    """Валидация описания: не длиннее 4000 символов"""
    description = message.text.strip()
    if len(description) > 4000:
        await message.answer("❌ Описание слишком длинное (макс. 4000 символов). Введите заново:")
        return
    
    await state.update_data(description=description)
    data = await state.get_data()
    content_type = data.get('content_type', '')
    await state.set_state(AdminUploadState.waiting_for_category)
    # Используем кэшированные категории
    categories = await db.get_content_categories_cached(content_type)
    await message.answer("Выберите категорию:", reply_markup=admin_category_keyboard(content_type, categories))


@router.callback_query(F.data.startswith("admin:category:"))
async def admin_category_callback(callback: types.CallbackQuery, state: FSMContext):
    category = callback.data.split(":")[2]
    await state.update_data(category=category)
    await state.set_state(AdminUploadState.waiting_for_price)
    await callback.message.edit_text("Введите цену в звёздах (0 для бесплатного, макс. 10000):")
    await callback.answer()


@router.message(AdminUploadState.waiting_for_price)
async def admin_price_handler(message: types.Message, state: FSMContext):
    """Валидация цены: число от 0 до 10000"""
    try:
        price = int(message.text)
        if price < 0:
            raise ValueError
        if price > 10000:
            await message.answer("❌ Цена слишком высокая (макс. 10000⭐️). Введите заново:")
            return
    except ValueError:
        await message.answer("❌ Введите корректное число (0 или больше):")
        return
    await state.update_data(price=price)
    await state.set_state(AdminUploadState.waiting_for_file)
    await message.answer("Отправьте файл (фото, видео или .xlsx, макс. 50 МБ):")


@router.message(AdminUploadState.waiting_for_file, F.photo | F.video | F.document)
async def admin_file_handler(message: types.Message, state: FSMContext):
    """Обработка загрузки файла с валидацией"""
    data = await state.get_data()
    content_type = data.get('content_type')
    title = data.get('title')
    description = data.get('description')
    category = data.get('category')
    price = data.get('price', 0)
    
    # Получаем file_id и информацию о файле
    telegram_file_id = None
    file_type = 'document'
    file_name = None
    file_size = None
    mime_type = None
    MAX_FILE_SIZE = 50 * 1024 * 1024  # 50 МБ в байтах
    
    if message.photo:
        telegram_file_id = message.photo[-1].file_id
        file_type = 'photo'
        file_size = message.photo[-1].file_size
        if file_size > MAX_FILE_SIZE:
            await message.answer(f"❌ Файл слишком большой (макс. 50 МБ). Ваш размер: {file_size/1024/1024:.1f} МБ")
            return
    elif message.video:
        telegram_file_id = message.video.file_id
        file_type = 'video'
        file_name = f"video_{telegram_file_id}.mp4"
        file_size = message.video.file_size
        mime_type = 'video/mp4'
        if file_size > MAX_FILE_SIZE:
            await message.answer(f"❌ Видео слишком большое (макс. 50 МБ). Ваш размер: {file_size/1024/1024:.1f} МБ")
            return
        # Проверяем разрешение видео (опционально, для оптимизации)
        if message.video.width and message.video.height:
            # Предупреждаем о очень высоком разрешении (может быть тяжелым для просмотра)
            if message.video.width * message.video.height > 1920 * 1080:  # больше Full HD
                await message.answer(
                    f"⚠️ Видео имеет высокое разрешение ({message.video.width}x{message.video.height}). "
                    f"Рекомендуется загружать видео не более 1920x1080 для быстрой загрузки."
                )
    elif message.document:
        telegram_file_id = message.document.file_id
        file_type = 'document'
        file_name = message.document.file_name
        file_size = message.document.file_size
        mime_type = message.document.mime_type
        # Проверяем расширение файла
        from config import ALLOWED_EXTENSIONS
        allowed_exts = ALLOWED_EXTENSIONS.get(content_type, ALLOWED_EXTENSIONS.get('nutrition_plan', []))
        if allowed_exts and not any(file_name.lower().endswith(ext) for ext in allowed_exts):
            await message.answer(f"❌ Недопустимое расширение файла. Разрешены: {', '.join(allowed_exts)}")
            return
        if file_size > MAX_FILE_SIZE:
            await message.answer(f"❌ Файл слишком большой (макс. 50 МБ). Ваш размер: {file_size/1024/1024:.1f} МБ")
            return
    
    if not telegram_file_id:
        await message.answer("Ошибка: не удалось получить файл. Попробуйте еще раз.")
        return
    
    try:
        # Создаём контент
        content_id = await db.add_content(content_type, title, description, price, category)
        # Сохраняем только file_id в БД
        await db.add_content_file(
            content_id,
            telegram_file_id,
            file_type=file_type,
            file_name=file_name,
            file_size=file_size,
            mime_type=mime_type
        )
        
        await state.clear()
        user = await db.get_user_by_telegram(message.from_user.id)
        user_role = user['role'] if user else 'user'
        await message.answer(
            f"✅ Контент загружен!\n\n"
            f"ID: {content_id}\n"
            f"Тип: {content_type}\n"
            f"Заголовок: {title}\n"
            f"Категория: {category}\n"
            f"Цена: {price}⭐️",
            reply_markup=get_main_menu_reply(user_role)
        )
    except Exception as e:
        logger.error(f"Error uploading content: {e}")
        await message.answer("❌ Ошибка при загрузке контента. Попробуйте снова.")


@router.callback_query(F.data == "admin:list")
async def admin_list_callback(callback: types.CallbackQuery):
    """Оптимизированный список контента с пагинацией"""
    if not await db.is_admin(callback.from_user.id):
        await callback.answer("Нет прав", show_alert=True)
        return
    
    # Пагинация: 50 записей на страницу
    limit = 50
    offset = 0
    
    contents = await db.get_all_content_with_details(limit, offset)
    total_count = await db.get_content_count_by_type()
    
    if not contents:
        await callback.message.edit_text("📋 Контент отсутствует.")
        await callback.answer()
        return
    
    text = f"📋 Список контента (показано {len(contents)} из {total_count}):\n\n"
    for c in contents:
        category_name = c.get('category_display_name') or c.get('category_name') or "N/A"
        purchases = c.get('purchase_count', 0)
        text += f"ID:{c['id']} | {c['title'][:30]} | {c['type'][:15]} | {category_name[:15]} | {c['price']}⭐️ | 👁{purchases}\n"
    
    # Добавляем кнопки пагинации если нужно
    markup = admin_content_list_keyboard(contents)
    # Можно добавить кнопки "Вперед/Назад" если записей больше limit
    
    await callback.message.edit_text(text, reply_markup=markup)
    await callback.answer()


@router.callback_query(F.data.startswith("admin:delete:"))
async def admin_delete_callback(callback: types.CallbackQuery):
    content_id = int(callback.data.split(":")[2])
    await callback.message.edit_text(
        f"Вы уверены, что хотите удалить контент ID:{content_id}?",
        reply_markup=confirm_delete_keyboard(content_id)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin:confirm_delete:"))
async def admin_confirm_delete_callback(callback: types.CallbackQuery):
    content_id = int(callback.data.split(":")[2])
    # Удаляем запись из БД (файлы в Telegram удалять не нужно, file_id управляется самим Telegram)
    await db.delete_content(content_id)
    await callback.message.edit_text(f"✅ Контент ID:{content_id} удалён.", reply_markup=admin_panel_keyboard())
    await callback.answer()


@router.message(F.text.in_(["🥗 Планы питания", "💪 Программы тренировок", "🎬 Обучающие видео", "📦 Мои покупки", "🔧 Админ-панель"]), F.state != None)
async def ignore_reply_buttons_during_fsm(message: types.Message):
    # Ignore reply button texts during FSM to prevent interference
    pass
