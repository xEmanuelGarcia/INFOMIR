"""
Fica de olho na janela do MIR4. Quando a tela de morte aparecer, manda uma
mensagem no Telegram. So dispara de novo depois que a tela de morte sumir
(evita spam). Nao precisa de calibracao manual -- todas as regioes (incluindo
a deteccao de morte) sao relativas ao HUD do jogo e escalam automaticamente.

Pra monitorar mais de uma conta ao mesmo tempo, cada instancia roda com um
account_id (ex: "python watcher.py conta_1") que aponta pra uma entrada em
settings.json["accounts"] -- cada uma mira sua propria janela e grava estado
(morte/vigor/missao/etc.) em arquivos separados, pra nao se misturarem.
"""
import logging
import sys
import time

from common import (
    PERIODIC_REPORT_SECONDS,
    QUEST_NOTIFICATIONS_ENABLED,
    VIGOR_LOW_THRESHOLD_MINUTES,
    account_slug,
    check_primary_quest_progress,
    check_quest_icon_completion,
    crop_region,
    extract_stats,
    get_frame,
    get_regions,
    get_vigor_region,
    is_death_screen_visible,
    load_settings,
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
    resolve_death_state,
    resolve_vigor_minutes,
    resolve_zone,
    save_snapshot,
    send_telegram_photo,
    set_account,
    set_death_alerted,
    set_mission_alerted,
    set_vigor_alerted,
)

POLL_INTERVAL_SECONDS = 1.5


def resolve_account(account_id: str):
    """Acha a conta configurada com esse id (slug do rotulo em
    settings.json["accounts"]). Retorna (window_title, label); ambos "" no
    modo legado (account_id vazio) ou se a conta nao for mais encontrada
    na configuracao (window_title=None faz get_frame cair no fallback)."""
    if not account_id:
        return None, ""
    for acc in load_settings().get("accounts", []):
        if account_slug(acc.get("label", "")) == account_id:
            return acc.get("window_title", ""), acc.get("label", "")
    return None, ""


def main(account_id: str = ""):
    window_title, label = resolve_account(account_id)
    set_account(account_id)
    suffix = f"_{account_id}" if account_id else ""
    prefix = f"[{label}] " if label else ""

    log = logging.getLogger(f"watcher{suffix}")
    log.setLevel(logging.INFO)
    handler = logging.FileHandler(f"watcher{suffix}.log", encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(message)s", datefmt="%Y-%m-%d %H:%M:%S"))
    log.addHandler(handler)
    log.addHandler(logging.StreamHandler())

    death_snapshot_path = f"death_snapshot{suffix}.jpg"
    periodic_snapshot_path = f"periodic_snapshot{suffix}.jpg"
    vigor_snapshot_path = f"vigor_snapshot{suffix}.jpg"
    mission_snapshot_path = f"mission_snapshot{suffix}.jpg"
    quest_snapshot_path = f"quest_snapshot{suffix}.jpg"

    log.info(f"Monitorando{' ' + label if label else ''}... (Ctrl+C para parar)")

    while True:
        try:
            # recalculada a cada volta -- a janela do jogo pode ainda nao ter
            # aberto quando o watcher iniciou, ou pode ter sido movida (ou
            # coberta por outra janela -- get_frame pega o conteudo real dela
            # mesmo assim, ver gfx_capture.py)
            full = get_frame(window_title)
            regions = get_regions(full)

            is_dead_now = is_death_screen_visible(full)
            confirmed_dead = resolve_death_state(is_dead_now)
            log.info(f"is_dead={confirmed_dead}")

            feed_crop = crop_region(full, regions["copper_feed"])
            record_copper_tick(feed_crop)

            zone_crop = crop_region(full, regions["zone"])
            resolve_zone(read_zone_text(zone_crop))

            vigor_crop = crop_region(full, get_vigor_region(full))
            vigor_minutes = resolve_vigor_minutes(parse_vigor_minutes(read_vigor_text(vigor_crop)))
            if vigor_minutes is not None:
                if vigor_minutes <= VIGOR_LOW_THRESHOLD_MINUTES and is_vigor_alert_armed():
                    set_vigor_alerted(True)
                    log.info(f"[vigor baixo] {vigor_minutes:.1f} min -> enviando Telegram")
                    save_snapshot(vigor_snapshot_path, full)
                    stats = format_stats_text(extract_stats(full))
                    send_telegram_photo(
                        vigor_snapshot_path,
                        f"{prefix}Vigor quase acabando ({format_vigor(vigor_minutes)})!\n\n{stats}",
                        log=log,
                    )
                elif vigor_minutes > VIGOR_LOW_THRESHOLD_MINUTES and not is_vigor_alert_armed():
                    set_vigor_alerted(False)

            mission_crop = crop_region(full, regions["mission"])
            mission_visible = is_mission_complete_banner_visible(mission_crop)
            if mission_visible and is_mission_alert_armed():
                set_mission_alerted(True)
                log.info("[missao concluida] -> enviando Telegram")
                save_snapshot(mission_snapshot_path, full)
                stats = format_stats_text(extract_stats(full))
                send_telegram_photo(
                    mission_snapshot_path,
                    f"{prefix}Missao concluida no MIR4!\n\n{stats}",
                    log=log,
                )
            elif not mission_visible and not is_mission_alert_armed():
                set_mission_alerted(False)

            if QUEST_NOTIFICATIONS_ENABLED:
                quest_name_crop = crop_region(full, regions["quest_name"])
                quest_obj_crop = crop_region(full, regions["quest_objective"])
                quest_icon_crop = crop_region(full, regions["quest_icon"])

                quest_result = check_primary_quest_progress(quest_name_crop, quest_obj_crop)
                icon_completed = check_quest_icon_completion(quest_icon_crop)

                if quest_result or icon_completed:
                    if quest_result:
                        quest_name, quest_objective = quest_result
                    else:
                        quest_name = read_quest_name(quest_name_crop)
                        quest_objective, _ = read_quest_objective(quest_obj_crop)
                    log.info(f"[missao primaria] {quest_objective} -> enviando Telegram")
                    save_snapshot(quest_snapshot_path, full)
                    stats = format_stats_text(extract_stats(full))
                    send_telegram_photo(
                        quest_snapshot_path,
                        f"{prefix}Objetivo concluido: {quest_name} - {quest_objective}\n\n{stats}",
                        log=log,
                    )

            if is_periodic_report_due(PERIODIC_REPORT_SECONDS):
                mark_periodic_report_sent()
                log.info("[relatorio periodico] enviando Telegram")
                save_snapshot(periodic_snapshot_path, full)
                stats = format_stats_text(extract_stats(full))
                send_telegram_photo(periodic_snapshot_path, f"{prefix}Status periodico:\n\n{stats}", log=log)

            if confirmed_dead and is_death_alert_armed():
                set_death_alerted(True)
                log.info("[morte detectada] -> enviando Telegram")
                save_snapshot(death_snapshot_path, full)
                stats = format_stats_text(extract_stats(full))
                send_telegram_photo(
                    death_snapshot_path,
                    f"{prefix}Voce morreu no MIR4! Volta la pra ressuscitar e continuar upando.\n\n{stats}",
                    log=log,
                )
            elif not confirmed_dead and not is_death_alert_armed():
                set_death_alerted(False)
                log.info("[ressuscitado]")

        except KeyboardInterrupt:
            log.info("Encerrando.")
            break
        except Exception as exc:
            log.error(f"[erro] {exc}")

        time.sleep(POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    main(*sys.argv[1:])
