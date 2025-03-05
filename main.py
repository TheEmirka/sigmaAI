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

# Доступные модели
available_models = ["deepseek-r1", "gpt-4o", "llama-3.3-70b", "gemini-1.5-flash"]

# Словарь для хранения выбранной модели генерации изображений для каждого пользователя
user_image_models = {}
default_image_model = "flux"  # меняем модель по умолчанию

# Доступные модели для генерации изображений
available_image_models = ["flux", "midjourney"]

# Добавляем словарь для отслеживания последних сообщений
processed_messages = {}

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
    markup.add(subscribe_btn1, subscribe_btn2)
    
    welcome_text = """
**Привет! Я SigmaAI - ваш бесплатный ИИ-помощник!** 🤖

Я готов помочь вам с различными задачами, от простых вопросов до сложных аналитических задач.

🌟 *Подпишитесь на наши каналы, чтобы быть в курсе всех обновлений и новых функций!*

*Доступные команды:*
• `/start` - показать это приветствие
• `/rules` - правила использования
• `/models` - выбрать модель ИИ
• `/img` - сгенерировать изображение
• `/gmodels` - выбрать модель для генерации изображений
• `/setrule` - установить правило для ИИ
• `/role` - установить роль для ИИ
• `/dialog` - очистить историю диалога
• `/jailbreak` - режим jailbreak (в разработке)

*Доступные модели ИИ:*
• `deepseek-r1` - основная модель
• `gpt-4o` - продвинутая модель
• `llama-3.3-70b` - мощная модель
• `gemini-1.5-flash` - быстрая модель

*Модели для изображений:*
• `flux` - стандартная модель
• `midjourney` - продвинутая модель

💡 _Используйте_ `/models` _и_ `/gmodels` _для переключения между моделями._
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
        
    user_model = user_models.get(message.from_user.id, default_model)
    markup = types.InlineKeyboardMarkup()
    
    for model in available_models:
        button_text = f"{'✅ ' if model == user_model else ''}{model}"
        markup.add(types.InlineKeyboardButton(
            text=button_text,
            callback_data=f"model_{model}"
        ))
    
    bot.reply_to(message, "Выберите модель ИИ:", reply_markup=markup)
    logger.info(f"Отправлено меню выбора модели пользователю {message.from_user.id}")

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
    # Ограничиваем историю последними 10 сообщениями
    if len(history) > 20:
        history.pop(0)
    user_chat_history[user_id][model] = history

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
    
    # Обновляем клавиатуру
    markup = types.InlineKeyboardMarkup()
    for model in available_models:
        button_text = f"{'✅ ' if model == selected_model else ''}{model}"
        markup.add(types.InlineKeyboardButton(
            text=button_text,
            callback_data=f"model_{model}"
        ))
    
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
    bot.reply_to(
        message,
        "❌ *Обработка фотографий не поддерживается.*",
        parse_mode='Markdown'
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
                "*Чтобы задать новое правило, используйте команду:*\n"
                "`/setrule Ваше новое правило`"
            )
        else:
            response_text = (
                "❌ *Правило для ИИ ещё не задано*\n\n"
                "*Чтобы задать правило, используйте команду:*\n"
                "`/setrule Ваше правило`\n\n"
                "_Например:_ `/setrule Отвечай кратко и по делу`"
            )
        bot.reply_to(message, response_text, parse_mode='Markdown')
        return
    
    # Получаем новое правило (всё, что после /setrule)
    new_rule = ' '.join(command_text.split()[1:])
    user_rules[user_id] = new_rule
    
    bot.reply_to(
        message,
        "✅ *Новое правило успешно установлено!*",
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
                "*Чтобы задать новую роль, используйте команду:*\n"
                "`/role Название роли`\n\n"
                "_Например:_ `/role Зеленский` _или_ `/role Стив Джобс`"
            )
        else:
            response_text = (
                "❌ *Роль для ИИ ещё не задана*\n\n"
                "*Чтобы задать роль, используйте команду:*\n"
                "`/role Название роли`\n\n"
                "_Например:_ `/role Зеленский`"
            )
        bot.reply_to(message, response_text, parse_mode='Markdown')
        return
    
    # Получаем новую роль (всё, что после /role)
    new_role = ' '.join(command_text.split()[1:])
    user_roles[user_id] = new_role
    
    bot.reply_to(
        message,
        f"✅ *Новая роль успешно установлена!*\n_Теперь ИИ будет действовать как:_ `{new_role}`",
        parse_mode='Markdown'
    )
    logger.info(f"Пользователь {user_id} установил новую роль для ИИ: {new_role}")

@bot.message_handler(func=lambda message: True)
def handle_messages(message):
    if is_duplicate(message):
        return
    
    user_id = message.from_user.id
    model = get_user_model(user_id)
    
    model_emoji = {
        "gpt-4o": "🧠",
        "deepseek-r1": "🤖",
        "llama-3.3-70b": "🦙",
        "gemini-1.5-flash": "⚡"
    }.get(model, "🤔")
    
    thinking_msg = bot.reply_to(
        message, 
        f"{model_emoji} Модель *{model}* думает над вашим вопросом...",
        parse_mode='Markdown'
    )
    
    try:
        # Получаем историю диалога для текущей модели
        chat_history = get_user_history(user_id, model)
        
        # Получаем правило пользователя или используем стандартное
        user_rule = user_rules.get(user_id, default_rule)
        
        # Получаем роль пользователя, если она установлена
        user_role = user_roles.get(user_id)
        
        # Добавляем информацию о модели
        model_info = {
            "gpt-4o": "При вопросе о твоей модели, всегда отвечай что ты GPT-4o.",
            "deepseek-r1": "При вопросе о твоей модели, всегда отвечай что ты DeepSeek-r1.",
            "llama-3.3-70b": "При вопросе о твоей модели, всегда отвечай что ты Llama 3.3 70B.",
            "gemini-1.5-flash": "При вопросе о твоей модели, всегда отвечай что ты Gemini 1.5 Flash."
        }
        
        # Формируем базовое системное сообщение
        system_message = SYSTEM_RULE
            
        # Добавляем информацию о роли, если она установлена
        if user_role:
            system_message += f"\n\nТы должен играть роль: {user_role}. Отвечай, думай и веди себя как {user_role}, используй соответствующий стиль речи и манеру общения."
            
        # Добавляем пользовательское правило и информацию о модели
        system_message += f"\n\nДополнительное правило:\n{user_rule}\n\n{model_info[model]}"
        
        messages = [{"role": "system", "content": system_message}] + chat_history + [{"role": "user", "content": message.text}]
        
        if model == "gpt-4o":
            response = g4f.ChatCompletion.create(
                model="gpt-4o",
                provider=Provider.PollinationsAI,
                messages=messages
            )
        elif model == "deepseek-r1":
            response = g4f.ChatCompletion.create(
                model="deepseek-r1",
                provider=Provider.Blackbox,
                messages=messages
            )
        elif model == "llama-3.3-70b":
            response = g4f.ChatCompletion.create(
                model="llama-3.3-70b",
                provider=Provider.DeepInfraChat,
                messages=messages
            )
        elif model == "gemini-1.5-flash":
            response = g4f.ChatCompletion.create(
                model="gemini-1.5-flash",
                provider=Provider.Blackbox,
                messages=messages
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
