from aiogram import Bot, Router
from aiogram.filters import CommandStart
from aiogram.types import Message


router = Router()


@router.message(CommandStart())
async def cmd_start(message: Message, bot: Bot):
    bot_information = await bot.get_me()

    await message.answer(
        f"Приветствую тебя в <b>{bot_information.full_name}</b>! \n"
        f"<b>ℹ️ Для получения информации о командах и их использовании напиши</b> /help"
    )
