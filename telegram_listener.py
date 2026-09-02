"""
Fica escutando mensagens no bot do Telegram. Quando voce manda "/status" ou
"status", ele responde com um print atual da tela + nivel/poder/XP.
"""
import logging
import time

import mss
import numpy as np
import requests

from common import (
    MONITOR_INDEX,
    TELEGRAM_CHAT_ID,
    TELEGRAM_TOKEN,
    extract_stats,
    format_stats_text,
    save_snapshot,
    send_telegram_photo,
)

API_URL = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"
STATUS_SNAPSHOT_PATH = "status_snapshot.jpg"
LOG_PATH = "telegram_listener.log"
STATUS_COMMANDS = {"/status", "status"}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[logging.FileHandler(LOG_PATH, encoding="utf-8"), logging.StreamHandler()],
)
log = logging.getLogger(__name__)


def get_updates(offset=None):
    params = {"timeout": 25}
    if offset is not None:
        params["offset"] = offset
    resp = requests.get(f"{API_URL}/getUpdates", params=params, timeout=30)
    resp.raise_for_status()
    return resp.json()["result"]


def main():
    initial = get_updates()
    offset = (initial[-1]["update_id"] + 1) if initial else None
    log.info("Ouvindo comandos no Telegram... (Ctrl+C para parar)")

    with mss.MSS() as sct:
        while True:
            try:
                updates = get_updates(offset)
                for update in updates:
                    offset = update["update_id"] + 1
                    message = update.get("message")
                    if not message or "text" not in message:
                        continue
                    if str(message["chat"]["id"]) != TELEGRAM_CHAT_ID:
                        continue

                    text = message["text"].strip().lower()
                    if text in STATUS_COMMANDS:
                        log.info(f"comando recebido: {text}")
                        full = np.array(sct.grab(sct.monitors[MONITOR_INDEX]))[:, :, :3]
                        save_snapshot(STATUS_SNAPSHOT_PATH, full)
                        stats = format_stats_text(extract_stats(full))
                        send_telegram_photo(STATUS_SNAPSHOT_PATH, f"Status atual:\n\n{stats}", log=log)

            except KeyboardInterrupt:
                log.info("Encerrando.")
                break
            except requests.RequestException as exc:
                log.error(f"[erro] {exc}")
                time.sleep(5)


if __name__ == "__main__":
    main()
