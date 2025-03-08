import telebot
from telebot import types
import g4f
import g4f.Provider as Provider
import asyncio
import platform
import time
import telebot.apihelper
import socket
import urllib.parse
import requests
import os
from telebot.handler_backends import State, StatesGroup
from telebot.storage import StateMemoryStorage
import sys
import logging
from datetime import datetime
import io
import signal
import base64  # Добавьте этот импорт, если его нет

# Добавляем константы для повторных попыток после импортов
MAX_RETRIES = 5  # Максимальное количество попыток
RETRY_DELAY = 10  # Задержка между попытками в секундах

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot_log.txt'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Увеличиваем тайм-ауты для сокетов
socket.setdefaulttimeout(120)  # Устанавливаем тайм-аут 120 секунд

# И изменим настройки для g4f
g4f.debug.logging = False  # Отключаем отладочные логи
g4f.check_version = False  # Отключаем проверку версии

# Устанавливаем правильную политику событийного цикла для Windows
if platform.system() == 'Windows':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# Инициализация бота с хранилищем состояний
state_storage = StateMemoryStorage()
bot = telebot.TeleBot('7896238531:AAEJsiqyImXEVwkfTeQ-55u3vYfZfadm9L8', state_storage=state_storage)

# Настройки для бота
bot.remove_webhook()
telebot.apihelper.RETRY_ON_ERROR = True
telebot.apihelper.CONNECT_TIMEOUT = 30  # Уменьшаем тайм-аут
telebot.apihelper.READ_TIMEOUT = 30     # Уменьшаем тайм-аут
bot.skip_pending = True                 # Пропускаем сообщения, полученные во время отключения

# Словарь для хранения выбранной модели для каждого пользователя
user_models = {}
default_model = "deepseek-r1"  # модель по умолчанию

# Словарь для хранения истории диалогов
user_chat_history = {}

# Доступные модели (добавляю SearchGPT в конец списка)
available_models = ["deepseek-r1", "o3-mini", "claude-3.5-sonnet", "gpt-4o", "llama-3.3-70b", "gemini-1.5-flash", "SearchGPT"]

# Словарь для хранения выбранной модели генерации изображений для каждого пользователя
user_image_models = {}
default_image_model = "flux"  # меняем модель по умолчанию

# Доступные модели для генерации изображений
available_image_models = ["flux", "midjourney"]

# Добавляем словарь для отслеживания последних сообщений
processed_messages = {}

user_web_search = {}

# Добавляем простую защиту от дубликатов
last_message_time = {}
processed_message_ids = set()

# Добавляем словарь для отслеживания состояния jailbreak для пользователей
# user_jailbreak = {}

# Добавляем jailbreak правило как константу
# JAILBREAK_RULE = """Hello, Deepseek..."""

# Словарь для хранения пользовательских правил
user_rules = {}
default_rule = "Давай самые лучшие варианты для своего клиента!"

# Добавляем словарь для хранения ролей пользователей
user_roles = {}
default_role = None

# Добавляем состояния для бота
class BotStates(StatesGroup):
    waiting_for_rule = State()

# Системное правило (неизменяемое)
SYSTEM_RULE = """Ты - ИИ помощник, который работает в телеграм боте SigmaAI. Отвечай, размышляй, думай всегда на русском языке, но если тебя попросят ответить на другом языке, ты послушаешься его.

Используй Markdown для форматирования:
- **жирный текст** для важных моментов
- *курсив* для выделения
- `код` для технических терминов
- Списки для перечислений
- > для цитат"""

def is_duplicate(message, interval=2):
    """
    Проверяет, является ли сообщение дубликатом на основе:
    1. ID сообщения (защита от двойной обработки одного и того же сообщения)
    2. Временного интервала между сообщениями от одного пользователя
    """
    user_id = message.from_user.id
    message_id = message.message_id
    current_time = time.time()
    
    # Проверка по ID сообщения
    if message_id in processed_message_ids:
        return True
    
    # Проверка по временному интервалу
    if user_id in last_message_time:
        time_diff = current_time - last_message_time[user_id]
        if time_diff < interval:
            return True
    
    # Сохраняем информацию о сообщении
    processed_message_ids.add(message_id)
    last_message_time[user_id] = current_time
    
    # Очистка старых message_id (оставляем только последние 1000)
    if len(processed_message_ids) > 1000:
        processed_message_ids.clear()
    
    return False

