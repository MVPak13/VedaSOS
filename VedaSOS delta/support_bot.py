import asyncio
import json
import os
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ConversationHandler,
    filters,
    ContextTypes
)
import requests
import logging

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Состояния для ConversationHandler
BRANCH, DESCRIPTION = range(2)

# Конфигурация
TELEGRAM_TOKEN = "ВАШ_ТОКЕН_БОТА"
PYRUS_API_TOKEN = "ВАШ_ТОКЕН_PYRUS"
PYRUS_FORM_ID = "ID_ФОРМЫ_PYRUS"

# Пути к файлам
DATA_DIR = "data"
GROUPS_FILE = os.path.join(DATA_DIR, "groups.json")
USER_SETTINGS_FILE = os.path.join(DATA_DIR, "user_settings.json")
LOCALES_DIR = "locales"


class LocalizationManager:
    """Менеджер локализации"""
    
    def __init__(self):
        self.locales = {}
        self.load_locales()
    
    def load_locales(self):
        """Загрузка всех языковых файлов"""
        for lang in ['RU', 'UZ']:
            locale_file = os.path.join(LOCALES_DIR, f"{lang}.json")
            try:
                with open(locale_file, 'r', encoding='utf-8') as f:
                    self.locales[lang] = json.load(f)
                logger.info(f"Загружена локализация: {lang}")
            except FileNotFoundError:
                logger.error(f"Файл локализации не найден: {locale_file}")
                self.locales[lang] = {}
    
    def get(self, lang, *keys, **kwargs):
        """Получение локализованного текста"""
        try:
            text = self.locales.get(lang, self.locales['RU'])
            for key in keys:
                text = text[key]
            
            # Форматирование с параметрами
            if kwargs:
                return text.format(**kwargs)
            return text
        except (KeyError, TypeError):
            logger.error(f"Ключ локализации не найден: {'.'.join(keys)}")
            return f"[Missing translation: {'.'.join(keys)}]"


