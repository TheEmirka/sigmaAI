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
bot = telebot.TeleBot('7606481420:AAF2D6dln9mMSxBXgN3adMNZ575324dOzbI', state_storage=state_storage)

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

# Доступные модели (добавляю o1-mini)
available_models = ["deepseek-r1", "o3-mini", "o1-mini", "claude-3.5-sonnet", "gpt-4o", "llama-3.3-70b", "gemini-1.5-flash", "SearchGPT", "claude-3-haiku"]

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

# Добавляем словарь для хранения выбранного агента для каждого пользователя
user_agents = {}
default_agent = "Python Agent"

# Доступные агенты
available_agents = ["Python Agent", "Java Agent", "JavaScript Agent", "HTML Agent"]

# Описания агентов
agent_descriptions = {
    "Python Agent": "Специализируется на Python коде, алгоритмах и решении задач программирования на Python",
    "Java Agent": "Эксперт по Java, объектно-ориентированному программированию и разработке на Java",
    "JavaScript Agent": "Специалист по JavaScript, веб-разработке, фреймворкам и библиотекам JS",
    "HTML Agent": "Мастер HTML/CSS, верстки и дизайна веб-страниц"
}

# Добавляем словарь для хранения выбранной модели для анализа изображений
user_vision_models = {}
default_vision_model = "GPT-4o-mini"

# Доступные модели для анализа изображений
available_vision_models = ["GPT-4o-mini", "gpt-4o"]

# Добавляем словарь для хранения выбранного голоса для каждого пользователя
user_voices = {}
default_voice = "alloy"  # голос по умолчанию

# Доступные голоса для преобразования текста в речь
available_voices = [
    "alloy", "echo", "fable", "onyx", "nova", "shimmer", "coral", "verse", 
    "ballad", "ash", "sage", "amuch", "aster", "brook", "clover", "dan", 
    "elan", "marilyn", "meadow"
]

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
• `/vision_models` - выбрать модель для анализа изображений
• `/agents` - выбрать специализированного агента
• `/agent` - использовать выбранного агента
• `/voices` - выбрать голос для озвучивания текста
• `/voice` - преобразовать текст в аудио
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
• `o3-mini` - мощнейшая модель
• `o1-mini` - быстрая модель
• `llama-3.3-70b` - мощная модель
• `gemini-1.5-flash` - быстрая модель
• `claude-3.5-sonnet` - умная модель
• `claude-3-haiku` - быстрая модель
• `SearchGPT` - модель с доступом к интернету

*Специализированные агенты:*
• `Python Agent` - эксперт по Python
• `Java Agent` - эксперт по Java
• `JavaScript Agent` - эксперт по JavaScript
• `HTML Agent` - эксперт по HTML/CSS

*Модели для изображений:*
• `flux` - стандартная модель
• `midjourney` - продвинутая модель

*Модели для анализа изображений:*
• `GPT-4o-mini` - быстрая модель
• `gpt-4o` - продвинутая модель

💡 _Используйте_ `/models`, `/agents`, `/image_models` _и_ `/vision_models` _для переключения между моделями._
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
        "<----- OpenAI ----->": ["gpt-4o", "o3-mini", "o1-mini"],
        "<----- Anthropic ----->": ["claude-3.5-sonnet", "claude-3-haiku"],
        "<----- Meta ----->": ["llama-3.3-70b"],
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
        "<----- OpenAI ----->": ["gpt-4o", "o3-mini", "o1-mini"],
        "<----- Anthropic ----->": ["claude-3.5-sonnet", "claude-3-haiku"],
        "<----- Meta ----->": ["llama-3.3-70b"],
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

@bot.message_handler(commands=['image_models'])
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
    
    # Добавляем эмодзи в зависимости от модели
    model_emoji = "✨" if current_model == "flux" else "🖌️"
    
    thinking_msg = bot.reply_to(message, f"{model_emoji} *{current_model.capitalize()}* генерирует изображение...", parse_mode='Markdown')
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
                caption=f"{model_emoji} Изображение сгенерировано моделью *{current_model.capitalize()}*\n\n**Запрос:** _{prompt}_",
                parse_mode='Markdown',
                reply_to_message_id=message.message_id
            )
            bot.delete_message(thinking_msg.chat.id, thinking_msg.message_id)
        else:
            bot.edit_message_text(
                chat_id=thinking_msg.chat.id,
                message_id=thinking_msg.message_id,
                text=f"❌ Не удалось сгенерировать изображение с моделью *{current_model.capitalize()}*. Попробуйте другой запрос или другую модель.",
                parse_mode='Markdown'
            )
    except Exception as e:
        logger.error(f"Ошибка при генерации изображения: {e}")
        bot.edit_message_text(
            chat_id=thinking_msg.chat.id,
            message_id=thinking_msg.message_id,
            text=f"❌ Произошла ошибка при генерации изображения с моделью *{current_model.capitalize()}*. Попробуйте позже.",
            parse_mode='Markdown'
        )

