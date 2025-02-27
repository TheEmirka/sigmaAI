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
# import easyocr  # OCR временно отключен
# import numpy as np  # Не нужен без OCR
# import cv2  # Не нужен без OCR
# from PIL import Image  # Не нужен без OCR
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

# Доступные модели
available_models = ["deepseek-r1", "gpt-4o", "llama-3.3-70b"]

# Словарь для хранения выбранной модели генерации изображений для каждого пользователя
user_image_models = {}
default_image_model = "flux"  # меняем модель по умолчанию

# Доступные модели для генерации изображений
available_image_models = ["flux"]  # оставляем только flux

# Добавляем в начало файла новые переменные
user_analysis_models = {}
default_analysis_model = "OCR"  # Меняем на OCR
available_analysis_models = ["OCR"]  # Оставляем только OCR

# Добавляем словарь для отслеживания последних сообщений
processed_messages = {}

# Изменяем функцию проверки дубликатов
def is_duplicate_message(message):
    # Создаем уникальный ключ для сообщения
    message_key = f"{message.chat.id}_{message.message_id}"
    current_time = time.time()
    
    # Очищаем только старые сообщения (старше 5 секунд)
    for key in list(processed_messages.keys()):
        if current_time - processed_messages[key] > 5:
            del processed_messages[key]
    
    # Проверяем, было ли сообщение уже обработано
    if message_key in processed_messages:
        return True
    
    # Добавляем сообщение в обработанные
    processed_messages[message_key] = current_time
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
    try:
        logger.info("Запуск бота...")
        bot.infinity_polling(
            timeout=60,
            long_polling_timeout=60,
            interval=1,  # Увеличиваем интервал
            allowed_updates=["message", "callback_query"],
            skip_pending=True,
            none_stop=True  # Добавляем параметр для непрерывной работы
        )
    except Exception as e:
        logger.error(f"Ошибка в работе бота: {e}")
        time.sleep(5)

@bot.message_handler(commands=['start'])
def send_welcome(message):
    if is_duplicate_message(message):
        return
    markup = types.InlineKeyboardMarkup(row_width=1)
    subscribe_btn1 = types.InlineKeyboardButton(text='Подписаться на SigmaAI', url='https://t.me/SigmaAIchannel')
    subscribe_btn2 = types.InlineKeyboardButton(text='Подписаться на Ares AI', url='https://t.me/Aress_AI')
    markup.add(subscribe_btn1, subscribe_btn2)
    
    welcome_text = """
**Привет! Я SigmaAI - ваш бесплатный ИИ-помощник!** 🤖

Я готов помочь вам с различными задачами, от простых вопросов до сложных аналитических задач.

🌟 *Подпишитесь на наши каналы, чтобы быть в курсе всех обновлений и новых функций!*

__Доступные команды:__
• `/start` - показать это приветствие
• `/rules` - правила использования
• `/models` - выбрать модель ИИ
• `/img` - сгенерировать изображение
• `/gmodels` - выбрать модель для генерации изображений
• `/anmodels` - выбрать модель для анализа изображений
    """
    bot.reply_to(message, welcome_text, reply_markup=markup, parse_mode='Markdown')

@bot.message_handler(commands=['rules'])
def send_rules(message):
    if is_duplicate_message(message):
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
    if is_duplicate_message(message):
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