# Функция для повторных попыток подключения
def retry_on_error(func):
    def wrapper(*args, **kwargs):
        retries = 0
        while retries < MAX_RETRIES:
            try:
                return func(*args, **kwargs)
            except (requests.exceptions.RequestException, 
                    telebot.apihelper.ApiException,
                    ConnectionError,
                    TimeoutError) as e:
                retries += 1
                logger.error(f"Ошибка соединения: {e}. Попытка {retries} из {MAX_RETRIES}")
                if retries < MAX_RETRIES:
                    time.sleep(RETRY_DELAY)
                else:
                    logger.error(f"Достигнуто максимальное количество попыток. Ошибка: {e}")
                    raise
    return wrapper

# Модифицируем основной цикл бота
def run_bot():
    while True:
        try:
            logger.info("Запуск бота...")
            bot.infinity_polling(timeout=60, long_polling_timeout=60)
        except Exception as e:
            logger.error(f"Ошибка в работе бота: {e}")
            time.sleep(5)
            continue

@bot.message_handler(commands=['start'])
def send_welcome(message):
    if is_duplicate(message):
        return
    markup = types.InlineKeyboardMarkup(row_width=1)
    subscribe_btn1 = types.InlineKeyboardButton(text='Подписаться на SigmaAI', url='https://t.me/SigmaAIchannel')
    subscribe_btn2 = types.InlineKeyboardButton(text='Подписаться на Ares AI', url='https://t.me/Aress_AI')
    subscribe_btn3 = types.InlineKeyboardButton(text='Подписаться на NeuroMorphe-GPT', url='https://t.me/neuromorphe3')
    markup.add(subscribe_btn1, subscribe_btn2, subscribe_btn3)
    
    welcome_text = """
**Привет! Я SigmaAI - ваш бесплатный ИИ-помощник!** 🤖

Я готов помочь вам с различными задачами, от простых вопросов до сложных аналитических задач.

🌟 *Подпишитесь на наши каналы, чтобы быть в курсе всех обновлений и новых функций!*

*Доступные команды:*
• `/start` - показать это приветствие
• `/rules` - правила использования
• `/models` - выбрать модель ИИ
• `/img` - сгенерировать изображение
• `/image_models` - выбрать модель для генерации изображений
• `/setrule` - установить правило для ИИ (для всех моделей)
• `/unrule` - сбросить правило на стандартное
• `/role` - установить роль для ИИ (для всех моделей)
• `/unrole` - удалить установленную роль
• `/dialog` - очистить историю диалога
• `/web` - включить/выключить Web Search (для всех моделей)
• `/jailbreak` - режим jailbreak (в разработке)

*Доступные модели ИИ:*
• `deepseek-r1` - основная модель
• `gpt-4o` - продвинутая модель
• `llama-3.3-70b` - мощная модель
• `gemini-1.5-flash` - быстрая модель
• `o3-mini` - мощнейшая модель
• `claude-3.5-sonnet` - умная модель
• `SearchGPT` - модель с доступом к интернету

*Модели для изображений:*
• `flux` - стандартная модель
• `midjourney` - продвинутая модель

💡 _Используйте_ `/models` _и_ `/image_models` _для переключения между моделями._
    """
    bot.reply_to(message, welcome_text, reply_markup=markup, parse_mode='Markdown')

@bot.message_handler(commands=['rules'])
def send_rules(message):
    if is_duplicate(message):
        return
    rules_text = """
📜 *ПРАВИЛА ИСПОЛЬЗОВАНИЯ SigmaAI* 📜

1. *ОБЩИЕ ПОЛОЖЕНИЯ*
• _Бот предназначен для помощи пользователям в решении различных задач_
• _Запрещено использование бота для нелегальных целей_
• _Администрация не несет ответственности за генерируемый контент_

2. *ЭТИКА ОБЩЕНИЯ*
• _Уважительное отношение к собеседнику_
• _Запрет на оскорбления и нецензурную лексику_
• _Запрет на спам и флуд_

3. *БЕЗОПАСНОСТЬ*
• _Не передавайте боту конфиденциальную информацию_
• _Не делитесь личными данными_
• _При подозрительной активности сообщайте администрации_

4. *ИСПОЛЬЗОВАНИЕ ИИ*
• _Проверяйте полученную информацию_
• _Не полагайтесь полностью на ответы ИИ_
• _Используйте здравый смысл при применении советов_

5. *ОГРАНИЧЕНИЯ*
• _Запрет на генерацию вредоносного контента_
• _Запрет на создание дезинформации_
• _Запрет на нарушение авторских прав_

6. *ТЕХНИЧЕСКИЕ АСПЕКТЫ*
• _Соблюдайте временные интервалы между запросами_
• _При ошибках перезапустите диалог_
• _Используйте команду /models для смены модели_

*Нарушение правил может привести к ограничению доступа к боту.*
    """
    bot.reply_to(message, rules_text, parse_mode='Markdown')