@bot.message_handler(commands=['vision_models'])
def choose_vision_model(message):
    if is_duplicate(message):
        logger.info(f"Дубликат команды /vision_models от пользователя {message.from_user.id}")
        return
        
    user_id = message.from_user.id
    user_model = user_vision_models.get(user_id, default_vision_model)
    markup = types.InlineKeyboardMarkup()
    
    # Добавляем кнопки для каждой модели
    for model in available_vision_models:
        button_text = f"{'✅ ' if model == user_model else ''}{model}"
        markup.add(types.InlineKeyboardButton(
            text=button_text,
            callback_data=f"vision_model_{model}"
        ))
    
    bot.reply_to(message, "Выберите модель для анализа изображений:", reply_markup=markup)
    logger.info(f"Отправлено меню выбора модели анализа изображений пользователю {message.from_user.id}")

@bot.callback_query_handler(func=lambda call: call.data.startswith('vision_model_'))
def handle_vision_model_selection(call):
    selected_model = '_'.join(call.data.split('_')[2:])  # Берем все части после 'vision_model_'
    user_id = call.from_user.id
    current_model = user_vision_models.get(user_id, default_vision_model)
    
    # Проверяем, не выбрана ли уже эта модель
    if selected_model == current_model:
        bot.answer_callback_query(call.id, "⚠️ Эта модель уже выбрана!", show_alert=True)
        return
    
    # Сохраняем выбор модели
    user_vision_models[user_id] = selected_model
    logger.info(f"Модель анализа изображений пользователя {user_id} изменена на {selected_model}")
    
    # Создаем новую клавиатуру
    markup = types.InlineKeyboardMarkup()
    
    # Добавляем кнопки для каждой модели
    for model in available_vision_models:
        button_text = f"{'✅ ' if model == selected_model else ''}{model}"
        markup.add(types.InlineKeyboardButton(
            text=button_text,
            callback_data=f"vision_model_{model}"
        ))
    
    try:
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=f"Выбрана модель анализа изображений: {selected_model}",
            reply_markup=markup
        )
        bot.answer_callback_query(call.id, f"✅ Выбрана модель {selected_model}")
        logger.info(f"Успешно обновлен интерфейс выбора модели анализа изображений для пользователя {user_id}")
    except Exception as e:
        logger.error(f"Ошибка при обновлении модели анализа изображений: {e}")
        bot.answer_callback_query(call.id, "❌ Произошла ошибка при выборе модели")

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
    
    # Получаем выбранную модель для анализа изображений
    vision_model = user_vision_models.get(user_id, default_vision_model)
    
    # Получаем имя пользователя для персонализации ответа
    user_name = message.from_user.first_name or "Пользователь"
    
    thinking_msg = bot.reply_to(message, f"🔍 Анализирую изображение с помощью модели *{vision_model}*...", parse_mode='Markdown')
    
    try:
        # Получаем содержимое файла изображения
        response = requests.get(file_url)
        image_data = base64.b64encode(response.content).decode('utf-8')
        
        # Формируем сообщение для модели с указанием использовать Markdown
        system_message = "Ты - ИИ помощник, который анализирует изображения. Отвечай всегда на русском языке, подробно описывай все детали, которые видишь на изображении. Используй Markdown для форматирования ответа: **жирный текст** для важных деталей, *курсив* для акцентов, списки для перечисления элементов."
        
        # Выбираем модель и параметры в зависимости от выбранной модели
        if vision_model == "GPT-4o-mini":
            model_name = "openai"
        elif vision_model == "gpt-4o":
            model_name = "openai-large"
        else:
            model_name = "openai"  # По умолчанию
        
        # Используем PollinationsAI с выбранной моделью для анализа
        response_text = g4f.ChatCompletion.create(
            model=model_name,
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
            # Добавляем эмодзи и заголовок с Markdown форматированием
            formatted_response = f"# 🖼️ Анализ изображения ({vision_model})\n\n{response_text}"
            
            # Отправляем с Markdown форматированием
            bot.edit_message_text(
                chat_id=thinking_msg.chat.id,
                message_id=thinking_msg.message_id,
                text=formatted_response,
        parse_mode='Markdown'
            )
            logger.info(f"Успешный анализ изображения для пользователя {user_id} с моделью {vision_model}")
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

@bot.message_handler(commands=['agents'])
def choose_agent(message):
    if is_duplicate(message):
        logger.info(f"Дубликат команды /agents от пользователя {message.from_user.id}")
        return
        
    user_id = message.from_user.id
    current_agent = user_agents.get(user_id, default_agent)
    markup = types.InlineKeyboardMarkup()
    
    # Добавляем кнопки для каждого агента (без заголовка)
    for agent in available_agents:
        button_text = f"{'✅ ' if agent == current_agent else ''}{agent}"
        markup.add(types.InlineKeyboardButton(
            text=button_text,
            callback_data=f"agent_{agent}"
        ))
    
    bot.reply_to(message, "Выберите специализированного агента:", reply_markup=markup)
    logger.info(f"Отправлено меню выбора агента пользователю {message.from_user.id}")

@bot.callback_query_handler(func=lambda call: call.data.startswith('agent_'))
def handle_agent_selection(call):
    # Получаем название выбранного агента
    selected_agent = '_'.join(call.data.split('_')[1:])
    user_id = call.from_user.id
    current_agent = user_agents.get(user_id, default_agent)
    
    # Проверяем, не выбран ли уже этот агент
    if selected_agent == current_agent:
        bot.answer_callback_query(call.id, "⚠️ Этот агент уже выбран!", show_alert=True)
        return
    
    # Сохраняем выбор агента
    user_agents[user_id] = selected_agent
    logger.info(f"Агент пользователя {user_id} изменен на {selected_agent}")
    
    # Создаем новую клавиатуру (без заголовка)
    markup = types.InlineKeyboardMarkup()
    
    # Добавляем кнопки для каждого агента
    for agent in available_agents:
        button_text = f"{'✅ ' if agent == selected_agent else ''}{agent}"
        markup.add(types.InlineKeyboardButton(
            text=button_text,
            callback_data=f"agent_{agent}"
        ))
    
    # Описание выбранного агента
    agent_description = agent_descriptions.get(selected_agent, "Специализированный агент для решения задач")
    
    try:
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=f"Выбран агент: *{selected_agent}*\n\n_{agent_description}_",
            reply_markup=markup,
            parse_mode='Markdown'
        )
        bot.answer_callback_query(call.id, f"✅ Выбран агент {selected_agent}")
        logger.info(f"Успешно обновлен интерфейс выбора агента для пользователя {user_id}")
    except Exception as e:
        logger.error(f"Ошибка при обновлении агента: {e}")
        bot.answer_callback_query(call.id, "❌ Произошла ошибка при выборе агента")

