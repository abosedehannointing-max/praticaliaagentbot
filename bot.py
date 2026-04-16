import os
import logging
import asyncio
import img2pdf
from starlette.applications import Starlette
from starlette.routing import Route
from starlette.requests import Request
from starlette.responses import PlainTextResponse, Response
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

# --- Setup Logging ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Configuration ---
TOKEN = os.environ.get("BOT_TOKEN")
if not TOKEN:
    raise ValueError("BOT_TOKEN environment variable is not set!")

RENDER_URL = os.environ.get("RENDER_EXTERNAL_URL")
PORT = int(os.environ.get("PORT", 8000))

# --- Store images for each user ---
user_sessions = {}

# --- Bot Handlers ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_sessions[user_id] = []  # Initialize session
    await update.message.reply_text(
        "👋 Hello! Send me some images, then use /done to generate your PDF."
    )

async def handle_image(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in user_sessions:
        user_sessions[user_id] = []

    # Download the image
    photo_file = await update.message.photo[-1].get_file()
    file_path = f"temp_{user_id}_{update.message.message_id}.jpg"
    await photo_file.download_to_drive(file_path)
    user_sessions[user_id].append(file_path)
    
    await update.message.reply_text(
        f"✅ Image added. You have {len(user_sessions[user_id])} image(s). Send more or /done."
    )

async def done(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    image_paths = user_sessions.get(user_id, [])
    
    if not image_paths:
        await update.message.reply_text("⚠️ No images to convert. Send me some images first!")
        return

    await update.message.reply_text("🔄 Generating your PDF...")
    pdf_path = f"output_{user_id}.pdf"
    
    try:
        # Convert images to PDF using img2pdf
        with open(pdf_path, "wb") as f:
            f.write(img2pdf.convert(image_paths))
        
        # Send the PDF to the user
        with open(pdf_path, 'rb') as pdf_file:
            await update.message.reply_document(
                document=pdf_file,
                filename=f"converted_images_{user_id}.pdf",
                caption=f"✅ Here's your PDF with {len(image_paths)} page(s)!"
            )
        
        # Clean up temporary files
        for path in image_paths:
            if os.path.exists(path):
                os.remove(path)
        if os.path.exists(pdf_path):
            os.remove(pdf_path)
            
    except Exception as e:
        logger.error(f"PDF generation error: {e}")
        await update.message.reply_text(f"❌ Error generating PDF: {str(e)}")
    
    # Clear session
    user_sessions[user_id] = []

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    # Clean up any temporary files
    if user_id in user_sessions:
        for path in user_sessions[user_id]:
            if os.path.exists(path):
                os.remove(path)
        user_sessions[user_id] = []
    await update.message.reply_text("❌ Operation cancelled. All images cleared.")

# --- Webhook and Server Setup ---
async def main():
    # Create Telegram Bot Application
    app = Application.builder().token(TOKEN).updater(None).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("done", done))
    app.add_handler(CommandHandler("cancel", cancel))
    app.add_handler(MessageHandler(filters.PHOTO, handle_image))
    
    # Set webhook
    if RENDER_URL:
        webhook_path = "/telegram"
        await app.bot.set_webhook(url=f"{RENDER_URL}{webhook_path}")
        logger.info(f"✅ Webhook set to {RENDER_URL}{webhook_path}")
    else:
        logger.warning("⚠️ RENDER_EXTERNAL_URL not set. Webhook will not be configured.")

    # Create Starlette web server
    async def telegram_webhook(request: Request):
        """Receives updates from Telegram."""
        try:
            data = await request.json()
            update = Update.de_json(data, app.bot)
            await app.update_queue.put(update)
            return Response(status_code=200)
        except Exception as e:
            logger.error(f"Error processing update: {e}")
            return Response(status_code=500)

    async def health_check(_: Request):
        """Render health check endpoint."""
        return PlainTextResponse("OK")

    starlette_app = Starlette(routes=[
        Route("/telegram", telegram_webhook, methods=["POST"]),
        Route("/healthcheck", health_check, methods=["GET"]),
    ])

    # Run server
    logger.info(f"🚀 Starting web server on port {PORT}...")
    import uvicorn
    webserver = uvicorn.Server(
        uvicorn.Config(starlette_app, host="0.0.0.0", port=PORT, log_level="info")
    )
    
    async with app:
        await app.start()
        await webserver.serve()
        await app.stop()

if __name__ == "__main__":
    asyncio.run(main())