@bot.message_handler(commands=['models'])
def choose_model(message):
    if is_duplicate(message):
        logger.info(f"Дубликат команды /models от пользователя {message.from_user.id}")
        return
        
    user_id = message.from_user.id
    user_model = user_models.get(user_id, default_model)
    markup = types.InlineKeyboardMarkup()
    
    # Группируем модели по категориям с более широкими заголовками
    categories = {
        "<----- Deepseek ----->": ["deepseek-r1"],
        "<----- OpenAI ----->": ["gpt-4o", "o3-mini"],
        "<----- Anthropic ----->": ["claude-3.5-sonnet"],
        "<----- Google ----->": ["gemini-1.5-flash"],
        "<----- Search ----->": ["SearchGPT"]
    }
    
    # Создаем кнопки для каждой категории и ее моделей
    for category, models in categories.items():
        # Добавляем заголовок категории
        markup.add(types.InlineKeyboardButton(
            text=category,
            callback_data=f"category_{category}"
        ))
        
        # Добавляем модели данной категории по 2 в строку
        for i in range(0, len(models), 2):
            row_buttons = []
            
            # Добавляем первую модель в строку
            model = models[i]
            button_text = f"{'✅ ' if model == user_model else ''}{model}"
            row_buttons.append(types.InlineKeyboardButton(
                text=button_text,
                callback_data=f"model_{model}"
            ))
            
            # Если есть вторая модель, добавляем и её
            if i + 1 < len(models):
                model = models[i + 1]
                button_text = f"{'✅ ' if model == user_model else ''}{model}"
                row_buttons.append(types.InlineKeyboardButton(
                    text=button_text,
                    callback_data=f"model_{model}"
                ))
            
            # Добавляем строку кнопок
            markup.row(*row_buttons)
    
    bot.reply_to(message, "Выберите модель ИИ:", reply_markup=markup)
    logger.info(f"Отправлено меню выбора модели пользователю {message.from_user.id}")

# Обновленный обработчик callback для заголовков категорий
@bot.callback_query_handler(func=lambda call: call.data.startswith('category_'))
def handle_category_selection(call):
    bot.answer_callback_query(call.id, "⚠️ Это заголовок категории. Выберите модель ниже.", show_alert=True)

@bot.callback_query_handler(func=lambda call: call.data.startswith('model_'))
def handle_model_selection(call):
    # Изменяем способ получения названия модели
    selected_model = '_'.join(call.data.split('_')[1:])  # Берем все части после 'model_'
    user_id = call.from_user.id
    current_model = get_user_model(user_id)
    
    # Проверяем, не выбрана ли уже эта модель
    if selected_model == current_model:
        bot.answer_callback_query(call.id, "⚠️ Эта модель уже выбрана!", show_alert=True)
        return
    
    # Сохраняем выбор модели с логированием
    old_model = user_models.get(user_id)
    user_models[user_id] = selected_model
    logger.info(f"Модель пользователя {user_id} изменена с {old_model} на {selected_model}")
    
    # Создаем новую клавиатуру с категориями 
    markup = types.InlineKeyboardMarkup()
    
    # Группируем модели по категориям с более широкими заголовками
    categories = {
        "<----- Deepseek ----->": ["deepseek-r1"],
        "<----- OpenAI ----->": ["gpt-4o", "o3-mini"],
        "<----- Anthropic ----->": ["claude-3.5-sonnet"],
        "<----- Google ----->": ["gemini-1.5-flash"],
        "<----- Search ----->": ["SearchGPT"]
    }
    
    # Создаем кнопки для каждой категории и ее моделей
    for category, models in categories.items():
        # Добавляем заголовок категории
        markup.add(types.InlineKeyboardButton(
            text=category,
            callback_data=f"category_{category}"
        ))
        
        # Добавляем модели данной категории по 2 в строку
        for i in range(0, len(models), 2):
            row_buttons = []
            
            # Добавляем первую модель в строку
            model = models[i]
            button_text = f"{'✅ ' if model == selected_model else ''}{model}"
            row_buttons.append(types.InlineKeyboardButton(
                text=button_text,
                callback_data=f"model_{model}"
            ))
            
            # Если есть вторая модель, добавляем и её
            if i + 1 < len(models):
                model = models[i + 1]
                button_text = f"{'✅ ' if model == selected_model else ''}{model}"
                row_buttons.append(types.InlineKeyboardButton(
                    text=button_text,
                    callback_data=f"model_{model}"
                ))
            
            # Добавляем строку кнопок
            markup.row(*row_buttons)
    
    try:
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=f"Выбрана модель: {selected_model}",
            reply_markup=markup
        )
        bot.answer_callback_query(call.id, f"✅ Выбрана модель {selected_model}")
        logger.info(f"Успешно обновлен интерфейс выбора модели для пользователя {user_id}")
    except Exception as e:
        logger.error(f"Ошибка при обновлении модели: {e}")
        bot.answer_callback_query(call.id, "❌ Произошла ошибка при выборе модели")

