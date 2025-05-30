from db import get_pool, init_db
import asyncio
import logging
import sys
from os import getenv
from dotenv import load_dotenv
from collections import defaultdict
import json
from aiogram import Bot, Dispatcher, html, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.types import Message, BotCommandScopeChat, BotCommand, CallbackQuery, InputMediaPhoto, InputMediaVideo, InputMediaAudio
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types.inline_keyboard_button import InlineKeyboardButton
import datetime

load_dotenv()
TOKEN = getenv("BOT_TOKEN", "")
BOT_ID = int(getenv("BOT_ID"))
GROUP_ID = int(getenv("GROUP_ID"))
CHANNEL_ID = int(getenv("CHANNEL_ID"))

bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

pending_media_groups = defaultdict(list)
media_group_timers = {}


async def save_forwarded_message(msg_id: int, user_id: int):
    pool = get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO forward_messages (msg_id, user_id, date) VALUES ($1, $2, $3)",
            msg_id, user_id, datetime.datetime.now().isoformat()
        )

async def get_forward_message_user_id(msg_id: int):
    pool = get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT user_id FROM forward_messages WHERE msg_id = $1", msg_id)
        return row["user_id"] if row else None

async def ban_user(user_id: int):
    pool = get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO banned (user_id, date) VALUES ($1, $2)",
            user_id, datetime.datetime.now().isoformat()
        )

async def unban_user(user_id: int):
    pool = get_pool()
    async with pool.acquire() as conn:
        await conn.execute("DELETE FROM banned WHERE user_id = $1", user_id)

async def is_user_banned(user_id: int):
    pool = get_pool()
    async with pool.acquire() as conn:
        result = await conn.fetchrow(
            "SELECT * FROM banned WHERE user_id = $1", user_id
        )
        return bool(result)

async def register_user(user_id: int):
    pool = get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO users (user_id, date) VALUES ($1, $2)",
            user_id, datetime.datetime.now().isoformat()
        )

async def is_user_registered(user_id: int):
    pool = get_pool()
    async with pool.acquire() as conn:
        result = await conn.fetchrow(
            "SELECT * FROM users WHERE user_id = $1", user_id
        )
        return bool(result)

async def save_forward_relation(button_msg_id: int, message_data: dict, user_id: int):
    pool = get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO forward_relations (button_msg_id, message_data, user_id) VALUES ($1, $2, $3)",
            button_msg_id, json.dumps(message_data), user_id
        )

async def get_forward_relation(button_msg_id: int):
    pool = get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT message_data, user_id FROM forward_relations WHERE button_msg_id = $1", button_msg_id
        )
        if row:
            message_data = json.loads(row['message_data'])
            user_id = row['user_id']
            return message_data, user_id
        return None, None

async def set_bot_commands():
    commands = [
        BotCommand(command="ban", description="забанить (надо ответом)"),
        BotCommand(command="unban", description="разбанить (надо ответом)"),
        BotCommand(command="stats", description="стата"),
    ]
    await bot.set_my_commands(commands, scope=BotCommandScopeChat(chat_id=GROUP_ID))

async def handle_group_reply(message: Message):
    if not message.reply_to_message or message.reply_to_message.from_user.id != BOT_ID:
        return
    user_id = await get_forward_message_user_id(message.reply_to_message.message_id)
    if user_id:
        try:
            await message.copy_to(user_id)
        except Exception as ex:
            await message.reply(f"Не смог ответить\n{html.code(ex)}")
        
@dp.message(Command("stats"))
async def statscmd(message: Message) -> None:
    if message.chat.id == GROUP_ID:
        pool = get_pool()
        async with pool.acquire() as conn:
            total_users = (await conn.fetchrow("SELECT COUNT(*) FROM users"))[0]
            total_msgs = (await conn.fetchrow("SELECT COUNT(*) FROM forward_messages"))[0]
            total_banned = (await conn.fetchrow("SELECT COUNT(*) FROM banned"))[0]
            await message.answer(f"Статья:\n\n👤 Юзеров: {total_users}\n🔪 Забанено: {total_banned}\n☁ Сообщений: {total_msgs}")