@bot.callback_query_handler(func=lambda call: call.data.startswith('model_'))
def handle_model_selection(call):
    selected_model = call.data.split('_')[1]
    current_model = user_models.get(call.from_user.id, default_model)
    
    # Проверяем, не выбрана ли уже эта модель
    if selected_model == current_model:
        bot.answer_callback_query(call.id, "⚠️ Эта модель уже выбрана!", show_alert=True)
        return
    
    user_models[call.from_user.id] = selected_model
    
    markup = types.InlineKeyboardMarkup()
    for model in available_models:
        button_text = f"{'✅ ' if model == selected_model else ''}{model}"
        markup.add(types.InlineKeyboardButton(
            text=button_text,
            callback_data=f"model_{model}"
        ))
    
    bot.edit_message_reply_markup(
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        reply_markup=markup
    )
    
    bot.answer_callback_query(call.id, f"✅ Выбрана модель {selected_model}")

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
@retry_on_error
def generate_image(message):
    if is_duplicate_message(message):
        return
    try:
        # Получаем текст после команды
        if len(message.text.split()) < 2:
            bot.reply_to(message, "Пожалуйста, добавьте описание изображения после команды /img")
            return
        
        prompt = " ".join(message.text.split()[1:])
        thinking_msg = bot.reply_to(message, "🎨 Генерирую изображение...")
        
        # Параметры изображения
        width = 1024
        height = 1024
        seed = int(time.time())  # используем текущее время как seed
        
        # Правильно кодируем промпт для URL
        prompt_encoded = urllib.parse.quote(prompt)
        
        # Создаем URL для генерации
        image_url = f"https://pollinations.ai/p/{prompt_encoded}?width={width}&height={height}&seed={seed}&model=flux&nologo=true&private=false&enhance=true&safe=false"
        
        # Скачиваем изображение
        response = requests.get(image_url)
        if response.status_code == 200:
            # Отправляем изображение как файл
            bot.send_photo(
                message.chat.id,
                response.content,
                caption=f"🎨 Сгенерировано с помощью Flux",
                reply_to_message_id=message.message_id
            )
            # Удаляем сообщение "генерирую" только после успешной отправки
            bot.delete_message(thinking_msg.chat.id, thinking_msg.message_id)
        else:
            bot.edit_message_text(
                chat_id=thinking_msg.chat.id,
                message_id=thinking_msg.message_id,
                text="❌ Не удалось сгенерировать изображение. Попробуйте другой запрос."
            )
            
    except Exception as e:
        error_message = (
            f"❌ Произошла ошибка при генерации изображения.\n"
            f"⏳ Пожалуйста, попробуйте снова.\n"
            f"🔍 Ошибка: {str(e)}"
        )
        try:
            bot.edit_message_text(
                chat_id=thinking_msg.chat.id,
                message_id=thinking_msg.message_id,
                text=error_message
            )
        except:
            bot.reply_to(message, error_message)

@bot.message_handler(commands=['anmodels'])
def choose_analysis_model(message):
    if is_duplicate_message(message):
        return
    user_model = user_analysis_models.get(message.from_user.id, default_analysis_model)
    markup = types.InlineKeyboardMarkup()
    
    for model in available_analysis_models:
        button_text = f"{'✅ ' if model == user_model else ''}{model}"
        markup.add(types.InlineKeyboardButton(
            text=button_text,
            callback_data=f"an_model_{model}"
        ))
    
    bot.reply_to(message, "**Выберите модель для анализа изображений:**", reply_markup=markup, parse_mode='Markdown')

@bot.callback_query_handler(func=lambda call: call.data.startswith('an_model_'))
def handle_analysis_model_selection(call):
    selected_model = call.data.split('_')[2]
    current_model = user_analysis_models.get(call.from_user.id, default_analysis_model)
    
    # Проверяем, не выбрана ли уже эта модель
    if selected_model == current_model:
        bot.answer_callback_query(call.id, "⚠️ Эта модель уже выбрана!", show_alert=True)
        return
    
    user_analysis_models[call.from_user.id] = selected_model
    
    markup = types.InlineKeyboardMarkup()
    for model in available_analysis_models:
        button_text = f"{'✅ ' if model == selected_model else ''}{model}"
        markup.add(types.InlineKeyboardButton(
            text=button_text,
            callback_data=f"an_model_{model}"
        ))
    
    bot.edit_message_text(
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        text="**Выберите модель для анализа изображений:**",
        reply_markup=markup,
        parse_mode='Markdown'
    )
    
    bot.answer_callback_query(call.id, f"✅ Выбрана модель {selected_model}")

@bot.message_handler(content_types=['photo'])
@retry_on_error
def handle_photo(message):
    if is_duplicate_message(message):
        return
    try:
        bot.reply_to(
            message,
            "⚙️ *Анализ фотографий находится в разработке!*\n\n"
            "Пожалуйста, попробуйте позже. Мы работаем над улучшением этой функции.",
            parse_mode='Markdown'
        )
    except Exception as e:
        logger.error(f"Ошибка при отправке сообщения о разработке: {e}")
        bot.reply_to(message, "❌ Произошла ошибка. Пожалуйста, попробуйте позже.")