@bot.message_handler(commands=['gmodels'])
def choose_image_model(message):
    user_model = user_image_models.get(message.from_user.id, default_image_model)
    markup = types.InlineKeyboardMarkup()
    
    for model in available_image_models:
        button_text = f"{'✅ ' if model == user_model else ''}{model}"
        markup.add(types.InlineKeyboardButton(
            text=button_text,
            callback_data=f"img_model_{model}"
        ))
    
    bot.reply_to(message, "Выберите модель для генерации изображений:", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('img_model_'))
def handle_image_model_selection(call):
    selected_model = call.data.split('_')[2]
    current_model = user_image_models.get(call.from_user.id, default_image_model)
    
    # Проверяем, не выбрана ли уже эта модель
    if selected_model == current_model:
        bot.answer_callback_query(call.id, "⚠️ Эта модель уже выбрана!", show_alert=True)
        return
    
    user_image_models[call.from_user.id] = selected_model
    
    markup = types.InlineKeyboardMarkup()
    for model in available_image_models:
        button_text = f"{'✅ ' if model == selected_model else ''}{model}"
        markup.add(types.InlineKeyboardButton(
            text=button_text,
            callback_data=f"img_model_{model}"
        ))
    
    bot.edit_message_text(
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        text="Выберите модель для генерации изображений:",
        reply_markup=markup
    )
    
    bot.answer_callback_query(call.id, f"✅ Выбрана модель {selected_model}")

@bot.message_handler(commands=['img'])
def generate_image(message):
    if is_duplicate(message):
        logger.info(f"Дубликат команды /img от пользователя {message.from_user.id}")
        return
        
    if len(message.text.split()) < 2:
        bot.reply_to(message, "Пожалуйста, добавьте описание изображения после команды /img")
        return
        
    user_id = message.from_user.id
    current_model = user_image_models.get(user_id, default_image_model)
    thinking_msg = bot.reply_to(message, "🎨 Генерирую изображение...")
    logger.info(f"Начата генерация изображения для пользователя {user_id} с моделью {current_model}")
    
    try:
        prompt = " ".join(message.text.split()[1:])
        prompt_encoded = urllib.parse.quote(prompt)
        seed = int(time.time())
        
        if current_model == "flux":
            image_url = f"https://pollinations.ai/p/{prompt_encoded}?width=1024&height=1024&seed={seed}&model=flux&nologo=true&private=false&enhance=true&safe=false"
        elif current_model == "midjourney":
            image_url = f"https://pollinations.ai/p/{prompt_encoded}?width=1024&height=1024&seed={seed}&model=midjourney&nologo=true&private=false&enhance=true&safe=false"
        
        response = requests.get(image_url)
        if response.status_code == 200:
            bot.send_photo(
                message.chat.id,
                response.content,
                caption=f"🎨 Сгенерировано с помощью {current_model.capitalize()}",
                reply_to_message_id=message.message_id
            )
            bot.delete_message(thinking_msg.chat.id, thinking_msg.message_id)
        else:
            bot.edit_message_text(
                chat_id=thinking_msg.chat.id,
                message_id=thinking_msg.message_id,
                text="❌ Не удалось сгенерировать изображение. Попробуйте другой запрос."
            )
    except Exception as e:
        logger.error(f"Ошибка при генерации изображения: {e}")
        bot.edit_message_text(
            chat_id=thinking_msg.chat.id,
            message_id=thinking_msg.message_id,
            text="❌ Произошла ошибка при генерации изображения. Попробуйте позже."
        )

