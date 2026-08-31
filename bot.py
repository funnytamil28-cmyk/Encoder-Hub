import os
import time
import math
import subprocess
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from motor.motor_asyncio import AsyncIOMotorClient
from config import Config

app = Client(
    "EncoderBot",
    api_id=Config.API_ID,
    api_hash=Config.API_HASH,
    bot_token=Config.BOT_TOKEN
)

# MongoDB Setup
mongo_client = AsyncIOMotorClient(Config.MONGO_URL) if Config.MONGO_URL else None
db = mongo_client["EncoderBotDB"] if mongo_client is not None else None
users_db = db["users"] if db is not None else None

if not os.path.isdir(Config.DOWNLOAD_LOCATION):
    os.makedirs(Config.DOWNLOAD_LOCATION)

def humanbytes(size):
    if not size:
        return "0 B"
    power = 2**10
    n = 0
    dic_power_n = {0: ' ', 1: 'K', 2: 'M', 3: 'G', 4: 'T'}
    while size > power:
        size /= power
        n += 1
    return f"{round(size, 2)} {dic_power_n[n]}B"

async def progress_bar(current, total, status_msg, start_time, action_name):
    now = time.time()
    diff = now - start_time
    if round(diff % 5) == 0 or current == total:
        percentage = current * 100 / total
        speed = current / diff if diff > 0 else 0
        eta = round((total - current) / speed) if speed > 0 else 0

        progress = "[{0}{1}] {2}%".format(
            ''.join(["█" for _ in range(math.floor(percentage / 10))]),
            ''.join(["░" for _ in range(10 - math.floor(percentage / 10))]),
            round(percentage, 2)
        )

        tmp = f"**{action_name}**\n\n" \
              f"{progress}\n" \
              f"**Completed:** {humanbytes(current)} / {humanbytes(total)}\n" \
              f"**Speed:** {humanbytes(speed)}/s\n" \
              f"**ETA:** {eta}s"

        try:
            await status_msg.edit_text(tmp)
        except Exception:
            pass

@app.on_message(filters.command("start"))
async def start_handler(client: Client, message: Message):
    user_id = message.from_user.id
    if users_db is not None:
        await users_db.update_one({"_id": user_id}, {"$set": {"user_id": user_id}}, upsert=True)

    await message.reply_text(
        "👋 **Welcome to Media Encoder & Video Tools Bot!**\n\n"
        "• Send a Video file to open the **Video Tools UI**.\n"
        "• Send a Photo to save a Custom Thumbnail to Database.\n"
        "• Use `/delthumb` to remove your saved thumbnail."
    )

# --- Thumbnail Handlers ---
@app.on_message(filters.photo)
async def save_thumbnail(client: Client, message: Message):
    user_id = message.from_user.id
    file_id = message.photo.file_id

    if users_db is not None:
        await users_db.update_one(
            {"_id": user_id},
            {"$set": {"thumb_id": file_id}},
            upsert=True
        )
        await message.reply_text("✅ **Custom Thumbnail Saved successfully!**")
    else:
        await message.reply_text("❌ MongoDB URL missing in Config!")

@app.on_message(filters.command("delthumb"))
async def delete_thumbnail(client: Client, message: Message):
    user_id = message.from_user.id
    if users_db is not None:
        await users_db.update_one({"_id": user_id}, {"$unset": {"thumb_id": ""}})
        await message.reply_text("🗑️ **Custom Thumbnail Deleted successfully!**")
    else:
        await message.reply_text("❌ MongoDB URL missing!")

# --- Video Tools UI Handler ---
@app.on_message(filters.video | filters.document)
async def video_handler(client: Client, message: Message):
    if message.document and not message.document.mime_type.startswith("video/"):
        await message.reply_text("❌ Please send a valid video file!")
        return

    # Video Tools UI Buttons (With Audio Stream and Subtitle Tools)
    buttons = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🎬 Encode 480p", callback_data=f"tool|enc_480p|{message.id}"),
            InlineKeyboardButton("🎬 Encode 720p", callback_data=f"tool|enc_720p|{message.id}")
        ],
        [
            InlineKeyboardButton("🎬 Encode 1080p", callback_data=f"tool|enc_1080p|{message.id}"),
            InlineKeyboardButton("⚡ Fast Compress", callback_data=f"tool|enc_org|{message.id}")
        ],
        [
            InlineKeyboardButton("🔇 Mute Audio (No Audio)", callback_data=f"tool|rm_audio|{message.id}"),
            InlineKeyboardButton("🎵 Extract Audio (No Video)", callback_data=f"tool|audio|{message.id}")
        ],
        [
            InlineKeyboardButton("💬 Keep Audio Track 1", callback_data=f"tool|aud_track1|{message.id}"),
            InlineKeyboardButton("💬 Keep Audio Track 2", callback_data=f"tool|aud_track2|{message.id}")
        ],
        [
            InlineKeyboardButton("📝 Extract Subtitles (.srt)", callback_data=f"tool|ext_sub|{message.id}"),
            InlineKeyboardButton("❌ Remove Subtitles", callback_data=f"tool|rm_sub|{message.id}")
        ],
        [
            InlineKeyboardButton("✂️ 30s Sample Video", callback_data=f"tool|sample|{message.id}")
        ]
    ])

    await message.reply_text(
        "🛠️ **VIDEO TOOLS MENU**\n\nSelect an option to process your video:",
        reply_markup=buttons,
        quote=True
    )

