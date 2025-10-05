import os
import re
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes
from background import keep_alive  # Для поддержки работы Flask

YOUTUBE_REGEX = r'(https?://(?:www\.)?(?:youtube\.com/(?:watch\?v=|shorts/)|youtu\.be/)[a-zA-Z0-9_\-]+(?:\?[a-zA-Z0-9_\-&=]*)?)'

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Проверяем, что есть сообщение и текст
    if update.message is None or update.message.text is None:
        return
    
    # Ищем YouTube ссылки в тексте сообщения
    matches = re.findall(YOUTUBE_REGEX, update.message.text)
    if matches:
        url = matches[0]
        
        # Логируем информацию о чате и пользователе
        chat_type = update.message.chat.type
        username = "Unknown"
        if update.message.from_user:
            username = update.message.from_user.username if update.message.from_user.username else update.message.from_user.first_name
        
        # Определяем тип видео
        is_shorts = is_youtube_shorts(url)
        video_type = "Shorts" if is_shorts else "видео"
        emoji = "🎬" if is_shorts else "🎥"
        
        print(f"YouTube {video_type} найдено в {chat_type} от {username}: {url}")
        
        msg = await update.message.reply_text(f"{emoji} Скачиваю {video_type}, подождите...")
        video_path = download_youtube_video(url)
        
        if video_path:
            with open(video_path, 'rb') as video_file:
                await context.bot.send_video(
                    chat_id=update.message.chat_id,
                    video=video_file,
                    caption=f'🎬 Видео скачано для @{username}'
                )
            # Удаляем временный файл
            os.remove(video_path)
            print(f"Видео успешно отправлено в {chat_type}")
        else:
            await update.message.reply_text("❌ Не удалось скачать видео. Проверьте ссылку.")
        
        # Удаляем сообщение "Скачиваю видео..."
        await msg.delete()

def is_youtube_shorts(url: str) -> bool:
    """Проверка, является ли URL ссылкой на YouTube Shorts"""
    return '/shorts/' in url.lower()

def get_enhanced_ydl_opts(url: str, output_path: str) -> dict:
    """Создает оптимизированные опции для yt-dlp на основе типа видео"""
    base_opts = {
        'outtmpl': output_path,
        'quiet': True,
        'no_warnings': True,
        'retries': 3,
        'fragment_retries': 3,
        'extractor_retries': 2,
    }
    
    # Приоритетная логика выбора качества:
    # 1. Пробуем 480p
    # 2. Если нет, идем вверх: 720p -> 1080p -> 1440p
    # 3. Если ничего выше нет, идем вниз: 360p -> 240p
    # 4. В конце fallback на best
    base_opts['format'] = 'bestvideo[height<=480]+bestaudio/bestvideo[height<=720]+bestaudio/bestvideo[height<=1080]+bestaudio/bestvideo[height<=1440]+bestaudio/bestvideo+bestaudio/bestvideo[height<=360]+bestaudio/bestvideo[height<=240]+bestaudio/best'
    
    # Объединяем видео и аудио в один файл
    base_opts['merge_output_format'] = 'mp4'
    
    return base_opts

def download_youtube_video(url):
    import yt_dlp
    output = 'temp_video.mp4'
    
    try:
        ydl_opts = get_enhanced_ydl_opts(url, output)
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
            return output
    except Exception as e:
        print(f"Ошибка при скачивании: {e}")
        return None

if __name__ == "__main__":
    import logging
    import asyncio
    from telegram.error import Conflict
    
    logging.basicConfig(level=logging.INFO)
    bot_token = os.getenv('TELEGRAM_BOT_TOKEN')  # токен берём из секретов Replit
    
    if not bot_token:
        print("Error: TELEGRAM_BOT_TOKEN environment variable is not set!")
        exit(1)
    
    keep_alive()  # поддержка работы через Flask
    
    # Создаем приложение
    application = Application.builder().token(bot_token).build()
    
    # Добавляем обработчик ошибок
    async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
        print(f"Exception while handling an update: {context.error}")
        if isinstance(context.error, Conflict):
            print("Конфликт с другим экземпляром бота. Перезапускаем...")
            await asyncio.sleep(5)  # Ждем 5 секунд перед повтором
    
    application.add_error_handler(error_handler)
    
    # Обработчик для всех текстовых сообщений (приватные чаты и группы)
    application.add_handler(MessageHandler(
        filters.TEXT & (~filters.COMMAND), 
        handle_message
    ))
    
    # Запускаем бота с обработкой конфликтов
    try:
        print("Запускаем Telegram бота...")
        application.run_polling(drop_pending_updates=True)
    except Conflict as e:
        print(f"Конфликт при запуске: {e}")
        print("Попробуйте перезапустить через несколько секунд.")
    except Exception as e:
        print(f"Неожиданная ошибка: {e}")