@dp.message(Command("ban"))
async def bancmd(message: Message) -> None:
    """Команда бана пользователя."""
    if message.chat.id == GROUP_ID and message.reply_to_message:
        user_id = await get_forward_message_user_id(message.reply_to_message.message_id)
        if user_id and not await is_user_banned(user_id):
            await ban_user(user_id)
            await message.reply("Забанен нахуй")
        elif await is_user_banned(user_id):
            await message.reply("Забанен уже ало")

@dp.message(Command("unban"))
async def unbancmd(message: Message) -> None:
    if message.chat.id == GROUP_ID and message.reply_to_message:
        user_id = await get_forward_message_user_id(message.reply_to_message.message_id)
        if user_id and await is_user_banned(user_id):
            await unban_user(user_id)
            await message.reply("Ладно, пускай пишет")
        elif not await is_user_banned(user_id):
            await message.reply("Пацык хороший же, не в бане")

@dp.message(Command("start"))
async def command_start_handler(message: Message) -> None:
    if message.chat.type == "private":
        if not await is_user_registered(message.from_user.id):
            await register_user(message.from_user.id)
        await message.answer_sticker(sticker="https://i.ibb.co/JWDRfdTW/Untitled.webp")
        await message.answer(f"ооууу! Привет...")

@dp.message()
async def on_message(message: Message) -> None:
    if message.chat.id == GROUP_ID:
        await handle_group_reply(message)
    elif message.chat.type == "private":
        if await is_user_banned(message.from_user.id):
            await message.answer("ой, вы заблокированы")
            return

        suffix = f"\n\n👤 {html.code(message.from_user.full_name)}"
        builder = InlineKeyboardBuilder()
        builder.add(InlineKeyboardButton(text="✅", callback_data="accept"))
        builder.add(InlineKeyboardButton(text="❌", callback_data="deny"))

        if message.media_group_id:
            pending_media_groups[message.media_group_id].append(message)
            if message.media_group_id in media_group_timers:
                media_group_timers[message.media_group_id].cancel()
            media_group_timers[message.media_group_id] = asyncio.create_task(process_media_group_after_delay(message.media_group_id, suffix))
            return

        message_data = {}
        if message.text:
            message_data = {"type": "text", "text": message.text + suffix}
            sent_msg = await bot.send_message(GROUP_ID, message_data["text"], reply_markup=builder.as_markup())
        elif message.photo:
            file_id = message.photo[-1].file_id
            caption = (message.caption or "") + suffix
            message_data = {"type": "photo", "file_id": file_id, "caption": caption}
            sent_msg = await bot.send_photo(GROUP_ID, photo=file_id, caption=caption, reply_markup=builder.as_markup())
        elif message.audio:
            file_id = message.audio.file_id
            caption = (message.caption or "") + suffix
            message_data = {"type": "audio", "file_id": file_id, "caption": caption}
            sent_msg = await bot.send_audio(GROUP_ID, audio=file_id, caption=caption, reply_markup=builder.as_markup())
        elif message.animation:
            file_id = message.animation.file_id
            caption = (message.caption or "") + suffix
            message_data = {"type": "animation", "file_id": file_id, "caption": caption}
            sent_msg = await bot.send_animation(GROUP_ID, animation=file_id, caption=caption, reply_markup=builder.as_markup())
        elif message.video:
            file_id = message.video.file_id
            caption = (message.caption or "") + suffix
            message_data = {"type": "video", "file_id": file_id, "caption": caption}
            sent_msg = await bot.send_video(GROUP_ID, video=file_id, caption=caption, reply_markup=builder.as_markup())

        if message_data:
            await save_forward_relation(sent_msg.message_id, message_data, message.from_user.id)
            await save_forwarded_message(sent_msg.message_id, message.from_user.id)

        await message.answer("Спасибо за ваше сообщение!")