class DataManager:
    """Менеджер данных для хранения информации о группах и пользователях"""
    
    def __init__(self):
        self.ensure_data_dir()
        self.groups = self.load_groups()
        self.user_settings = self.load_user_settings()
    
    def ensure_data_dir(self):
        """Создание директории для данных если её нет"""
        if not os.path.exists(DATA_DIR):
            os.makedirs(DATA_DIR)
            logger.info(f"Создана директория для данных: {DATA_DIR}")
    
    def load_groups(self):
        """Загрузка данных о группах"""
        if os.path.exists(GROUPS_FILE):
            try:
                with open(GROUPS_FILE, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except json.JSONDecodeError:
                logger.error(f"Ошибка чтения {GROUPS_FILE}")
                return {}
        return {}
    
    def save_groups(self):
        """Сохранение данных о группах"""
        with open(GROUPS_FILE, 'w', encoding='utf-8') as f:
            json.dump(self.groups, f, ensure_ascii=False, indent=2)
        logger.info("Данные групп сохранены")
    
    def load_user_settings(self):
        """Загрузка настроек пользователей"""
        if os.path.exists(USER_SETTINGS_FILE):
            try:
                with open(USER_SETTINGS_FILE, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except json.JSONDecodeError:
                logger.error(f"Ошибка чтения {USER_SETTINGS_FILE}")
                return {}
        return {}
    
    def save_user_settings(self):
        """Сохранение настроек пользователей"""
        with open(USER_SETTINGS_FILE, 'w', encoding='utf-8') as f:
            json.dump(self.user_settings, f, ensure_ascii=False, indent=2)
        logger.info("Настройки пользователей сохранены")
    
    def add_group(self, chat_id, chat_title):
        """Добавление или обновление группы"""
        chat_id_str = str(chat_id)
        
        if chat_id_str not in self.groups:
            self.groups[chat_id_str] = {
                "id": chat_id,
                "title": chat_title,
                "added_at": datetime.now().isoformat(),
                "last_activity": datetime.now().isoformat()
            }
            logger.info(f"Добавлена новая группа: {chat_title} (ID: {chat_id})")
        else:
            # Обновляем название и время последней активности
            self.groups[chat_id_str]["title"] = chat_title
            self.groups[chat_id_str]["last_activity"] = datetime.now().isoformat()
        
        self.save_groups()
    
    def get_user_language(self, user_id):
        """Получение языка пользователя"""
        user_id_str = str(user_id)
        return self.user_settings.get(user_id_str, {}).get("language", "RU")
    
    def set_user_language(self, user_id, language):
        """Установка языка пользователя"""
        user_id_str = str(user_id)
        
        if user_id_str not in self.user_settings:
            self.user_settings[user_id_str] = {}
        
        self.user_settings[user_id_str]["language"] = language
        self.save_user_settings()
        logger.info(f"Язык пользователя {user_id} изменен на {language}")


class SupportBot:
    """Основной класс бота техподдержки"""
    
    def __init__(self):
        self.user_data = {}
        self.localization = LocalizationManager()
        self.data_manager = DataManager()
    
    def get_text(self, user_id, *keys, **kwargs):
        """Получение локализованного текста для пользователя"""
        lang = self.data_manager.get_user_language(user_id)
        return self.localization.get(lang, *keys, **kwargs)
    
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Приветственное сообщение при добавлении в группу"""
        chat = update.effective_chat
        user_id = update.effective_user.id
        
        if chat.type in ['group', 'supergroup']:
            # Сохраняем информацию о группе
            self.data_manager.add_group(chat.id, chat.title)
            
            welcome_message = (
                f"{self.get_text(user_id, 'welcome', 'title')}\n\n"
                f"{self.get_text(user_id, 'welcome', 'description')}\n\n"
                f"{self.get_text(user_id, 'welcome', 'features')}\n\n"
                f"{self.get_text(user_id, 'welcome', 'commands')}\n\n"
                f"{self.get_text(user_id, 'welcome', 'warning')}"
            )
            
            # Кнопка выбора языка
            keyboard = [
                [InlineKeyboardButton(
                    self.get_text(user_id, 'menu', 'select_language'),
                    callback_data='select_language'
                )]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text(welcome_message, reply_markup=reply_markup)
            await update.message.reply_text(
                self.get_text(user_id, 'ticket', 'group_saved')
            )
        else:
            await update.message.reply_text(
                self.get_text(user_id, 'errors', 'group_only')
            )
    
    async def language_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда выбора языка"""
        await self.show_language_selection(update, update.effective_user.id)
    
    async def show_language_selection(self, update: Update, user_id: int):
        """Показать меню выбора языка"""
        keyboard = [
            [
                InlineKeyboardButton("🇷🇺 Русский", callback_data='lang_RU'),
                InlineKeyboardButton("🇺🇿 O'zbekcha", callback_data='lang_UZ')
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        text = self.localization.get('RU', 'language', 'select')
        
        if update.callback_query:
            await update.callback_query.edit_message_text(
                text=text,
                reply_markup=reply_markup
            )
        else:
            await update.message.reply_text(text, reply_markup=reply_markup)
    
    async def language_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка выбора языка"""
        query = update.callback_query
        await query.answer()
        
        user_id = update.effective_user.id
        
        if query.data == 'select_language':
            await self.show_language_selection(update, user_id)
        elif query.data.startswith('lang_'):
            language = query.data.split('_')[1]
            self.data_manager.set_user_language(user_id, language)
            
            await query.edit_message_text(
                self.get_text(user_id, 'language', 'changed')
            )
    
    async def sos_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Начало процесса создания заявки"""
        user_id = update.effective_user.id
        chat = update.effective_chat
        
        # Проверяем, что команда вызвана в группе
        if chat.type not in ['group', 'supergroup']:
            await update.message.reply_text(
                self.get_text(user_id, 'errors', 'group_only')
            )
            return ConversationHandler.END
        
        # Обновляем информацию о группе
        self.data_manager.add_group(chat.id, chat.title)
        
        # Сохраняем название группы
        group_name = chat.title
        self.user_data[user_id] = {
            'group_name': group_name,
            'group_id': chat.id,
            'user_name': update.effective_user.full_name
        }
        
        # Создаём кнопку "Нет филиала"
        keyboard = [[
            InlineKeyboardButton(
                self.get_text(user_id, 'ticket', 'no_branch'),
                callback_data='no_branch'
            )
        ]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            self.get_text(user_id, 'ticket', 'enter_branch_name'),
            reply_markup=reply_markup
        )
        
        return BRANCH
    
    async def receive_branch(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Получение филиала от пользователя"""
        user_id = update.effective_user.id
        branch = update.message.text.strip()
        
        if not branch:
            await update.message.reply_text(
                self.get_text(user_id, 'errors', 'empty_branch')
            )
            return BRANCH
        
        # Сохраняем филиал
        if user_id in self.user_data:
            self.user_data[user_id]['branch'] = branch
            
            await update.message.reply_text(
                self.get_text(user_id, 'ticket', 'describe_problem')
            )
            return DESCRIPTION
        else:
            await update.message.reply_text(
                self.get_text(user_id, 'errors', 'general_error')
            )
            return ConversationHandler.END
    
    async def no_branch_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка нажатия кнопки 'Нет филиала'"""
        query = update.callback_query
        await query.answer()
        
        user_id = update.effective_user.id
        
        if user_id in self.user_data:
            self.user_data[user_id]['branch'] = 'Не указан'
            
            await query.edit_message_text(
                self.get_text(user_id, 'ticket', 'describe_problem')
            )
        else:
            await query.edit_message_text(
                self.get_text(user_id, 'errors', 'general_error')
            )
    
    async def receive_description(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Получение описания проблемы"""
        user_id = update.effective_user.id
        description = update.message.text.strip()
        
        if not description:
            await update.message.reply_text(
                self.get_text(user_id, 'errors', 'empty_description')
            )
            return DESCRIPTION
        
        if user_id not in self.user_data:
            await update.message.reply_text(
                self.get_text(user_id, 'errors', 'general_error')
            )
            return ConversationHandler.END
        
        # Сохраняем описание
        self.user_data[user_id]['description'] = description
        
        # Показываем подтверждение
        data = self.user_data[user_id]
        summary = self.get_text(
            user_id,
            'ticket',
            'confirm_details',
            user_name=data['user_name'],
            group_name=data['group_name'],
            branch=data['branch'],
            description=data['description']
        )
        
        # Кнопки подтверждения
        keyboard = [
            [InlineKeyboardButton(
                self.get_text(user_id, 'ticket', 'btn_confirm'),
                callback_data='confirm_ticket'
            )],
            [InlineKeyboardButton(
                self.get_text(user_id, 'ticket', 'btn_cancel'),
                callback_data='cancel_ticket'
            )]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            f"{self.get_text(user_id, 'ticket', 'confirm_title')}\n\n{summary}",
            reply_markup=reply_markup
        )
        
        return ConversationHandler.END
    
    async def confirm_ticket_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка подтверждения заявки"""
        query = update.callback_query
        await query.answer()
        
        user_id = update.effective_user.id
        
        try:
            if query.data == 'confirm_ticket':
                if user_id in self.user_data:
                    data = self.user_data[user_id]
                    
                    # Отправляем заявку в Pyrus
                    success = await self.send_to_pyrus(data)
                    
                    if success:
                        await query.edit_message_text(
                            self.get_text(user_id, 'ticket', 'created')
                        )
                    else:
                        await query.edit_message_text(
                            self.get_text(user_id, 'errors', 'pyrus_error')
                        )
                    
                    # Очищаем данные пользователя
                    del self.user_data[user_id]
                else:
                    await query.edit_message_text(
                        self.get_text(user_id, 'errors', 'general_error')
                    )
            
            elif query.data == 'cancel_ticket':
                if user_id in self.user_data:
                    del self.user_data[user_id]
                
                await query.edit_message_text(
                    self.get_text(user_id, 'ticket', 'cancelled')
                )
        except Exception as e:
            logger.error(f"Ошибка при обработке callback заявки: {e}")
            await query.edit_message_text(
                self.get_text(user_id, 'errors', 'general_error')
            )
    
    async def send_to_pyrus(self, data):
        """Отправка заявки в Pyrus"""
        try:
            url = "https://api.pyrus.com/v4/tasks"
            
            headers = {
                "Authorization": f"Bearer {PYRUS_API_TOKEN}",
                "Content-Type": "application/json"
            }
            
            # Формируем тело запроса для Pyrus
            payload = {
                "form_id": PYRUS_FORM_ID,
                "text": f"Новая заявка от {data['user_name']} из группы {data['group_name']}",
                "fields": [
                    {"id": 1, "value": data['group_name']},      # Поле "Группа"
                    {"id": 2, "value": data['branch']},          # Поле "Филиал"
                    {"id": 3, "value": data['description']}      # Поле "Описание"
                ]
            }
            
            # Отправляем запрос
            response = requests.post(url, json=payload, headers=headers, timeout=10)
            
            if response.status_code == 200:
                logger.info(f"Заявка успешно отправлена в Pyrus: {data}")
                return True
            else:
                logger.error(f"Ошибка Pyrus API: {response.status_code} - {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"Ошибка при отправке в Pyrus: {e}")
            return False
    
    async def cancel(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Отмена создания заявки"""
        user_id = update.effective_user.id
        
        if user_id in self.user_data:
            del self.user_data[user_id]
        
        await update.message.reply_text(
            self.get_text(user_id, 'ticket', 'cancelled')
        )
        return ConversationHandler.END
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда помощи"""
        user_id = update.effective_user.id
        await update.message.reply_text(
            self.get_text(user_id, 'help', 'text')
        )


def main():
    """Запуск бота"""
    # Проверяем, что токены заполнены
    if TELEGRAM_TOKEN == "ВАШ_ТОКЕН_БОТА":
        logger.error("❌ ОШИБКА: Заполните TELEGRAM_TOKEN в коде!")
        return
    
    if PYRUS_API_TOKEN == "ВАШ_ТОКЕН_PYRUS":
        logger.warning("⚠️ ВНИМАНИЕ: Заполните PYRUS_API_TOKEN для отправки заявок в Pyrus")
    
    if PYRUS_FORM_ID == "ID_ФОРМЫ_PYRUS":
        logger.warning("⚠️ ВНИМАНИЕ: Заполните PYRUS_FORM_ID для корректной работы")
    
    # Создаём экземпляр бота
    bot = SupportBot()
    
    # Создаём приложение
    application = Application.builder().token(TELEGRAM_TOKEN).build()
    
    # Обработчик диалога для создания заявки
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('SOS', bot.sos_command)],
        states={
            BRANCH: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, bot.receive_branch),
                CallbackQueryHandler(bot.no_branch_callback, pattern='^no_branch$')
            ],
            DESCRIPTION: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, bot.receive_description)
            ],
        },
        fallbacks=[CommandHandler('cancel', bot.cancel)],
    )
    
    # Добавляем обработчики в правильном порядке
    application.add_handler(CommandHandler('start', bot.start))
    application.add_handler(CommandHandler('language', bot.language_command))
    application.add_handler(CommandHandler('help', bot.help_command))
    
    # Обработчик callback кнопок перед ConversationHandler
    application.add_handler(CallbackQueryHandler(
        bot.language_callback,
        pattern='^(select_language|lang_)'
    ))
    application.add_handler(CallbackQueryHandler(
        bot.confirm_ticket_callback,
        pattern='^(confirm_ticket|cancel_ticket)$'
    ))
    
    # Обработчик диалога добавляем последним
    application.add_handler(conv_handler)
    
    # Запускаем бота
    logger.info("✅ Бот запущен!")
    try:
        application.run_polling(allowed_updates=Update.ALL_TYPES)
    except KeyboardInterrupt:
        logger.info("Бот остановлен пользователем")
    except Exception as e:
        logger.error(f"Критическая ошибка: {e}")


if __name__ == '__main__':
    main()
