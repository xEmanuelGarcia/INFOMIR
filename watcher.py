"""
Fica de olho na regiao calibrada (config.json / templates/death_template.png).
Quando a tela de morte do MIR4 aparecer, manda uma mensagem no Telegram.
So dispara de novo depois que a tela de morte sumir (evita spam).

Requisitos: rode "python calibrate.py" antes, pelo menos uma vez.
"""
import json
import logging
import os
import time

import cv2
import mss
import numpy as np

from common import (
    COPPER_FEED_REGION,
    MISSION_REGION,
    MONITOR_INDEX,
    PERIODIC_REPORT_SECONDS,
    QUEST_NOTIFICATIONS_ENABLED,
    QUEST_ICON_REGION,
    QUEST_NAME_REGION,
    QUEST_OBJECTIVE_REGION,
    VIGOR_LOW_THRESHOLD_MINUTES,
    VIGOR_REGION,
    ZONE_REGION,
    check_primary_quest_progress,
    check_quest_icon_completion,
    extract_stats,
    read_quest_name,
    read_quest_objective,
    format_stats_text,
    format_vigor,
    is_death_alert_armed,
    is_mission_alert_armed,
    is_mission_complete_banner_visible,
    is_periodic_report_due,
    is_vigor_alert_armed,
    mark_periodic_report_sent,
    parse_vigor_minutes,
    read_vigor_text,
    read_zone_text,
    record_copper_tick,
    resolve_vigor_minutes,
    resolve_zone,
    save_snapshot,
    send_telegram_photo,
    set_death_alerted,
    set_mission_alerted,
    set_vigor_alerted,
)

CONFIG_PATH = "config.json"
TEMPLATE_PATH = "templates/death_template.png"
LOG_PATH = "watcher.log"
HISTORY_DIR = "history"
HISTORY_SCORE_THRESHOLD = 0.25
HISTORY_MAX_FILES = 30
DEATH_SNAPSHOT_PATH = "death_snapshot.jpg"
PERIODIC_SNAPSHOT_PATH = "periodic_snapshot.jpg"
VIGOR_SNAPSHOT_PATH = "vigor_snapshot.jpg"
MISSION_SNAPSHOT_PATH = "mission_snapshot.jpg"
QUEST_SNAPSHOT_PATH = "quest_snapshot.jpg"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[logging.FileHandler(LOG_PATH, encoding="utf-8"), logging.StreamHandler()],
)
log = logging.getLogger(__name__)


def load_config():
    if not os.path.exists(CONFIG_PATH):
        raise SystemExit("config.json nao encontrado. Rode 'python calibrate.py' primeiro.")
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def similarity(search_img, template_img) -> float:
    result = cv2.matchTemplate(search_img, template_img, cv2.TM_CCOEFF_NORMED)
    _, max_val, _, _ = cv2.minMaxLoc(result)
    return float(max_val)


def save_evidence(sct, score: float):
    os.makedirs(HISTORY_DIR, exist_ok=True)
    full = np.array(sct.grab(sct.monitors[MONITOR_INDEX]))[:, :, :3]
    stamp = time.strftime("%Y%m%d_%H%M%S")
    cv2.imwrite(os.path.join(HISTORY_DIR, f"{stamp}_score{score:.2f}.png"), full)

    files = sorted(
        (os.path.join(HISTORY_DIR, f) for f in os.listdir(HISTORY_DIR)),
        key=os.path.getmtime,
    )
    for old_file in files[:-HISTORY_MAX_FILES]:
        try:
            os.remove(old_file)
        except OSError:
            pass  # arquivo pode estar temporariamente em uso (ex: sendo lido)


