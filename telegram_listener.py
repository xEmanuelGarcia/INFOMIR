"""
Fica escutando mensagens no bot do Telegram. Quando voce manda "/status" ou
"status", ele responde com um print atual + nivel/poder/XP -- uma mensagem
por conta configurada em settings.json["accounts"] (ou uma unica, no modo
legado sem contas configuradas).
"""
import logging
import time

import requests

from common import (
    TELEGRAM_CHAT_ID,
    TELEGRAM_TOKEN,
    account_slug,
    extract_stats,
    format_stats_text,
    get_frame,
    load_settings,
    save_snapshot,
    send_telegram_photo,
    set_account,
)

API_URL = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"
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


def send_status(window_title: str, account_id: str, label: str):
    set_account(account_id)
    full = get_frame(window_title)
    snapshot_path = f"status_snapshot_{account_id}.jpg" if account_id else "status_snapshot.jpg"
    save_snapshot(snapshot_path, full)
    stats = format_stats_text(extract_stats(full))
    prefix = f"[{label}] " if label else ""
    send_telegram_photo(snapshot_path, f"{prefix}Status atual:\n\n{stats}", log=log)


def handle_status_command():
    accounts = load_settings().get("accounts", [])
    if not accounts:
        send_status(None, "", "")
        return
    for acc in accounts:
        label = acc.get("label", "")
        send_status(acc.get("window_title", ""), account_slug(label), label)


def main():
    initial = get_updates()
    offset = (initial[-1]["update_id"] + 1) if initial else None
    log.info("Ouvindo comandos no Telegram... (Ctrl+C para parar)")

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
                    handle_status_command()

        except KeyboardInterrupt:
            log.info("Encerrando.")
            break
        except requests.RequestException as exc:
            log.error(f"[erro] {exc}")
            time.sleep(5)


if __name__ == "__main__":
    main()
