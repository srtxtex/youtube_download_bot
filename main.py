import os
import re
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes
from background import keep_alive  # Для поддержки работы Flask

YOUTUBE_REGEX = r'(https?://(?:www\.)?youtu(?:\.be|be\.com)/[a-zA-Z0-9_\-?&=]+)'

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
        print(f"YouTube ссылка найдена в {chat_type} от {username}: {url}")
        
        msg = await update.message.reply_text("📥 Скачиваю видео, подождите...")
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

def download_youtube_video(url):
    import yt_dlp
    output = 'temp_video.mp4'
    ydl_opts = {
        'outtmpl': output,
        'format': 'mp4',
        'quiet': True,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        try:
            ydl.download([url])
            return output
        except Exception as e:
            print(f"Ошибка: {e}")
            return None

if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO)
    bot_token = os.getenv('TELEGRAM_BOT_TOKEN')  # токен берём из секретов Replit
    
    if not bot_token:
        print("Error: TELEGRAM_BOT_TOKEN environment variable is not set!")
        exit(1)
    
    keep_alive()  # поддержка работы через Flask
    application = Application.builder().token(bot_token).build()
    # Обработчик для всех текстовых сообщений (приватные чаты и группы)
    application.add_handler(MessageHandler(
        filters.TEXT & (~filters.COMMAND), 
        handle_message
    ))
    application.run_polling()