def main():
    config = load_config()
    template = cv2.imread(TEMPLATE_PATH, cv2.IMREAD_COLOR)
    if template is None:
        raise SystemExit(f"Nao consegui carregar {TEMPLATE_PATH}.")

    region = config["region"]
    enter_threshold = config["enter_threshold"]
    exit_threshold = config["exit_threshold"]
    poll_interval = config["poll_interval_seconds"]

    monitor = {
        "left": region["left"],
        "top": region["top"],
        "width": region["width"],
        "height": region["height"],
    }

    log.info("Monitorando... (Ctrl+C para parar)")

    with mss.MSS() as sct:
        while True:
            try:
                shot = sct.grab(monitor)
                frame = np.array(shot)[:, :, :3]
                score = similarity(frame, template)
                log.info(f"score={score:.2f} is_dead={not is_death_alert_armed()}")

                feed_crop = np.array(sct.grab(COPPER_FEED_REGION))[:, :, :3]
                record_copper_tick(feed_crop)

                zone_crop = np.array(sct.grab(ZONE_REGION))[:, :, :3]
                resolve_zone(read_zone_text(zone_crop))

                vigor_crop = np.array(sct.grab(VIGOR_REGION))[:, :, :3]
                vigor_minutes = resolve_vigor_minutes(parse_vigor_minutes(read_vigor_text(vigor_crop)))
                if vigor_minutes is not None:
                    if vigor_minutes <= VIGOR_LOW_THRESHOLD_MINUTES and is_vigor_alert_armed():
                        set_vigor_alerted(True)
                        log.info(f"[vigor baixo] {vigor_minutes:.1f} min -> enviando Telegram")
                        full = np.array(sct.grab(sct.monitors[MONITOR_INDEX]))[:, :, :3]
                        save_snapshot(VIGOR_SNAPSHOT_PATH, full)
                        stats = format_stats_text(extract_stats(full))
                        send_telegram_photo(
                            VIGOR_SNAPSHOT_PATH,
                            f"Vigor quase acabando ({format_vigor(vigor_minutes)})!\n\n{stats}",
                            log=log,
                        )
                    elif vigor_minutes > VIGOR_LOW_THRESHOLD_MINUTES and not is_vigor_alert_armed():
                        set_vigor_alerted(False)

                mission_crop = np.array(sct.grab(MISSION_REGION))[:, :, :3]
                mission_visible = is_mission_complete_banner_visible(mission_crop)
                if mission_visible and is_mission_alert_armed():
                    set_mission_alerted(True)
                    log.info("[missao concluida] -> enviando Telegram")
                    full = np.array(sct.grab(sct.monitors[MONITOR_INDEX]))[:, :, :3]
                    save_snapshot(MISSION_SNAPSHOT_PATH, full)
                    stats = format_stats_text(extract_stats(full))
                    send_telegram_photo(
                        MISSION_SNAPSHOT_PATH,
                        f"Missao concluida no MIR4!\n\n{stats}",
                        log=log,
                    )
                elif not mission_visible and not is_mission_alert_armed():
                    set_mission_alerted(False)

                if QUEST_NOTIFICATIONS_ENABLED:
                    quest_name_crop = np.array(sct.grab(QUEST_NAME_REGION))[:, :, :3]
                    quest_obj_crop = np.array(sct.grab(QUEST_OBJECTIVE_REGION))[:, :, :3]
                    quest_icon_crop = np.array(sct.grab(QUEST_ICON_REGION))[:, :, :3]

                    quest_result = check_primary_quest_progress(quest_name_crop, quest_obj_crop)
                    icon_completed = check_quest_icon_completion(quest_icon_crop)

                    if quest_result or icon_completed:
                        if quest_result:
                            quest_name, quest_objective = quest_result
                        else:
                            quest_name = read_quest_name(quest_name_crop)
                            quest_objective, _ = read_quest_objective(quest_obj_crop)
                        log.info(f"[missao primaria] {quest_objective} -> enviando Telegram")
                        full = np.array(sct.grab(sct.monitors[MONITOR_INDEX]))[:, :, :3]
                        save_snapshot(QUEST_SNAPSHOT_PATH, full)
                        stats = format_stats_text(extract_stats(full))
                        send_telegram_photo(
                            QUEST_SNAPSHOT_PATH,
                            f"Objetivo concluido: {quest_name} - {quest_objective}\n\n{stats}",
                            log=log,
                        )

                if is_periodic_report_due(PERIODIC_REPORT_SECONDS):
                    mark_periodic_report_sent()
                    log.info("[relatorio periodico] enviando Telegram")
                    full = np.array(sct.grab(sct.monitors[MONITOR_INDEX]))[:, :, :3]
                    save_snapshot(PERIODIC_SNAPSHOT_PATH, full)
                    stats = format_stats_text(extract_stats(full))
                    send_telegram_photo(PERIODIC_SNAPSHOT_PATH, f"Status periodico:\n\n{stats}", log=log)

                if score >= HISTORY_SCORE_THRESHOLD:
                    save_evidence(sct, score)

                if is_death_alert_armed() and score >= enter_threshold:
                    set_death_alerted(True)
                    log.info(f"[morte detectada] score={score:.2f} -> enviando Telegram")
                    full = np.array(sct.grab(sct.monitors[MONITOR_INDEX]))[:, :, :3]
                    save_snapshot(DEATH_SNAPSHOT_PATH, full)
                    stats = format_stats_text(extract_stats(full))
                    send_telegram_photo(
                        DEATH_SNAPSHOT_PATH,
                        f"Voce morreu no MIR4! Volta la pra ressuscitar e continuar upando.\n\n{stats}",
                        log=log,
                    )
                elif not is_death_alert_armed() and score <= exit_threshold:
                    set_death_alerted(False)
                    log.info(f"[ressuscitado] score={score:.2f}")

            except KeyboardInterrupt:
                log.info("Encerrando.")
                break
            except Exception as exc:
                log.error(f"[erro] {exc}")

            time.sleep(poll_interval)


if __name__ == "__main__":
    main()