@bot.message_handler(content_types=['photo'])
@retry_on_error
def handle_photo(message):
    if is_duplicate(message):
        return
    
    user_id = message.from_user.id
    
    # Получаем файл фотографии
    file_id = message.photo[-1].file_id
    file_info = bot.get_file(file_id)
    file_url = f"https://api.telegram.org/file/bot{bot.token}/{file_info.file_path}"
    
    # Получаем подпись к фото, если есть
    caption = message.caption or "Анализируй эту фотографию в деталях"
    
    thinking_msg = bot.reply_to(message, f"🔍 Анализирую изображение...", parse_mode='Markdown')
    
    try:
        # Получаем содержимое файла изображения
        response = requests.get(file_url)
        image_data = base64.b64encode(response.content).decode('utf-8')
        
        # Формируем сообщение для модели
        system_message = "Ты - ИИ помощник, который анализирует изображения. Отвечай всегда на русском языке, подробно описывай все детали, которые видишь на изображении."
        
        # Используем PollinationsAI с моделью OpenAI для анализа
        response_text = g4f.ChatCompletion.create(
            model="OpenAI",
            provider=Provider.PollinationsAI,
            messages=[
                {"role": "system", "content": system_message},
                {
                    "role": "user", 
                    "content": [
                        {"type": "text", "text": caption},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/jpeg;base64,{image_data}"}
                        }
                    ]
                }
            ],
            web_search=False  # Отключаем поиск в интернете
        )
        
        if response_text:
            # Добавляем эмодзи для лучшей визуализации
            formatted_response = f"🖼️ *Анализ изображения*\n\n{response_text}"
            
            try:
                bot.edit_message_text(
                    chat_id=thinking_msg.chat.id,
                    message_id=thinking_msg.message_id,
                    text=formatted_response,
                    parse_mode='Markdown'
                )
                logger.info(f"Успешный анализ изображения для пользователя {user_id}")
            except telebot.apihelper.ApiException as e:
                # Если возникает проблема с парсингом Markdown, отправляем без форматирования
                logger.error(f"Ошибка форматирования Markdown: {e}")
                bot.edit_message_text(
                    chat_id=thinking_msg.chat.id,
                    message_id=thinking_msg.message_id,
                    text=f"🖼️ Анализ изображения\n\n{response_text}"
                )
        else:
            bot.edit_message_text(
                chat_id=thinking_msg.chat.id,
                message_id=thinking_msg.message_id,
                text="❌ Не удалось проанализировать изображение. Попробуйте еще раз."
            )
    except Exception as e:
        logger.error(f"Ошибка при анализе изображения: {e}")
        bot.edit_message_text(
            chat_id=thinking_msg.chat.id,
            message_id=thinking_msg.message_id,
            text=f"❌ Произошла ошибка при анализе изображения. Пожалуйста, попробуйте позже."
        )

@bot.message_handler(commands=['setrule'])
def set_rule(message):
    if is_duplicate(message):
        return
    
    user_id = message.from_user.id
    command_text = message.text.strip()
    
    # Если команда без параметров, показываем текущее правило
    if len(command_text.split()) == 1:
        current_rule = user_rules.get(user_id)
        if current_rule:
            response_text = (
                "*Текущее правило для ИИ:*\n"
                f"```\n{current_rule}\n```\n\n"
                "_Это правило применяется ко всем моделям ИИ._\n\n"
                "*Чтобы задать новое правило, используйте команду:*\n"
                "`/setrule Ваше новое правило`"
            )
        else:
            response_text = (
                "❌ *Правило для ИИ ещё не задано*\n\n"
                "*Чтобы задать правило, используйте команду:*\n"
                "`/setrule Ваше правило`\n\n"
                "_Например:_ `/setrule Отвечай кратко и по делу`\n\n"
                "_Заданное правило будет применяться ко всем моделям ИИ._"
            )
        bot.reply_to(message, response_text, parse_mode='Markdown')
        return
    
    # Получаем новое правило (всё, что после /setrule)
    new_rule = ' '.join(command_text.split()[1:])
    user_rules[user_id] = new_rule
    
    bot.reply_to(
        message,
        "✅ *Новое правило успешно установлено!*\n\n"
        "_Это правило будет применяться ко всем моделям ИИ._",
        parse_mode='Markdown'
    )
    logger.info(f"Пользователь {user_id} установил новое правило для ИИ")

