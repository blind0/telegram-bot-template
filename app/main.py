import asyncio
import logging

import coloredlogs
from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.telegram import TelegramAPIServer
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.client.bot import DefaultBotProperties
from aiogram.webhook.aiohttp_server import SimpleRequestHandler
from aiogram.webhook.aiohttp_server import setup_application
from aiogram_dialog import setup_dialogs
from aiohttp import web

from app import db
from app.arguments import parse_arguments
from app.config import Config, parse_config
from app.db import close_orm, init_orm
from app.dialogs import get_dialog_router
from app.handlers import get_handlers_router
from app.inline.handlers import get_inline_router
from app.middlewares import register_middlewares
from app.commands import remove_bot_commands, setup_bot_commands


async def on_startup(
    dispatcher: Dispatcher, bot: Bot, config: Config
):

    register_middlewares(dp=dispatcher, config=config)

    dispatcher.include_router(get_handlers_router())
    dispatcher.include_router(get_inline_router())
    dispatcher.include_router(get_dialog_router())

    await setup_bot_commands(bot, config)

    if config.settings.use_webhook:
        webhook_url = (
            config.webhook.url + config.webhook.path
            if config.webhook.url
            else f"http://localhost:{config.webhook.port}{config.webhook.path}"
        )
        await bot.set_webhook(
            webhook_url,
            drop_pending_updates=config.settings.drop_pending_updates,
            allowed_updates=dispatcher.resolve_used_update_types(),
        )
    else:
        await bot.delete_webhook(
            drop_pending_updates=config.settings.drop_pending_updates,
        )

    bot_info = await bot.get_me()

    logging.info(f"Name - {bot_info.full_name}")
    logging.info(f"Username - @{bot_info.username}")
    logging.info(f"ID - {bot_info.id}")

    states = {
        True: "Enabled",
        False: "Disabled",
    }

    logging.debug(f"Groups Mode - {states[bot_info.can_join_groups]}")
    logging.debug(f"Privacy Mode - {states[not bot_info.can_read_all_group_messages]}")
    logging.debug(f"Inline Mode - {states[bot_info.supports_inline_queries]}")

    logging.error("Bot started!")


async def on_shutdown(dispatcher: Dispatcher, bot: Bot, config: Config):
    logging.warning("Stopping bot...")
    await remove_bot_commands(bot, config)
    await bot.delete_webhook(drop_pending_updates=config.settings.drop_pending_updates)
    await dispatcher.fsm.storage.close()
    await bot.session.close()


async def main():
    coloredlogs.install(level=logging.INFO)
    logging.warning("Starting bot...")

    arguments = parse_arguments()
    config = parse_config(arguments.config)

    session = AiohttpSession(
        api=TelegramAPIServer.from_base(
            config.api.bot_api_url, is_local=config.api.is_local
            )
        )
    token = config.bot.token
    bot_settings = {
        "session": session, 
        "default": DefaultBotProperties(parse_mode=ParseMode.HTML)
        }

    bot = Bot(token, **bot_settings)

    storage = MemoryStorage()

    dp = Dispatcher(storage=storage)
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)

    registry = setup_dialogs(dp)

    context_kwargs = {"config": config, "registry": registry}

    if config.settings.use_webhook:
        logging.getLogger("aiohttp.access").setLevel(logging.CRITICAL)

        web_app = web.Application()
        SimpleRequestHandler(dispatcher=dp, bot=bot, **context_kwargs).register(
            web_app, path=config.webhook.path
        )

        setup_application(web_app, dp, bot=bot, **context_kwargs)

        runner = web.AppRunner(web_app)
        await runner.setup()
        site = web.TCPSite(runner, port=config.webhook.port)
        await site.start()

        await asyncio.Event().wait()
    else:
        await dp.start_polling(bot, **context_kwargs)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logging.error("Bot stopped!")