async def process_media_group_after_delay(media_group_id: str, suffix: str):
    try:
        await asyncio.sleep(2)
        messages = pending_media_groups.pop(media_group_id, [])
        if messages:
            message_data = {"type": "media_group", "media": []}
            media = []

            for i, msg in enumerate(messages):
                caption = (msg.caption or "") + suffix if i == 0 else None
                if msg.photo:
                    file_id = msg.photo[-1].file_id
                    media.append(InputMediaPhoto(media=file_id, caption=caption))
                    message_data["media"].append({"type": "photo", "file_id": file_id, "caption": caption})
                elif msg.video:
                    file_id = msg.video.file_id
                    media.append(InputMediaVideo(media=file_id, caption=caption))
                    message_data["media"].append({"type": "video", "file_id": file_id, "caption": caption})
                elif msg.audio:
                    file_id = msg.audio.file_id
                    media.append(InputMediaAudio(media=file_id, caption=caption))
                    message_data["media"].append({"type": "audio", "file_id": file_id, "caption": caption})

            if media:
                sent = await bot.send_media_group(chat_id=GROUP_ID, media=media)
                builder = InlineKeyboardBuilder()
                builder.add(InlineKeyboardButton(text="✅", callback_data="accept"))
                builder.add(InlineKeyboardButton(text="❌", callback_data="deny"))
                button_msg = await sent[0].reply("———————————————————", reply_markup=builder.as_markup())
                await save_forward_relation(button_msg.message_id, message_data, messages[0].from_user.id)
                for sent_msg in sent:
                    await save_forwarded_message(sent_msg.message_id, messages[0].from_user.id)
    except asyncio.CancelledError:
        pass

@dp.callback_query(F.data.in_(["accept", "deny"]))
async def handle_accept_deny(callback: CallbackQuery):
    button_msg_id = callback.message.message_id
    message_data, user_id = await get_forward_relation(button_msg_id)
    if callback.data == "accept" and message_data:
        if message_data["type"] == "text":
            await bot.send_message(CHANNEL_ID, message_data["text"])
        elif message_data["type"] == "photo":
            await bot.send_photo(CHANNEL_ID, photo=message_data["file_id"], caption=message_data["caption"])
        elif message_data["type"] == "audio":
            await bot.send_audio(CHANNEL_ID, audio=message_data["file_id"], caption=message_data["caption"])
        elif message_data["type"] == "voice":
            await bot.send_voice(CHANNEL_ID, voice=message_data["file_id"], caption=message_data["caption"])
        elif message_data["type"] == "animation":
            await bot.send_animation(CHANNEL_ID, animation=message_data["file_id"], caption=message_data["caption"])
        elif message_data["type"] == "video":
            await bot.send_video(CHANNEL_ID, video=message_data["file_id"], caption=message_data["caption"])
        elif message_data["type"] == "media_group":
            media = []
            for item in message_data["media"]:
                if item["type"] == "photo":
                    media.append(InputMediaPhoto(media=item["file_id"], caption=item["caption"]))
                elif item["type"] == "video":
                    media.append(InputMediaVideo(media=item["file_id"], caption=item["caption"]))
                elif item["type"] == "audio":
                    media.append(InputMediaAudio(media=item["file_id"], caption=item["caption"]))
            await bot.send_media_group(CHANNEL_ID, media=media)
        
        try:
            await bot.send_message(user_id, "⭐️ Ваше сообщение было опубликовано")
        except: 
            pass

    is_banned = await is_user_banned(user_id) if user_id else False
    builder = InlineKeyboardBuilder()
    builder.add(InlineKeyboardButton(text="🔓 Разбан" if is_banned else "⛔ Бан", callback_data="unban" if is_banned else "ban"))
    await callback.message.edit_reply_markup(reply_markup=builder.as_markup())
    await callback.answer()

@dp.callback_query(F.data == "ban")
async def handle_ban(callback: CallbackQuery):
    """Обработка кнопки 'бан'."""
    button_msg_id = callback.message.message_id
    _, user_id = await get_forward_relation(button_msg_id)
    if user_id:
        await ban_user(user_id)
    builder = InlineKeyboardBuilder()
    builder.add(InlineKeyboardButton(text="🔓 Разбан", callback_data="unban"))
    await callback.message.edit_reply_markup(reply_markup=builder.as_markup())
    await callback.answer()

@dp.callback_query(F.data == "unban")
async def handle_unban(callback: CallbackQuery):
    """Обработка кнопки 'разбан'."""
    button_msg_id = callback.message.message_id
    _, user_id = await get_forward_relation(button_msg_id)
    if user_id:
        await unban_user(user_id)
    builder = InlineKeyboardBuilder()
    builder.add(InlineKeyboardButton(text="⛔ Бан", callback_data="ban"))
    await callback.message.edit_reply_markup(reply_markup=builder.as_markup())
    await callback.answer()

async def main() -> None:
    if not TOKEN:
        print("Token not found in the venv")
        return
    await init_db()
    await set_bot_commands()
    await dp.start_polling(bot)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, stream=sys.stdout)
    asyncio.run(main())