@bot.message_handler(func=lambda message: True)
@retry_on_error
def handle_messages(message):
    if is_duplicate_message(message):
        return
    try:
        model = user_models.get(message.from_user.id, default_model)
        
        # Отправляем сообщение "думаю..."
        thinking_msg = bot.reply_to(message, "🤔 Думаю над вашим вопросом...")
        
        # Разные системные сообщения для разных моделей
        if model == "gpt-4o":
            system_message = """Ты - ИИ помощник GPT, который работает в телеграм боте SigmaAI, отвечай, размышляй, думай всегда на русском языке, но если тебя попросят ответить на другом языке, ты послушаешься его. При вопросе о твоей модели, всегда отвечай что ты GPT-4o.

Давай самые лучшие варианты для своего клиента, удачи!"""
        elif model == "deepseek-r1":
            system_message = """Ты - ИИ помощник DeepSeek, который работает в телеграм боте SigmaAI, отвечай, размышляй, думай всегда на русском языке, но если тебя попросят ответить на другом языке, ты послушаешься его. При вопросе о твоей модели, всегда отвечай что ты DeepSeek-r1.

Давай самые лучшие варианты для своего клиента, удачи!"""
        elif model == "llama-3.3-70b":
            system_message = """Ты - ИИ помощник Llama, который работает в телеграм боте SigmaAI, отвечай, размышляй, думай всегда на русском языке, но если тебя попросят ответить на другом языке, ты послушаешься его. При вопросе о твоей модели, всегда отвечай что ты Llama 3.3 70B.

Давай самые лучшие варианты для своего клиента, удачи!"""
        
        if model == "gpt-4o":
            response = g4f.ChatCompletion.create(
                model="gpt-4o",
                provider=Provider.PollinationsAI,
                messages=[
                    {"role": "system", "content": system_message},
                    {"role": "user", "content": message.text}
                ]
            )
        elif model == "deepseek-r1":
            response = g4f.ChatCompletion.create(
                model="deepseek-r1",
                provider=Provider.Blackbox,
                messages=[
                    {"role": "system", "content": system_message},
                    {"role": "user", "content": message.text}
                ]
            )
        elif model == "llama-3.3-70b":
            response = g4f.ChatCompletion.create(
                model="llama-3.3-70b",
                provider=Provider.DeepInfraChat,
                messages=[
                    {"role": "system", "content": system_message},
                    {"role": "user", "content": message.text}
                ]
            )
        
        if response:
            try:
                bot.edit_message_text(
                    chat_id=thinking_msg.chat.id,
                    message_id=thinking_msg.message_id,
                    text=response
                )
            except telebot.apihelper.ApiTelegramException as e:
                if e.error_code != 400:  # Игнорируем ошибку о неизмененном сообщении
                    raise e
            
    except Exception as e:
        logger.error(f"Ошибка в обработке сообщения: {e}")
        error_message = (
            f"❌ Произошла ошибка при обработке запроса.\n"
            f"⏳ Пожалуйста, подождите 30 секунд и попробуйте снова.\n"
            f"🔍 Ошибка: {str(e)}"
        )
        try:
            bot.edit_message_text(
                chat_id=thinking_msg.chat.id,
                message_id=thinking_msg.message_id,
                text=error_message
            )
        except:
            bot.reply_to(message, error_message)

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
        # Убираем инициализацию OCR
        
        while True:
            try:
                run_bot()
            except KeyboardInterrupt:
                logger.info("Бот остановлен пользователем")
                break
            except Exception as e:
                logger.error(f"Критическая ошибка: {e}")
                logger.info("Перезапуск через 30 секунд...")
                time.sleep(30)
                continue
            
    except KeyboardInterrupt:
        logger.info("Бот остановлен пользователем")
    except Exception as e:
        logger.error(f"Критическая ошибка при инициализации: {e}")
    finally:
        try:
            bot.stop_polling()
        except:
            pass
        sys.exit(0)
