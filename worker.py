import asyncio
import logging

from app.db import init_db
from app.services.telegram import TelegramLeadService

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")


async def main() -> None:
    init_db()
    service = TelegramLeadService()
    await service.start()
    try:
        while True:
            await service.process_pending()
            await asyncio.sleep(15)
    finally:
        await service.stop()


if __name__ == "__main__":
    asyncio.run(main())