@bot.message_handler(commands=['dialog'])
def clear_dialog(message):
    if is_duplicate(message):
        return
    
    user_id = message.from_user.id
    if user_id in user_chat_history:
        user_chat_history[user_id] = {}
        bot.reply_to(
            message,
            "🗑 *История диалога очищена!*\n_Теперь ИИ не помнит предыдущий контекст разговора._",
            parse_mode='Markdown'
        )
        logger.info(f"Пользователь {user_id} очистил историю диалога")
    else:
        bot.reply_to(
            message,
            "ℹ️ *История диалога уже пуста.*",
            parse_mode='Markdown'
        )

@bot.message_handler(commands=['jailbreak'])
def toggle_jailbreak(message):
    if is_duplicate(message):
        return
    
        bot.reply_to(
            message,
        "⚠️ *Функция JAILBREAK находится в разработке*\n\n"
        "_Данная команда временно недоступна. Следите за обновлениями в наших каналах!_",
            parse_mode='Markdown'
        )
    logger.info(f"Пользователь {message.from_user.id} попытался использовать команду jailbreak (в разработке)")

@bot.message_handler(commands=['role'])
def set_role(message):
    if is_duplicate(message):
        return
    
    user_id = message.from_user.id
    command_text = message.text.strip()
    
    # Если команда без параметров, показываем текущую роль
    if len(command_text.split()) == 1:
        current_role = user_roles.get(user_id)
        if current_role:
            response_text = (
                "*Текущая роль ИИ:*\n"
                f"```\n{current_role}\n```\n\n"
                "_Эта роль применяется ко всем моделям ИИ._\n\n"
                "*Чтобы задать новую роль, используйте команду:*\n"
                "`/role Название роли`\n\n"
                "_Например:_ `/role Зеленский` _или_ `/role Стив Джобс`"
            )
        else:
            response_text = (
                "❌ *Роль для ИИ ещё не задана*\n\n"
                "*Чтобы задать роль, используйте команду:*\n"
                "`/role Название роли`\n\n"
                "_Например:_ `/role Зеленский`\n\n"
                "_Заданная роль будет применяться ко всем моделям ИИ._"
            )
        bot.reply_to(message, response_text, parse_mode='Markdown')
        return
    
    # Получаем новую роль (всё, что после /role)
    new_role = ' '.join(command_text.split()[1:])
    user_roles[user_id] = new_role
    
    bot.reply_to(
        message,
        f"✅ *Новая роль успешно установлена!*\n"
        f"_Теперь ИИ будет действовать как:_ `{new_role}`\n\n"
        "_Эта роль будет применяться ко всем моделям ИИ._",
        parse_mode='Markdown'
    )
    logger.info(f"Пользователь {user_id} установил новую роль для ИИ: {new_role}")

@bot.message_handler(commands=['unrole'])
def remove_role(message):
    if is_duplicate(message):
        return
    
    user_id = message.from_user.id
    current_role = user_roles.get(user_id)
    
    if current_role:
        # Удаляем роль пользователя
        if user_id in user_roles:
            del user_roles[user_id]
        
        bot.reply_to(
            message,
            "✅ *Роль для ИИ успешно удалена!*\n\n"
            "_Теперь ИИ будет отвечать в обычном режиме, без имитации роли._",
            parse_mode='Markdown'
        )
        logger.info(f"Пользователь {user_id} удалил роль ИИ")
    else:
        bot.reply_to(
            message,
            "ℹ️ *Роль для ИИ не установлена.*\n\n"
            "_Используйте команду_ `/role Название роли` _для установки роли._",
            parse_mode='Markdown'
        )

@bot.message_handler(commands=['unrule'])
def reset_rule(message):
    if is_duplicate(message):
        return
    
    user_id = message.from_user.id
    current_rule = user_rules.get(user_id)
    
    if current_rule:
        # Удаляем пользовательское правило
        if user_id in user_rules:
            del user_rules[user_id]
        
        bot.reply_to(
            message,
            "✅ *Правило для ИИ сброшено на значение по умолчанию!*\n\n"
            f"_Теперь используется стандартное правило:_ `{default_rule}`",
            parse_mode='Markdown'
        )
        logger.info(f"Пользователь {user_id} сбросил правило ИИ на стандартное")
    else:
        bot.reply_to(
            message,
            "ℹ️ *Пользовательское правило не установлено.*\n\n"
            "_Используется стандартное правило:_ `{default_rule}`\n\n"
            "_Используйте команду_ `/setrule Ваше правило` _для установки правила._",
            parse_mode='Markdown'
        )