@bot.message_handler(commands=['agent'])
def use_agent(message):
    if is_duplicate(message):
        logger.info(f"Дубликат команды /agent от пользователя {message.from_user.id}")
        return
        
    user_id = message.from_user.id
    command_text = message.text.strip()
    
    # Проверяем, есть ли текст после команды
    if len(command_text.split()) < 2:
        bot.reply_to(message, "Пожалуйста, добавьте запрос после команды /agent\n\nПример: `/agent напиши функцию для сортировки массива`", parse_mode='Markdown')
        return
    
    # Получаем текущего агента пользователя или используем агент по умолчанию
    current_agent = user_agents.get(user_id, default_agent)
    
    # Получаем запрос (всё, что после /agent)
    prompt = ' '.join(command_text.split()[1:])
    
    # Получаем правило пользователя или используем стандартное
    user_rule = user_rules.get(user_id, default_rule)
    
    # Для агентов НЕ используем роль пользователя
    # user_role = user_roles.get(user_id)  # Закомментировано
    
    # Получаем состояние Web Search
    web_search_enabled = user_web_search.get(user_id, False)
    
    # Эмодзи для разных агентов
    agent_emoji = {
        "Python Agent": "🐍",
        "Java Agent": "☕",
        "JavaScript Agent": "🟨",
        "HTML Agent": "🌐"
    }.get(current_agent, "🤖")
    
    thinking_text = f"{agent_emoji} *{current_agent}* думает над вашим запросом..."
    
    # Убираем индикатор активной роли
    # if user_role:
    #     thinking_text += f"\n👤 *Активная роль:* `{user_role}`"
    
    # Добавляем индикатор активного правила (сокращенная версия)
    rule_preview = user_rule
    if len(rule_preview) > 30:
        rule_preview = rule_preview[:27] + "..."
    thinking_text += f"\n📜 *Правило:* `{rule_preview}`"
    
    # Добавляем индикатор Web Search
    if web_search_enabled:
        thinking_text += f"\n🌐 *Web Search:* Включен"
    
    thinking_msg = bot.reply_to(message, thinking_text, parse_mode='Markdown')
    
    try:
        # Формируем системное сообщение в зависимости от выбранного агента
        base_system_messages = {
            "Python Agent": "Ты - Python Agent, эксперт по программированию на Python. Твоя задача - помогать с кодом на Python, объяснять концепции, решать алгоритмические задачи и давать советы по лучшим практикам. Всегда используй форматирование кода в своих ответах и давай подробные объяснения. Отвечай на русском языке.",
            "Java Agent": "Ты - Java Agent, эксперт по программированию на Java. Твоя задача - помогать с кодом на Java, объяснять концепции ООП, решать задачи и давать советы по лучшим практикам. Всегда используй форматирование кода в своих ответах и давай подробные объяснения. Отвечай на русском языке.",
            "JavaScript Agent": "Ты - JavaScript Agent, эксперт по программированию на JavaScript. Твоя задача - помогать с кодом на JavaScript, объяснять концепции, фреймворки (React, Vue, Angular), решать задачи и давать советы по лучшим практикам. Всегда используй форматирование кода в своих ответах и давай подробные объяснения. Отвечай на русском языке.",
            "HTML Agent": "Ты - HTML Agent, эксперт по HTML, CSS и веб-дизайну. Твоя задача - помогать с версткой, стилями, макетами и дизайном веб-страниц. Всегда используй форматирование кода в своих ответах и давай подробные объяснения. Отвечай на русском языке."
        }
        
        base_system_message = base_system_messages.get(current_agent, "Ты - специализированный агент для решения задач программирования. Отвечай на русском языке.")
        
        # Формируем системное сообщение с ЯВНЫМ приоритетом пользовательского правила
        # Но БЕЗ информации о роли
        system_message = f"АБСОЛЮТНЫЙ ПРИОРИТЕТ - СЛЕДУЙ ЭТОМУ ПРАВИЛУ В ПЕРВУЮ ОЧЕРЕДЬ: {user_rule}\n\n{base_system_message}\n\n{SYSTEM_RULE}"
        
        # Убираем добавление информации о роли
        # if user_role:
        #     system_message += f"\n\nТы должен играть роль: {user_role}. Отвечай, думай и веди себя как {user_role}, используй соответствующий стиль речи и манеру общения."
        
        # Добавляем указание о Web Search, если он включен
        if web_search_enabled:
            system_message += "\n\nУ тебя есть доступ к интернету. При ответе на сложные вопросы используй актуальную информацию из интернета и указывай источники информации в конце ответа в виде ссылок."
        
        # Добавляем дополнительное усиленное указание о приоритете правила
        system_message += "\n\nВНИМАНИЕ: Пользовательское правило выше является САМЫМ ГЛАВНЫМ и имеет ВЫСШИЙ ПРИОРИТЕТ над всеми другими инструкциями. ВСЕГДА следуй ему в первую очередь!"
        
        # Формируем сообщения для запроса
        messages = [
            {"role": "system", "content": system_message},
            {"role": "user", "content": prompt}
        ]
        
        # Определяем модель и провайдера в зависимости от агента
        agent_models = {
            "Python Agent": {"model": "Python Agent", "provider": Provider.Blackbox},
            "Java Agent": {"model": "Java Agent", "provider": Provider.Blackbox},
            "JavaScript Agent": {"model": "JavaScript Agent", "provider": Provider.Blackbox},
            "HTML Agent": {"model": "HTML Agent", "provider": Provider.Blackbox}
        }
        
        agent_config = agent_models.get(current_agent, {"model": current_agent, "provider": Provider.Blackbox})
        
        response = g4f.ChatCompletion.create(
            model=agent_config["model"],
            provider=agent_config["provider"],
            messages=messages,
            max_tokens=4000,
            web_search=web_search_enabled
        )
        
        if response:
            # Обработка ответа для удаления символов ">" в начале строк
            response = response.replace("\n> ", "\n").replace("> ", "")
            
            # Добавляем сообщение пользователя и ответ в историю
            add_to_history(user_id, current_agent, "user", message.text)
            add_to_history(user_id, current_agent, "assistant", response)
            
            bot.edit_message_text(
                chat_id=thinking_msg.chat.id,
                message_id=thinking_msg.message_id,
                text=response,
                parse_mode='Markdown'
            )
            logger.info(f"Успешный ответ от агента {current_agent} для пользователя {user_id}")
        else:
            bot.edit_message_text(
                chat_id=thinking_msg.chat.id,
                message_id=thinking_msg.message_id,
                text=f"❌ Не удалось получить ответ от агента {current_agent}. Попробуйте повторить запрос позже.",
                parse_mode='Markdown'
            )
    except Exception as e:
        logger.error(f"Ошибка при использовании агента {current_agent}: {e}")
        bot.edit_message_text(
            chat_id=thinking_msg.chat.id,
            message_id=thinking_msg.message_id,
            text=f"❌ **Произошла ошибка при работе с агентом** `{current_agent}`. Попробуйте повторить запрос позже.\n\nДетали ошибки: {str(e)}",
            parse_mode='Markdown'
        )

