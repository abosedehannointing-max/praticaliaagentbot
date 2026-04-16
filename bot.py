import os
import logging
import asyncio
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
TOKEN = os.environ["BOT_TOKEN"]
# Render automatically sets this environment variable
RENDER_URL = os.environ.get("RENDER_EXTERNAL_URL")
PORT = int(os.environ.get("PORT", 8000))

# --- A simple dictionary to store images for each user ---
user_sessions = {}

# --- Bot Handlers (Integrate your logic here) ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_sessions[user_id] = [] # Initialize a session for the user
    await update.message.reply_text(
        "👋 Send me some images. When you're done, use /done to generate the PDF."
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
    
    await update.message.reply_text(f"✅ Image added. You have {len(user_sessions[user_id])} image(s).")

async def done(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    image_paths = user_sessions.get(user_id, [])
    
    if not image_paths:
        await update.message.reply_text("⚠️ No images to convert.")
        return

    await update.message.reply_text("🔄 Generating your PDF...")
    pdf_path = f"output_{user_id}.pdf"
    # --- Call your image-to-PDF function here ---
    # convert_images_to_pdf(image_paths, pdf_path)
    
    # Simulate conversion for demonstration
    await asyncio.sleep(1)
    
    # Clean up temporary files and session
    # for path in image_paths: os.remove(path)
    # with open(pdf_path, 'rb') as pdf_file: await update.message.reply_document(...)
    # os.remove(pdf_path)
    user_sessions[user_id] = []
    await update.message.reply_text("✨ Here is your PDF! (Simulated)")

# --- Webhook and Server Setup ---
async def main():
    # 1. Create the Telegram Bot Application
    app = Application.builder().token(TOKEN).updater(None).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.PHOTO, handle_image))
    app.add_handler(CommandHandler("done", done))
    
    # 2. Set the webhook to point to Render's public URL
    if RENDER_URL:
        webhook_path = "/telegram"
        await app.bot.set_webhook(url=f"{RENDER_URL}{webhook_path}")
        logger.info(f"Webhook set to {RENDER_URL}{webhook_path}")
    else:
        logger.error("RENDER_EXTERNAL_URL is not set. Webhook setup failed.")
        return

    # 3. Create a Starlette web server to handle incoming updates
    async def telegram_webhook(request: Request):
        """Receives updates from Telegram and queues them for the bot."""
        try:
            data = await request.json()
            update = Update.de_json(data, app.bot)
            await app.update_queue.put(update)
            return Response(status_code=200)
        except Exception as e:
            logger.error(f"Error processing update: {e}")
            return Response(status_code=500)

    async def health_check(_: Request):
        """Render uses this endpoint to ensure the service is alive."""
        return PlainTextResponse("OK")

    starlette_app = Starlette(routes=[
        Route("/telegram", telegram_webhook, methods=["POST"]),
        Route("/healthcheck", health_check, methods=["GET"]),
    ])

    # 4. Run both the bot application and the web server
    logger.info(f"Starting web server on port {PORT}...")
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