# --- Callback Handler for Tools Menu ---
@app.on_callback_query(filters.regex(r"^tool"))
async def callback_tools(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    data = callback_query.data.split("|")
    action = data[1]
    msg_id = int(data[2])

    message = await client.get_messages(callback_query.message.chat.id, msg_id)
    status_msg = await callback_query.message.edit_text(f"📥 **Processing Request ({action})... Downloading Video...**")
    start_time = time.time()

    file_name = message.video.file_name if message.video else message.document.file_name
    if not file_name:
        file_name = f"video_{message.id}.mp4"

    input_path = os.path.join(Config.DOWNLOAD_LOCATION, file_name)
    output_path = os.path.join(Config.DOWNLOAD_LOCATION, f"out_{action}_{file_name}")

    try:
        # Download Media
        await client.download_media(
            message=message,
            file_name=input_path,
            progress=progress_bar,
            progress_args=(status_msg, start_time, "Downloading Video...")
        )

        await status_msg.edit_text(f"⚙️ **Applying FFmpeg Tool ({action})...**")

        ffmpeg_cmd = []

        # 1. ENCODING & RESOLUTION ADJUSTMENT
        if action.startswith("enc_"):
            quality = action.split("_")[1]
            scale_filter = []
            if quality == "480p":
                scale_filter = ["-vf", "scale=-2:480"]
            elif quality == "720p":
                scale_filter = ["-vf", "scale=-2:720"]
            elif quality == "1080p":
                scale_filter = ["-vf", "scale=-2:1080"]

            ffmpeg_cmd = [
                "ffmpeg", "-y", "-i", input_path,
                *scale_filter,
                "-vcodec", "libx264",
                "-crf", "28",
                "-preset", "fast",
                "-acodec", "aac",
                output_path
            ]

        # 2. REMOVE AUDIO STREAM (MUTE VIDEO)
        elif action == "rm_audio":
            ffmpeg_cmd = [
                "ffmpeg", "-y", "-i", input_path,
                "-c:v", "copy", "-an",
                output_path
            ]

        # 3. EXTRACT AUDIO STREAM (REMOVE VIDEO)
        elif action == "audio":
            output_path = output_path.rsplit(".", 1)[0] + ".mp3"
            ffmpeg_cmd = [
                "ffmpeg", "-y", "-i", input_path,
                "-vn", "-acodec", "libmp3lame", "-q:a", "2",
                output_path
            ]

        # 4. SELECT SPECIFIC AUDIO STREAM
        elif action == "aud_track1":
            ffmpeg_cmd = [
                "ffmpeg", "-y", "-i", input_path,
                "-map", "0:v:0", "-map", "0:a:0", "-c", "copy",
                output_path
            ]

        elif action == "aud_track2":
            ffmpeg_cmd = [
                "ffmpeg", "-y", "-i", input_path,
                "-map", "0:v:0", "-map", "0:a:1?", "-c", "copy",
                output_path
            ]

        # 5. SUBTITLE STREAM TOOLS
        elif action == "ext_sub":
            output_path = output_path.rsplit(".", 1)[0] + ".srt"
            ffmpeg_cmd = [
                "ffmpeg", "-y", "-i", input_path,
                "-map", "0:s:0?",
                output_path
            ]

        elif action == "rm_sub":
            ffmpeg_cmd = [
                "ffmpeg", "-y", "-i", input_path,
                "-c", "copy", "-sn",
                output_path
            ]

        # 6. SAMPLE VIDEO TRIM
        elif action == "sample":
            ffmpeg_cmd = [
                "ffmpeg", "-y", "-ss", "00:00:00", "-i", input_path,
                "-t", "30", "-c", "copy",
                output_path
            ]

        process = subprocess.Popen(ffmpeg_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        process.communicate()

        if not os.path.exists(output_path):
            await status_msg.edit_text("❌ **Processing Failed!** No track or output found.")
            return

        # Fetch Custom Thumbnail
        thumb_file_path = None
        if users_db is not None:
            user_data = await users_db.find_one({"_id": user_id})
            if user_data and "thumb_id" in user_data:
                thumb_file_path = await client.download_media(user_data["thumb_id"], file_name=f"thumb_{user_id}.jpg")

        await status_msg.edit_text("📤 **Uploading Result...**")
        upload_start = time.time()

        # Send File according to type
        if action == "audio":
            await client.send_audio(
                chat_id=message.chat.id,
                audio=output_path,
                caption="🎵 **Audio Stream Extracted Successfully!**",
                progress=progress_bar,
                progress_args=(status_msg, upload_start, "Uploading Audio...")
            )
        elif action == "ext_sub":
            await client.send_document(
                chat_id=message.chat.id,
                document=output_path,
                caption="📝 **Subtitle Stream Extracted (.srt)!**",
                progress=progress_bar,
                progress_args=(status_msg, upload_start, "Uploading Subtitle...")
            )
        else:
            await client.send_video(
                chat_id=message.chat.id,
                video=output_path,
                thumb=thumb_file_path,
                caption=f"✅ **Processed Successfully!** (Action: `{action}`)",
                progress=progress_bar,
                progress_args=(status_msg, upload_start, "Uploading Video...")
            )

    except Exception as e:
        await status_msg.edit_text(f"❌ **Error:** `{e}`")

    finally:
        if os.path.exists(input_path):
            os.remove(input_path)
        if os.path.exists(output_path):
            os.remove(output_path)
        if thumb_file_path and os.path.exists(thumb_file_path):
            os.remove(thumb_file_path)
        try:
            await status_msg.delete()
        except Exception:
            pass

if __name__ == "__main__":
    print("Encoder Bot is running online...")
    app.run()
  
