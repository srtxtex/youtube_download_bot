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

def select_best_format(formats):
    """Выбирает лучший формат согласно приоритетам: 480p -> выше -> ниже"""
    if not formats:
        return None
    
    # Разделяем форматы на видео и аудио
    video_formats = []
    audio_formats = []
    combined_formats = []
    
    for fmt in formats:
        if fmt.get('vcodec') != 'none' and fmt.get('acodec') != 'none':
            combined_formats.append(fmt)
        elif fmt.get('vcodec') != 'none' and fmt.get('acodec') == 'none':
            video_formats.append(fmt)
        elif fmt.get('vcodec') == 'none' and fmt.get('acodec') != 'none':
            audio_formats.append(fmt)
    
    # Приоритеты качества
    target_heights = [480, 720, 1080, 1440, 2160, 360, 240, 144]
    
    # Сначала пробуем найти комбинированный формат
    for target in target_heights:
        for fmt in combined_formats:
            height = fmt.get('height', 0)
            if height and abs(height - target) <= 100:  # допуск ±100px
                return fmt['format_id']
    
    # Если нет комбинированного, ищем раздельные видео+аудио
    selected_video = None
    for target in target_heights:
        for fmt in video_formats:
            height = fmt.get('height', 0)
            if height and abs(height - target) <= 100:
                selected_video = fmt['format_id']
                break
        if selected_video:
            break
    
    # Выбираем лучшее аудио
    best_audio = None
    if audio_formats:
        best_audio = max(audio_formats, key=lambda x: x.get('abr', 0) or 0)['format_id']
    
    if selected_video and best_audio:
        return f"{selected_video}+{best_audio}"
    elif selected_video:
        return selected_video
    
    # Fallback на лучший доступный
    return 'best'

def download_youtube_video(url):
    import yt_dlp
    output = 'temp_video.mp4'
    
    try:
        # Сначала получаем информацию о доступных форматах
        info_opts = {
            'quiet': True,
            'no_warnings': True,
        }
        
        with yt_dlp.YoutubeDL(info_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            formats = info.get('formats', [])
            
            # Выбираем лучший формат
            selected_format = select_best_format(formats)
            print(f"Выбран формат: {selected_format}")
        
        # Скачиваем с выбранным форматом
        download_opts = {
            'outtmpl': output,
            'format': selected_format,
            'merge_output_format': 'mp4',
            'quiet': True,
            'no_warnings': True,
            'retries': 3,
            'fragment_retries': 3,
        }
        
        with yt_dlp.YoutubeDL(download_opts) as ydl:
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