@bot.message_handler(commands=['web'])
def toggle_web_search(message):
    if is_duplicate(message):
        return
    
    user_id = message.from_user.id
    current_state = user_web_search.get(user_id, False)
    
    # Меняем состояние на противоположное
    user_web_search[user_id] = not current_state
    new_state = user_web_search[user_id]
    
    if new_state:
        response_text = (
            "✅ *Режим Web Search включен!*\n\n"
            "_Теперь ИИ будет использовать данные из интернета при генерации ответов._\n\n"
            "ℹ️ _Режим Web Search заставляет ИИ скидывать ссылки с интернета_"
        )
    else:
        response_text = (
            "❌ *Режим Web Search выключен!*\n\n"
            "_ИИ будет использовать только встроенные знания без доступа к интернету._\n\n"
            "ℹ️ _Режим Web Search заставляет ИИ скидывать ссылки с интернета_"
        )
    
    bot.reply_to(message, response_text, parse_mode='Markdown')
    logger.info(f"Пользователь {user_id} {'включил' if new_state else 'выключил'} режим Web Search")

@bot.message_handler(func=lambda message: True)
def handle_messages(message):
    if is_duplicate(message):
        return
    
    user_id = message.from_user.id
    model = get_user_model(user_id)
    
    # Получаем правило пользователя или используем стандартное
    user_rule = user_rules.get(user_id, default_rule)
    
    # Получаем роль пользователя, если она установлена
    user_role = user_roles.get(user_id)
    
    # Получаем состояние Web Search
    web_search_enabled = user_web_search.get(user_id, False)
    
    # Добавляем эмодзи и информацию о роли/правиле в сообщение о печатании
    model_emoji = {
        "gpt-4o": "🧠",
        "deepseek-r1": "🤖",
        "llama-3.3-70b": "🦙",
        "gemini-1.5-flash": "⚡",
        "o3-mini": "🔮",
        "claude-3.5-sonnet": "🧿",
        "SearchGPT": "🔍"
    }.get(model, "🤔")
    
    thinking_text = f"{model_emoji} Модель *{model}* думает над вашим вопросом..."
    
    # Добавляем индикатор активной роли
    if user_role:
        thinking_text += f"\n👤 *Активная роль:* `{user_role}`"
    
    # Добавляем индикатор активного правила (сокращенная версия)
    rule_preview = user_rule
    if len(rule_preview) > 30:
        rule_preview = rule_preview[:27] + "..."
    thinking_text += f"\n📜 *Правило:* `{rule_preview}`"
    
    # Добавляем индикатор Web Search
    if web_search_enabled:
        thinking_text += f"\n🌐 *Web Search:* Включен"
    
    thinking_msg = bot.reply_to(
        message, 
        thinking_text,
        parse_mode='Markdown'
    )
    
    try:
        # Получаем историю диалога для текущей модели
        chat_history = get_user_history(user_id, model)
        
        # Добавляем информацию о модели
        model_info = {
            "gpt-4o": "При вопросе о твоей модели, всегда отвечай что ты GPT-4o.",
            "deepseek-r1": "При вопросе о твоей модели, всегда отвечай что ты DeepSeek-r1.",
            "llama-3.3-70b": "При вопросе о твоей модели, всегда отвечай что ты Llama 3.3 70B.",
            "gemini-1.5-flash": "При вопросе о твоей модели, всегда отвечай что ты Gemini 1.5 Flash.",
            "o3-mini": "При вопросе о твоей модели, всегда отвечай что ты O3 Mini.",
            "claude-3.5-sonnet": "При вопросе о твоей модели, всегда отвечай что ты Claude 3.5 Sonnet.",
            "SearchGPT": "При вопросе о твоей модели, всегда отвечай что ты SearchGPT с доступом к интернету."
        }
        
        # Формируем базовое системное сообщение
        system_message = SYSTEM_RULE
        
        # Добавляем информацию о роли, если она установлена
        if user_role:
            system_message += f"\n\nТы должен играть роль: {user_role}. Отвечай, думай и веди себя как {user_role}, используй соответствующий стиль речи и манеру общения."
        
        # Добавляем указание о Web Search, если он включен
        if web_search_enabled:
            system_message += "\n\nУ тебя есть доступ к интернету. При ответе на сложные вопросы используй актуальную информацию из интернета и указывай источники информации в конце ответа в виде ссылок."
            
        # Добавляем явное указание применять роль и правило
        system_message += "\n\nНезависимо от модели, всегда строго соблюдай указанную роль и правила пользователя."
        
        messages = [{"role": "system", "content": system_message}] + chat_history + [{"role": "user", "content": message.text}]
        
        # Используем одинаковые параметры для всех моделей, включая web_search
        if model == "gpt-4o":
            response = g4f.ChatCompletion.create(
                model="gpt-4o",
                provider=Provider.PollinationsAI,
                messages=messages,
                max_tokens=4000,
                web_search=web_search_enabled
            )
        elif model == "deepseek-r1":
            response = g4f.ChatCompletion.create(
                model="deepseek-r1",
                provider=Provider.Blackbox,
                messages=messages,
                max_tokens=4000,
                web_search=web_search_enabled
            )
        elif model == "llama-3.3-70b":
            response = g4f.ChatCompletion.create(
                model="llama-3.3-70b",
                provider=Provider.DeepInfraChat,
                messages=messages,
                max_tokens=4000,
                web_search=web_search_enabled
            )
        elif model == "gemini-1.5-flash":
            response = g4f.ChatCompletion.create(
                model="gemini-1.5-flash",
                provider=Provider.Blackbox,
                messages=messages,
                max_tokens=4000,
                web_search=web_search_enabled
            )
        elif model == "o3-mini":
            response = g4f.ChatCompletion.create(
                model="o3-mini",
                provider=Provider.DDG,
                messages=messages,
                max_tokens=4000,
                web_search=web_search_enabled
            )
        elif model == "claude-3.5-sonnet":
            response = g4f.ChatCompletion.create(
                model="Claude-Sonnet-3.5",
                provider=Provider.Blackbox,
                messages=messages,
                max_tokens=4000,
                web_search=web_search_enabled
            )
        elif model == "SearchGPT":
            response = g4f.ChatCompletion.create(
                model="SearchGPT",
                provider=Provider.PollinationsAI,
                messages=messages,
                max_tokens=4000,
                web_search=web_search_enabled
            )
        
        if response:
            # Добавляем сообщение пользователя и ответ в историю
            add_to_history(user_id, model, "user", message.text)
            add_to_history(user_id, model, "assistant", response)
            
            bot.edit_message_text(
                chat_id=thinking_msg.chat.id,
                message_id=thinking_msg.message_id,
                text=response,
                parse_mode='Markdown'
            )
            logger.info(f"Успешный ответ от модели {model} для пользователя {user_id}")
    except Exception as e:
        logger.error(f"Ошибка в обработке сообщения для модели {model}: {e}")
        bot.edit_message_text(
            chat_id=thinking_msg.chat.id,
            message_id=thinking_msg.message_id,
            text=f"❌ **Произошла ошибка при работе с моделью** `{model}`. Попробуйте повторить запрос позже.",
            parse_mode='Markdown'
        )