@bot.message_handler(commands=['voices'])
def choose_voice(message):
    if is_duplicate(message):
        logger.info(f"Дубликат команды /voices от пользователя {message.from_user.id}")
        return
        
    user_id = message.from_user.id
    current_voice = user_voices.get(user_id, default_voice)
    markup = types.InlineKeyboardMarkup()
    
    # Добавляем кнопки для каждого голоса по 3 в строку
    for i in range(0, len(available_voices), 3):
        row_buttons = []
        
        # Добавляем голоса в текущую строку
        for j in range(3):
            if i + j < len(available_voices):
                voice = available_voices[i + j]
                button_text = f"{'✅ ' if voice == current_voice else ''}{voice}"
                row_buttons.append(types.InlineKeyboardButton(
                    text=button_text,
                    callback_data=f"voice_{voice}"
                ))
        
        # Добавляем строку кнопок
        markup.row(*row_buttons)
    
    bot.reply_to(message, "Выберите голос для озвучивания текста:", reply_markup=markup)
    logger.info(f"Отправлено меню выбора голоса пользователю {message.from_user.id}")

@bot.callback_query_handler(func=lambda call: call.data.startswith('voice_'))
def handle_voice_selection(call):
    selected_voice = call.data.split('_')[1]
    user_id = call.from_user.id
    current_voice = user_voices.get(user_id, default_voice)
    
    # Проверяем, не выбран ли уже этот голос
    if selected_voice == current_voice:
        bot.answer_callback_query(call.id, "⚠️ Этот голос уже выбран!", show_alert=True)
        return
    
    # Сохраняем выбор голоса
    user_voices[user_id] = selected_voice
    logger.info(f"Голос пользователя {user_id} изменен на {selected_voice}")
    
    # Создаем новую клавиатуру
    markup = types.InlineKeyboardMarkup()
    
    # Добавляем кнопки для каждого голоса по 3 в строку
    for i in range(0, len(available_voices), 3):
        row_buttons = []
        
        # Добавляем голоса в текущую строку
        for j in range(3):
            if i + j < len(available_voices):
                voice = available_voices[i + j]
                button_text = f"{'✅ ' if voice == selected_voice else ''}{voice}"
                row_buttons.append(types.InlineKeyboardButton(
                    text=button_text,
                    callback_data=f"voice_{voice}"
                ))
        
        # Добавляем строку кнопок
        markup.row(*row_buttons)
    
    try:
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=f"Выбран голос: {selected_voice}",
            reply_markup=markup
        )
        bot.answer_callback_query(call.id, f"✅ Выбран голос {selected_voice}")
        logger.info(f"Успешно обновлен интерфейс выбора голоса для пользователя {user_id}")
    except Exception as e:
        logger.error(f"Ошибка при обновлении голоса: {e}")
        bot.answer_callback_query(call.id, "❌ Произошла ошибка при выборе голоса")

@bot.message_handler(commands=['voice'])
def text_to_speech(message):
    if is_duplicate(message):
        logger.info(f"Дубликат команды /voice от пользователя {message.from_user.id}")
        return
        
    # Проверяем, есть ли текст после команды
    if len(message.text.split()) == 1:
        bot.reply_to(
        message, 
            "ℹ️ Пожалуйста, добавьте текст после команды /voice\n\n"
            "*Пример:* `/voice Привет, как дела?`\n"
            "*Пример:* `/voice Расскажи анекдот`",
        parse_mode='Markdown'
    )
        return
        
    user_id = message.from_user.id
    current_voice = user_voices.get(user_id, default_voice)
    
    # Берем текст после команды /voice
    text = ' '.join(message.text.split()[1:])  # Изменено для безопасного получения текста
    text_encoded = urllib.parse.quote(text)
    
    thinking_msg = bot.reply_to(message, f"🔊 Генерирую аудио с голосом *{current_voice}*...", parse_mode='Markdown')
    logger.info(f"Начата генерация аудио для пользователя {user_id} с голосом {current_voice}")
    
    try:
        # Используем модель openai-audio, которая должна просто повторять текст
        audio_url = f"https://text.pollinations.ai/{text_encoded}?model=openai-audio&voice={current_voice}"
        
        # Делаем запрос с увеличенным timeout
        response = requests.get(audio_url, timeout=30)
        
        # Проверяем только статус ответа, без проверки размера
        if response.status_code == 200:
            # Сохраняем аудио во временный файл
            temp_audio_file = f"temp_audio_{user_id}.mp3"
            with open(temp_audio_file, "wb") as f:
                f.write(response.content)
            
            # Проверяем размер файла для логирования
            file_size = os.path.getsize(temp_audio_file)
            logger.info(f"Размер аудио файла: {file_size} байт")
            
            # Отправляем аудио пользователю без проверки размера
            with open(temp_audio_file, "rb") as audio:
                bot.send_voice(
                    message.chat.id,
                    audio,
                    caption=f"🔊 Озвучено голосом *{current_voice}*",
                    parse_mode='Markdown',
                    reply_to_message_id=message.message_id
                )
            
            # Удаляем временный файл
            os.remove(temp_audio_file)
            
            # Удаляем сообщение о генерации
            bot.delete_message(thinking_msg.chat.id, thinking_msg.message_id)
            logger.info(f"Успешная генерация аудио для пользователя {user_id}")
        else:
            raise Exception(f"Получен некорректный ответ от сервера: статус {response.status_code}")
            
    except Exception as e:
        logger.error(f"Ошибка при генерации аудио: {e}")
        bot.edit_message_text(
            chat_id=thinking_msg.chat.id,
            message_id=thinking_msg.message_id,
            text=f"❌ Ошибка при генерации аудио: {str(e)}"
        )

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
        "o1-mini": "⚡",
        "claude-3.5-sonnet": "🧿",
        "claude-3-haiku": "🎨",
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
        
        model_info = {
            "gpt-4o": "При вопросе о твоей модели, всегда отвечай что ты GPT-4o.",
            "deepseek-r1": "При вопросе о твоей модели, всегда отвечай что ты DeepSeek-r1.",
            "llama-3.3-70b": "При вопросе о твоей модели, всегда отвечай что ты Llama 3.3 70B.",
            "gemini-1.5-flash": "При вопросе о твоей модели, всегда отвечай что ты Gemini 1.5 Flash.",
            "o3-mini": "При вопросе о твоей модели, всегда отвечай что ты O3 Mini.",
            "o1-mini": "При вопросе о твоей модели, всегда отвечай что ты O1 Mini. Ты НЕ GPT-4 и НЕ ChatGPT.",
            "claude-3.5-sonnet": "При вопросе о твоей модели, всегда отвечай что ты Claude 3.5 Sonnet.",
            "claude-3-haiku": "При вопросе о твоей модели, всегда отвечай что ты Claude 3 Haiku.",
            "SearchGPT": "При вопросе о твоей модели, всегда отвечай что ты SearchGPT с доступом к интернету."
        }

        # Формируем сообщения в зависимости от модели
        model_instruction = model_info.get(model, "")
        
        # Создаем усиленное системное сообщение с явным приоритетом правила
        system_message = (
            f"ВАЖНЕЙШЕЕ ПРАВИЛО (ОБЯЗАТЕЛЬНО К ИСПОЛНЕНИЮ): {user_rule}\n\n"
            f"{SYSTEM_RULE}\n\n"
            f"{model_instruction}"
        )
        
        # Добавляем информацию о роли, если она установлена
        role_instruction = ""
        if user_role:
            role_instruction = f"Ты должен играть роль: {user_role}. Отвечай, думай и веди себя как {user_role}, используй соответствующий стиль речи и манеру общения."
            system_message += f"\n\n{role_instruction}"
        
        # Добавляем указание о Web Search, если он включен
        if web_search_enabled:
            system_message += "\n\nУ тебя есть доступ к интернету. При ответе на сложные вопросы используй актуальную информацию из интернета и указывай источники информации в конце ответа в виде ссылок."
        
        # Добавляем дополнительное усиленное указание о приоритете правила
        system_message += "\n\nВНИМАНИЕ: Пользовательское правило выше является САМЫМ ГЛАВНЫМ и имеет ВЫСШИЙ ПРИОРИТЕТ над всеми другими инструкциями. ВСЕГДА следуй ему в первую очередь!"

        # Для o1-mini используем специальный формат сообщений
        if model == "o1-mini":
            try:
                # Создаем специальное сообщение для o1-mini с явным указанием роли и ПРИОРИТЕТОМ ПРАВИЛА
                o1_instruction = f"Ты модель O1 Mini. "
                
                # Добавляем ВАЖНЕЙШЕЕ ПРАВИЛО в начало с многократным повторением
                o1_instruction += f"ВАЖНЕЙШЕЕ ПРАВИЛО (ОБЯЗАТЕЛЬНО К ИСПОЛНЕНИЮ): {user_rule}. "
                o1_instruction += f"ПРИОРИТЕТНОЕ ПРАВИЛО: {user_rule}. "
                o1_instruction += f"ГЛАВНАЯ ИНСТРУКЦИЯ: {user_rule}. "
                
                if user_role:
                    # Усиливаем инструкцию по роли для o1-mini
                    o1_instruction += f"ВАЖНО: Ты должен ПРИТВОРИТЬСЯ, что ты {user_role}. Ты НЕ ИИ, ты {user_role}. "
                    o1_instruction += f"Ты должен отвечать так, как будто ты {user_role}. "
                    o1_instruction += f"Ты должен думать как {user_role}. "
                    o1_instruction += f"Ты должен использовать лексику, характерную для {user_role}. "
                    o1_instruction += f"Ты должен иметь знания и опыт, характерные для {user_role}. "
                    o1_instruction += f"НИКОГДА не упоминай, что ты ИИ или языковая модель. "
                    o1_instruction += f"ВСЕГДА оставайся в роли {user_role} на протяжении всего диалога. "
                
                o1_instruction += f"НАПОМИНАНИЕ: Ты ОБЯЗАН следовать правилу: {user_rule}. Это правило имеет наивысший приоритет над всеми остальными инструкциями!"
                
                # Создаем сообщения с явным указанием роли и правила в каждом сообщении
                base_messages = [
                    {"role": "user", "content": o1_instruction + system_message},
                    {"role": "assistant", "content": f"Я буду строго следовать правилу: {user_rule}" + (f" и буду действовать как {user_role}" if user_role else "")}
                ]
                
                # Добавляем историю диалога с напоминаниями о правиле
                if chat_history:
                    for msg in chat_history:
                        if msg["role"] == "user":
                            # Добавляем напоминание о правиле и роли в каждое сообщение пользователя
                            rule_reminder = f"[ВАЖНЕЙШЕЕ ПРАВИЛО: {user_rule}] "
                            role_reminder = f"[ПОМНИ: Ты - {user_role}, а НЕ ИИ] " if user_role else ""
                            base_messages.append({"role": "user", "content": rule_reminder + role_reminder + msg["content"]})
                        else:
                            base_messages.append(msg)
                
                # Добавляем текущее сообщение пользователя с напоминанием о правиле и роли
                rule_reminder = f"[ВАЖНЕЙШЕЕ ПРАВИЛО: {user_rule}] "
                role_reminder = f"[ПОМНИ: Ты - {user_role}, а НЕ ИИ] " if user_role else ""
                base_messages.append({"role": "user", "content": rule_reminder + role_reminder + message.text})
                
                response = g4f.ChatCompletion.create(
                    model="openai-reasoning",
                    provider=Provider.PollinationsAI,
                    messages=base_messages,
                    max_tokens=4000,
                    web_search=web_search_enabled
                )
            except Exception as e:
                logger.error(f"Ошибка при работе с моделью o1-mini: {e}")
                raise Exception("Не удалось обработать сообщение для модели o1-mini")

        elif model == "claude-3.5-sonnet" or model == "claude-3-haiku":
            try:
                # Создаем специальное сообщение для Claude с многократным повторением правила и роли
                claude_system_message = (
                    f"ВАЖНЕЙШЕЕ ПРАВИЛО (ОБЯЗАТЕЛЬНО К ИСПОЛНЕНИЮ): {user_rule}\n\n"
                    f"ПРИОРИТЕТНОЕ ПРАВИЛО: {user_rule}\n\n"
                    f"ГЛАВНАЯ ИНСТРУКЦИЯ: {user_rule}\n\n"
                )
                
                # Добавляем роль в начало системного сообщения и повторяем её несколько раз
                if user_role:
                    claude_system_message += (
                        f"ТВОЯ РОЛЬ: Ты - {user_role}. ПРИТВОРИСЬ, что ты {user_role}.\n"
                        f"ВАЖНО: Ты должен отвечать, думать и вести себя как {user_role}.\n"
                        f"ИНСТРУКЦИЯ ПО РОЛИ: Представь, что ты {user_role} и отвечаешь в этом образе.\n"
                        f"НИКОГДА не упоминай, что ты ИИ или языковая модель.\n"
                        f"ВСЕГДА оставайся в роли {user_role} на протяжении всего диалога.\n"
                        f"Используй лексику, характерную для {user_role}.\n"
                        f"Имей знания и опыт, характерные для {user_role}.\n\n"
                        f"ВАЖНО: НЕ НАЧИНАЙ каждый ответ с фразы 'Я {user_role}'. Просто отвечай в образе {user_role}.\n\n"
                    )
                
                claude_system_message += (
                    f"ПРАВИЛО: {user_rule}\n\n"
                    f"ИНСТРУКЦИЯ: {user_rule}\n\n"
                    f"{SYSTEM_RULE}\n\n"
                    f"Ты - {model}. {model_instruction}\n\n"
                )
                
                if user_role:
                    claude_system_message += f"НАПОМИНАНИЕ О РОЛИ: Ты - {user_role}. Отвечай как {user_role}, но НЕ НАЧИНАЙ ответ с 'Я {user_role}'.\n\n"
                
                claude_system_message += f"НАПОМИНАНИЕ О ПРАВИЛЕ: Всегда следуй правилу: {user_rule}"
                
                # Создаем базовые сообщения с системным сообщением
                base_messages = [
                    {"role": "system", "content": claude_system_message}
                ]
                
                # Добавляем историю диалога с напоминаниями о роли и правиле
                if chat_history:
                    for i, msg in enumerate(chat_history):
                        if msg["role"] == "user":
                            # Перед каждым сообщением пользователя добавляем напоминание о роли и правиле
                            role_reminder = f"Помни, ты - {user_role}, а НЕ ИИ. Не представляйся как '{user_role}'. " if user_role else ""
                            base_messages.append({"role": "system", "content": f"{role_reminder}Следуй правилу: {user_rule}"})
                        
                        # Добавляем сообщение без модификации
                        base_messages.append(msg)
                
                # Добавляем напоминание о роли перед текущим сообщением
                if user_role:
                    base_messages.append({"role": "system", "content": f"ВАЖНО: Ты - {user_role}, а НЕ ИИ. Отвечай как {user_role}, но НЕ НАЧИНАЙ ответ с 'Я {user_role}'. Следуй правилу: {user_rule}"})
                else:
                    base_messages.append({"role": "system", "content": f"ВАЖНО: Следуй правилу: {user_rule}"})
                
                # Добавляем текущее сообщение пользователя
                base_messages.append({"role": "user", "content": message.text})
                
                # Выбираем правильного провайдера в зависимости от модели
                provider = Provider.Blackbox if model == "claude-3.5-sonnet" else Provider.DDG
                model_name = "Claude-Sonnet-3.5" if model == "claude-3.5-sonnet" else "claude-3-haiku"
                
                response = g4f.ChatCompletion.create(
                    model=model_name,
                    provider=provider,
                    messages=base_messages,
                    max_tokens=4000,
                    web_search=web_search_enabled
                )
                
                # Удаляем только префикс "Я {user_role}" если он есть в начале ответа
                if user_role:
                    if response.startswith(f"Я {user_role}."):
                        response = response[len(f"Я {user_role}."):]
                    elif response.startswith(f"Я {user_role},"):
                        response = response[len(f"Я {user_role},"):]
                    elif response.startswith(f"Я - {user_role}."):
                        response = response[len(f"Я - {user_role}."):]
                    elif response.startswith(f"Я - {user_role},"):
                        response = response[len(f"Я - {user_role},"):]
                    
                    # Удаляем лишние пробелы в начале
                    response = response.lstrip()
                
            except Exception as e:
                logger.error(f"Ошибка при работе с моделью {model}: {e}")
                raise Exception(f"Не удалось обработать сообщение для модели {model}")

        # Для остальных моделей используем общий подход с усиленными напоминаниями
        else:
            try:
                # Усиливаем системное сообщение для всех моделей
                if user_role:
                    role_instruction = (
                        f"ТВОЯ РОЛЬ: Ты - {user_role}. ПРИТВОРИСЬ, что ты {user_role}.\n"
                        f"ВАЖНО: Ты должен отвечать, думать и вести себя как {user_role}.\n"
                        f"НИКОГДА не упоминай, что ты ИИ или языковая модель.\n"
                        f"ВСЕГДА оставайся в роли {user_role} на протяжении всего диалога.\n"
                        f"Используй лексику, характерную для {user_role}.\n"
                        f"Имей знания и опыт, характерные для {user_role}.\n"
                    )
                    system_message = f"{role_instruction}\n\n{system_message}"
                
                # Создаем базовые сообщения с системным сообщением
                base_messages = [
                    {"role": "system", "content": system_message}
                ]
                
                # Добавляем историю диалога с напоминаниями о правиле и роли
                if chat_history:
                    # Добавляем напоминание о правиле и роли в начало истории
                    role_reminder = f"ПОМНИ: Ты - {user_role}, а НЕ ИИ. " if user_role else ""
                    base_messages.append({"role": "system", "content": f"{role_reminder}Следуй правилу: {user_rule}"})
                    
                    for msg in chat_history:
                        if msg["role"] == "user":
                            # Перед каждым сообщением пользователя добавляем напоминание
                            role_reminder = f"ПОМНИ: Ты - {user_role}, а НЕ ИИ. " if user_role else ""
                            base_messages.append({"role": "system", "content": f"{role_reminder}Помни о правиле: {user_rule}"})
                        base_messages.append(msg)
                
                # Добавляем напоминание о правиле и роли перед текущим сообщением
                role_reminder = f"ВАЖНО: Ты - {user_role}, а НЕ ИИ. " if user_role else ""
                base_messages.append({"role": "system", "content": f"{role_reminder}Следуй правилу: {user_rule}"})
                
                # Добавляем текущее сообщение пользователя
                base_messages.append({"role": "user", "content": message.text})
                
                # Выбираем модель и провайдера в зависимости от выбранной модели
                model_config = {
                    "gpt-4o": {"model": "gpt-4o", "provider": Provider.PollinationsAI},
                    "deepseek-r1": {"model": "deepseek-r1", "provider": Provider.Blackbox},
                    "llama-3.3-70b": {"model": "llama-3.3-70b", "provider": Provider.DeepInfraChat},
                    "gemini-1.5-flash": {"model": "gemini-1.5-flash", "provider": Provider.Blackbox},
                    "o3-mini": {"model": "o3-mini", "provider": Provider.DDG},
                    "SearchGPT": {"model": "SearchGPT", "provider": Provider.PollinationsAI}
                }.get(model, {"model": model, "provider": Provider.Blackbox})
                
                response = g4f.ChatCompletion.create(
                    model=model_config["model"],
                    provider=model_config["provider"],
                    messages=base_messages,
                    max_tokens=4000,
                    web_search=web_search_enabled
                )
            except Exception as e:
                logger.error(f"Ошибка при работе с моделью {model}: {e}")
                raise Exception(f"Не удалось обработать сообщение для модели {model}")
        
        if response:
            # Обработка ответа для удаления символов ">" в начале строк
            response = response.replace("\n> ", "\n").replace("> ", "")
            
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