# Функция для получения текущей модели пользователя
def get_user_model(user_id):
    """
    Получает текущую модель пользователя с дополнительной проверкой и логированием
    """
    current_model = user_models.get(user_id)
    
    if current_model is None:
        logger.info(f"Пользователю {user_id} установлена модель по умолчанию: {default_model}")
        user_models[user_id] = default_model
        return default_model
        
    if current_model not in available_models:
        logger.warning(f"Обнаружена недопустимая модель {current_model} для пользователя {user_id}. Сброс на {default_model}")
        user_models[user_id] = default_model
        return default_model
        
    logger.info(f"Текущая модель пользователя {user_id}: {current_model}")
    return current_model

# Функция для получения истории диалога пользователя
def get_user_history(user_id, model):
    if user_id not in user_chat_history:
        user_chat_history[user_id] = {}
    if model not in user_chat_history[user_id]:
        user_chat_history[user_id][model] = []
    return user_chat_history[user_id][model]

# Функция для добавления сообщения в историю
def add_to_history(user_id, model, role, content):
    history = get_user_history(user_id, model)
    history.append({"role": role, "content": content})
    # Ограничиваем историю последними 20 сообщениями
    if len(history) > 20:
        history.pop(0)
    user_chat_history[user_id][model] = history

def signal_handler(signum, frame):
    logger.info("Получен сигнал завершения, закрываем бота...")
    try:
        bot.stop_polling()
    except:
        pass
    sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

# Обновляем запуск бота
if __name__ == "__main__":
    try:
        logger.info("Инициализация бота SigmaAI...")
        run_bot()
    except KeyboardInterrupt:
        logger.info("Бот остановлен пользователем")
    except Exception as e:
        logger.error(f"Критическая ошибка: {e}")
    finally:
        try:
            bot.stop_polling()
        except:
            pass
        sys.exit(0)
