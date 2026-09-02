"""Funcoes compartilhadas entre watcher.py e telegram_listener.py."""
import difflib
import json
import os
import re
import time

import cv2
import mss
import numpy as np
import pytesseract
import requests
from dotenv import load_dotenv

load_dotenv()
# .get() em vez de [] -- numa instalacao nova o .env ainda nao existe, e o
# painel (launcher.py) precisa conseguir abrir mesmo assim pra pedir essas
# credenciais na aba Telegram, em vez de travar com KeyError na importacao.
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

SETTINGS_PATH = "settings.json"
SETTINGS_DEFAULTS = {
    "vigor_low_threshold_minutes": 15,
    "periodic_report_minutes": 30,
    "quest_notifications_enabled": True,
}


def load_settings() -> dict:
    settings = dict(SETTINGS_DEFAULTS)
    if os.path.exists(SETTINGS_PATH):
        with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
            settings.update(json.load(f))
    return settings


def save_settings(settings: dict):
    merged = load_settings()
    merged.update(settings)
    with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
        json.dump(merged, f, indent=2, ensure_ascii=False)


_settings = load_settings()

MONITOR_INDEX = 1

# Todas as regiões abaixo foram calibradas olhando a tela numa resolução de
# referência (1920x1080). Como o layout do HUD do MIR4 é sempre o mesmo --
# só muda de tamanho com a resolução --, guardamos os valores calibrados
# nessa referência e escalamos pra resolução real da tela em tempo de
# execução, em vez de fixar pixels absolutos. Numa tela 1920x1080 o fator de
# escala é 1.0 (nenhuma mudança de comportamento); numa tela diferente, tudo
# escala proporcionalmente.
_REFERENCE_WIDTH = 1920
_REFERENCE_HEIGHT = 1080


def _detect_screen_size():
    try:
        with mss.mss() as sct:
            monitor = sct.monitors[MONITOR_INDEX]
            return monitor["width"], monitor["height"]
    except Exception:
        return _REFERENCE_WIDTH, _REFERENCE_HEIGHT


SCREEN_WIDTH, SCREEN_HEIGHT = _detect_screen_size()
_SCALE_X = SCREEN_WIDTH / _REFERENCE_WIDTH
_SCALE_Y = SCREEN_HEIGHT / _REFERENCE_HEIGHT


def _region(left, top, width, height) -> dict:
    """Recebe coordenadas calibradas na resolucao de referencia e devolve o
    recorte correspondente escalado pra resolucao real da tela atual."""
    return {
        "left": round(left * _SCALE_X),
        "top": round(top * _SCALE_Y),
        "width": round(width * _SCALE_X),
        "height": round(height * _SCALE_Y),
    }


def scale_x(value):
    return round(value * _SCALE_X)


def scale_y(value):
    return round(value * _SCALE_Y)


JPEG_QUALITY = 85
TESSERACT_PATH = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
XP_STATE_PATH = "xp_state.json"
COPPER_STATE_PATH = "copper_state.json"
COPPER_FEED_REGION = _region(0, 985, 300, 95)
ZONE_REGION = _region(1610, 88, 300, 20)
ZONES_STATE_PATH = "known_zones.json"
ZONE_MATCH_THRESHOLD = 0.84
ZONE_CONFIRM_THRESHOLD = 0.6
ZONE_PENDING_CONFIRM_COUNT = 3
ZONE_MIN_LENGTH = 8
VIGOR_REGION = _region(138, 104, 24, 13)
VIGOR_LOW_THRESHOLD_MINUTES = _settings["vigor_low_threshold_minutes"]
PERIODIC_REPORT_SECONDS = _settings["periodic_report_minutes"] * 60
QUEST_NOTIFICATIONS_ENABLED = _settings["quest_notifications_enabled"]
VIGOR_MAX_PLAUSIBLE_MINUTES = 48 * 60
VIGOR_TOLERANCE_MINUTES = 2
VIGOR_STATE_PATH = "vigor_state.json"
DEATH_STATE_PATH = "death_state.json"
LAST_STATS_PATH = "last_stats.json"
PERIODIC_STATE_PATH = "periodic_state.json"
MISSION_REGION = _region(1610, 215, 310, 43)
MISSION_STATE_PATH = "mission_state.json"
QUEST_NAME_REGION = _region(1640, 152, 280, 28)
QUEST_OBJECTIVE_REGION = _region(1640, 178, 280, 32)
QUEST_STATE_PATH = "quest_state.json"
QUEST_ICON_REGION = _region(1650, 148, 35, 32)
QUEST_GLOW_PIXEL_THRESHOLD = round(30 * _SCALE_X * _SCALE_Y)
EXP_SEARCH_REGION = _region(0, 1020, 260, 60)
LEVEL_POWER_REGION = _region(0, 0, 230, 40)
LEVEL_MIN = 1
LEVEL_MAX = 200
POWER_TOLERANCE_RATIO = 0.5

pytesseract.pytesseract.tesseract_cmd = TESSERACT_PATH


def _load_json(path, default):
    if not os.path.exists(path):
        return default
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f)


def save_snapshot(path: str, img):
    """Salva como JPEG comprimido -- PNG de 1920x1080 fica uns 4-5MB, o que
    trava/estoura timeout em uploads pro Telegram numa conexao mais lenta."""
    cv2.imwrite(path, img, [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY])


def send_telegram_message(text: str, log=None):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        resp = requests.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "text": text}, timeout=10)
        resp.raise_for_status()
    except requests.RequestException as exc:
        if log:
            log.error(f"falha ao enviar mensagem no Telegram: {exc}")


def send_telegram_photo(image_path: str, caption: str, log=None):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto"
    for attempt in range(2):
        try:
            with open(image_path, "rb") as photo:
                resp = requests.post(
                    url,
                    data={"chat_id": TELEGRAM_CHAT_ID, "caption": caption},
                    files={"photo": photo},
                    timeout=60,
                )
            resp.raise_for_status()
            return
        except requests.RequestException as exc:
            if attempt == 0:
                if log:
                    log.error(f"falha ao enviar print no Telegram (tentando de novo): {exc}")
                continue
            if log:
                log.error(f"falha ao enviar print no Telegram: {exc}")


_FLOOR_RE = re.compile(r"^\[?(\d{1,2}F)\]?\s*(.*)$", re.IGNORECASE)
_ROMAN_SUFFIX_RE = re.compile(r"^(.*?)\s+([IVXL]{1,4})$", re.IGNORECASE)  # 'l' = confusao comum de OCR com 'I'


def _normalize_roman(token: str) -> str:
    return token.upper().replace("L", "I")


def _zone_similarity(a: str, b: str) -> float:
    """Compara dois nomes de mapa. Se ambos tem prefixo de andar (1F, 2F, ...)
    e/ou sufixo de instancia em numeral romano (Sala Magica I, II, III...), esses
    marcadores precisam bater exatamente -- senao 'Xf da Mina' e '2F da Mina', ou
    'Sala I' e 'Sala II', ficam quase identicos por similaridade de texto e um
    andar/instancia errado vira 'correcao' do outro. So o resto do nome (sem
    esses marcadores) e comparado por similaridade."""
    ma, mb = _FLOOR_RE.match(a), _FLOOR_RE.match(b)
    if ma and mb:
        if ma.group(1).upper() != mb.group(1).upper():
            return 0.0
        rest_a, rest_b = ma.group(2), mb.group(2)
    else:
        rest_a, rest_b = a, b

    ra, rb = _ROMAN_SUFFIX_RE.match(rest_a), _ROMAN_SUFFIX_RE.match(rest_b)
    if ra and rb:
        if _normalize_roman(ra.group(2)) != _normalize_roman(rb.group(2)):
            return 0.0
        rest_a, rest_b = ra.group(1), rb.group(1)

    return difflib.SequenceMatcher(None, rest_a.lower(), rest_b.lower()).ratio()


def resolve_zone(raw_text: str) -> str:
    """Compara a leitura atual com mapas ja vistos antes. Se a leitura parecer
    incompleta (ex: notificacao tampando o nome), usa o ultimo mapa valido.
    Se for parecida com um mapa conhecido, corrige erros de OCR usando o nome salvo.
    Uma leitura que nao bate com nenhum mapa conhecido so vira "mapa novo" depois
    de aparecer parecida 2 vezes seguidas -- ruido de OCR aleatorio raramente se
    repete do mesmo jeito duas vezes, um mapa novo de verdade sim."""
    state = _load_json(ZONES_STATE_PATH, {"known": [], "last_zone": None, "pending": None, "pending_count": 0})
    known = state.get("known", [])
    last_zone = state.get("last_zone")
    pending = state.get("pending")
    pending_count = state.get("pending_count", 0)

    real_words = re.findall(r"[A-Za-zÀ-ÿ]{4,}", raw_text)
    broken_floor = bool(re.match(r"^\[?S?F\]?\s", raw_text))  # "F"/"[SF]" = andar sem digito, causa raiz recorrente
    is_plausible = (
        bool(raw_text) and len(raw_text) >= ZONE_MIN_LENGTH and len(real_words) >= 2 and not broken_floor
    )
    if not is_plausible:
        return last_zone or (raw_text or "?")

    best_match, best_ratio = None, 0.0
    for candidate in known:
        ratio = _zone_similarity(raw_text, candidate)
        if ratio > best_ratio:
            best_match, best_ratio = candidate, ratio

    if best_match and best_ratio >= ZONE_MATCH_THRESHOLD:
        state["last_zone"] = best_match
        state["pending"] = None
        state["pending_count"] = 0
        _save_json(ZONES_STATE_PATH, state)
        return best_match

    if pending and _zone_similarity(raw_text, pending) >= ZONE_CONFIRM_THRESHOLD:
        pending_count += 1
    else:
        pending = raw_text
        pending_count = 1

    if pending_count >= ZONE_PENDING_CONFIRM_COUNT:
        known = (known + [pending])[-50:]
        state["known"] = known
        state["last_zone"] = pending
        state["pending"] = None
        state["pending_count"] = 0
        _save_json(ZONES_STATE_PATH, state)
        return pending

    state["pending"] = pending
    state["pending_count"] = pending_count
    _save_json(ZONES_STATE_PATH, state)
    return last_zone or raw_text


def clean_zone_name(text: str) -> str:
    """Tira o selo de estado do mapa (Danger/COMN/Special/Safe etc, sempre no
    inicio) e o canal/instancia (sempre no final), deixando so o nome."""
    text = re.sub(
        r"^\s*[\(\[]?\s*(Da\s*nger|COMN|Comum|Special|Safe|Seguro)\s*[\)\]\|]?\s*",
        "",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(r"\s*[\|\-–—“”]?\s*(Canal.*|.nico|Unico)\s*$", "", text, flags=re.IGNORECASE)
    text = re.sub(r"^[^A-Za-zÀ-ÿ\[]+", "", text)
    text = re.sub(r"^[A-Za-zÀ-ÿ](?=\d{1,2}F)", "", text)  # letra solta antes do andar, ex: "G6F"
    return re.sub(r"\s+", " ", text).strip(" |")


def read_zone_text(zone_crop_img) -> str:
    gray = cv2.cvtColor(zone_crop_img, cv2.COLOR_BGR2GRAY)
    big = cv2.resize(gray, None, fx=4, fy=4, interpolation=cv2.INTER_CUBIC)
    text = pytesseract.image_to_string(big, lang="por", config="--psm 7")
    return clean_zone_name(text)


def extract_zone(full_frame) -> str:
    z = ZONE_REGION
    crop = full_frame[z["top"]:z["top"] + z["height"], z["left"]:z["left"] + z["width"]]
    return resolve_zone(read_zone_text(crop))


def extract_exp_pct(full_frame):
    """XP% fica escrito em texto ciano bem colado numa barra ciano solida, o que
    confunde o OCR direto. A posicao vertical desse texto nao e fixa: quando tem
    mais mensagens empilhadas acima (Exp/Cobre ganhos), ele sobe na tela. Por
    isso procuramos a barra (linha quase 100% ciano) numa faixa maior e lemos
    o texto logo acima dela, em vez de usar coordenadas fixas."""
    s = EXP_SEARCH_REGION
    search = full_frame[s["top"]:s["top"] + s["height"], s["left"]:s["left"] + s["width"]]
    b, g, r = cv2.split(search.astype(np.int16))
    cyan = ((b > 150) & (g > 150) & (r < 120)).astype(np.uint8)

    row_density = cyan.sum(axis=1)
    bar_rows = np.where(row_density > 0.75 * s["width"])[0]
    if len(bar_rows) == 0:
        return None
    bar_top = int(bar_rows[0])
    text_top = max(0, bar_top - scale_y(18))
    text_bottom = max(text_top + 1, bar_top - 1)

    mask = cyan[text_top:text_bottom] * 255
    big = cv2.resize(mask, None, fx=5, fy=5, interpolation=cv2.INTER_CUBIC)
    text = pytesseract.image_to_string(big, config="--psm 7 -c tessedit_char_whitelist=0123456789.%EXP")
    match = re.search(r"(\d{1,3}\.\d+)\s*%", text)
    if not match:
        return None
    value = float(match.group(1))
    return value if 0 <= value <= 100 else None


def read_vigor_text(vigor_crop_img) -> str:
    """Le o texto do icone de vigor (formato '7H' ou '05:58'). O icone e um
    badge circular, entao o recorte precisa ser bem justo pra nao pegar a borda."""
    gray = cv2.cvtColor(vigor_crop_img, cv2.COLOR_BGR2GRAY)
    mask = (gray > 110).astype(np.uint8) * 255
    big = cv2.resize(mask, None, fx=8, fy=8, interpolation=cv2.INTER_CUBIC)
    return pytesseract.image_to_string(
        big, config="--psm 7 -c tessedit_char_whitelist=0123456789HM:"
    ).strip()


def parse_vigor_minutes(text: str):
    h_match = re.match(r"^(\d+)\s*H$", text)
    if h_match:
        return int(h_match.group(1)) * 60

    mmss_match = re.match(r"^(\d{1,2}):([0-5]\d)$", text)
    if mmss_match:
        return int(mmss_match.group(1)) + int(mmss_match.group(2)) / 60

    return None


def format_vigor(minutes) -> str:
    if minutes is None:
        return "?"
    if minutes >= 60:
        return f"{int(minutes // 60)}H"
    m = int(minutes)
    s = int(round((minutes - m) * 60))
    return f"{m:02d}:{s:02d}"


def resolve_vigor_minutes(raw_minutes):
    """Valida a leitura contra o valor esperado (vigor so decai com o tempo, nao
    oscila). O formato 'MM:SS' usado quando o vigor esta baixo e pequeno demais
    pro OCR ler de forma 100% confiavel, entao uma leitura que destoa muito do
    esperado (ruido, ou uma recarga de vigor de verdade) so e aceita se repetir
    parecida na proxima leitura. Se nada bater, estima pelo tempo decorrido."""
    state = _load_json(
        VIGOR_STATE_PATH, {"minutes": None, "timestamp": None, "alerted": False, "pending": None}
    )
    now = time.time()

    expected = None
    if state.get("minutes") is not None and state.get("timestamp") is not None:
        elapsed_minutes = (now - state["timestamp"]) / 60
        expected = max(0.0, state["minutes"] - elapsed_minutes)

    if raw_minutes is not None and 0 <= raw_minutes <= VIGOR_MAX_PLAUSIBLE_MINUTES:
        pending = state.get("pending")
        consistent = expected is None or abs(raw_minutes - expected) <= VIGOR_TOLERANCE_MINUTES
        confirmed = pending is not None and abs(raw_minutes - pending) <= VIGOR_TOLERANCE_MINUTES

        if consistent or confirmed:
            state["minutes"] = raw_minutes
            state["timestamp"] = now
            state["pending"] = None
            _save_json(VIGOR_STATE_PATH, state)
            return raw_minutes

        state["pending"] = raw_minutes
        _save_json(VIGOR_STATE_PATH, state)

    return expected


def is_vigor_alert_armed() -> bool:
    """True quando o alerta de vigor baixo ainda nao foi disparado pra
    leitura atual (persistido em disco, sobrevive a reinicios do watcher)."""
    return not _load_json(VIGOR_STATE_PATH, {}).get("alerted", False)


def set_vigor_alerted(value: bool):
    state = _load_json(VIGOR_STATE_PATH, {"minutes": None, "timestamp": None, "alerted": False})
    state["alerted"] = value
    _save_json(VIGOR_STATE_PATH, state)


def is_death_alert_armed() -> bool:
    """True quando o alerta de morte ainda nao foi disparado pra este estado
    (persistido em disco, sobrevive a reinicios do watcher)."""
    return not _load_json(DEATH_STATE_PATH, {}).get("is_dead", False)


def set_death_alerted(value: bool):
    _save_json(DEATH_STATE_PATH, {"is_dead": value})


def is_periodic_report_due(interval_seconds: float) -> bool:
    """Persistido em disco (nao so na memoria do processo) pra reinicios do
    watcher nao empurrarem o proximo envio pra frente toda vez."""
    state = _load_json(PERIODIC_STATE_PATH, None)
    now = time.time()
    if state is None:
        _save_json(PERIODIC_STATE_PATH, {"last_sent": now})
        return False
    return (now - state.get("last_sent", now)) >= interval_seconds


def mark_periodic_report_sent():
    _save_json(PERIODIC_STATE_PATH, {"last_sent": time.time()})


def is_mission_complete_banner_visible(mission_crop_img) -> bool:
    """O banner 'Jogar autom. a missao concluida' e passageiro (aparece e some
    sozinho depois de alguns segundos), entao a checagem e feita a cada tick."""
    gray = cv2.cvtColor(mission_crop_img, cv2.COLOR_BGR2GRAY)
    big = cv2.resize(gray, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC)
    text = pytesseract.image_to_string(big, lang="por", config="--psm 7")
    return "conclu" in text.lower()


def is_mission_alert_armed() -> bool:
    return not _load_json(MISSION_STATE_PATH, {}).get("alerted", False)


def set_mission_alerted(value: bool):
    _save_json(MISSION_STATE_PATH, {"alerted": value})


def read_quest_name(name_crop_img) -> str:
    gray = cv2.cvtColor(name_crop_img, cv2.COLOR_BGR2GRAY)
    big = cv2.resize(gray, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC)
    text = pytesseract.image_to_string(big, lang="por", config="--psm 7")
    text = re.sub(r"^[^A-Za-zÀ-ÿ]+", "", text)  # tira o icone "!" lido como lixo
    return re.sub(r"\s+", " ", text).strip()


def read_quest_objective(objective_crop_img):
    """Retorna o texto do objetivo atual e, se tiver contador tipo '3/5', a
    tupla (atual, alvo)."""
    gray = cv2.cvtColor(objective_crop_img, cv2.COLOR_BGR2GRAY)
    big = cv2.resize(gray, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC)
    text = pytesseract.image_to_string(big, lang="por", config="--psm 7")
    text = re.sub(r"^[^A-Za-z0-9À-ÿ]+", "", text).strip()
    text = re.sub(r"\s+", " ", text)

    match = re.search(r"(\d+)\s*/\s*(\d+)", text)
    progress = (int(match.group(1)), int(match.group(2))) if match else None
    return text, progress


QUEST_SAME_THRESHOLD = 0.75
QUEST_CONFIRM_THRESHOLD = 0.55


def is_quest_icon_glowing(icon_crop_img) -> bool:
    """O icone da missao tem uma borda azul brilhante enquanto o objetivo
    atual esta em andamento; a borda some quando ele e concluido."""
    b, g, r = cv2.split(icon_crop_img.astype(np.int16))
    glow_pixels = int(((b > 200) & (g > 150) & (r < 150)).sum())
    return glow_pixels > QUEST_GLOW_PIXEL_THRESHOLD


def check_quest_icon_completion(icon_crop_img):
    """Detecta a transicao 'brilhando -> sem brilho' (borda azul some), que
    indica que o objetivo atual da missao primaria foi concluido. Retorna
    True uma unica vez por transicao; None/False caso contrario."""
    glowing = is_quest_icon_glowing(icon_crop_img)
    state = _load_json(QUEST_STATE_PATH, {})
    was_glowing = state.get("icon_glowing")

    state["icon_glowing"] = glowing
    _save_json(QUEST_STATE_PATH, state)

    return was_glowing is True and glowing is False


def check_primary_quest_progress(name_crop_img, objective_crop_img):
    """Cobre qualquer tipo de objetivo (com ou sem contador). Dois sinais de
    conclusao: o contador bate o alvo (ex: '5/5', mais imediato quando existe),
    ou o texto do objetivo muda pra outro (o jogo avancou pro proximo passo --
    cobre objetivos sem contador tipo 'resgatar X'). A comparacao e por
    similaridade (nao igualdade exata), porque essa regiao tem OCR bem ruidoso
    e o mesmo objetivo raramente sai identico em duas leituras seguidas. Uma
    mudanca so e aceita depois de aparecer parecida 2x seguidas, pra nao
    disparar por ruido pontual. Retorna (nome, objetivo_novo) uma unica vez
    por transicao; None caso contrario."""
    objective_text, progress = read_quest_objective(objective_crop_img)
    state = _load_json(
        QUEST_STATE_PATH, {"last_objective": None, "alerted": False, "pending": None, "pending_count": 0}
    )
    last_objective = state.get("last_objective")

    is_plausible = bool(objective_text) and len(objective_text) >= 8

    if not is_plausible:
        return None

    if last_objective is None:
        state["last_objective"] = objective_text
        _save_json(QUEST_STATE_PATH, state)
        return None

    completed_by_counter = progress is not None and progress[0] >= progress[1] > 0
    same_ratio = difflib.SequenceMatcher(None, objective_text.lower(), last_objective.lower()).ratio()

    if same_ratio >= QUEST_SAME_THRESHOLD:
        if completed_by_counter and not state.get("alerted"):
            state["alerted"] = True
            _save_json(QUEST_STATE_PATH, state)
            return read_quest_name(name_crop_img), objective_text
        return None

    # parece diferente o suficiente pra ser mudanca real -- confirma 2x antes de aceitar
    pending = state.get("pending")
    if pending and difflib.SequenceMatcher(None, objective_text.lower(), pending.lower()).ratio() >= QUEST_CONFIRM_THRESHOLD:
        pending_count = state.get("pending_count", 0) + 1
    else:
        pending = objective_text
        pending_count = 1

    if pending_count >= 2:
        state["last_objective"] = objective_text
        state["alerted"] = False
        state["pending"] = None
        state["pending_count"] = 0
        _save_json(QUEST_STATE_PATH, state)
        return read_quest_name(name_crop_img), objective_text

    state["pending"] = pending
    state["pending_count"] = pending_count
    _save_json(QUEST_STATE_PATH, state)
    return None


def extract_vigor_minutes(full_frame):
    v = VIGOR_REGION
    crop = full_frame[v["top"]:v["top"] + v["height"], v["left"]:v["left"] + v["width"]]
    raw = parse_vigor_minutes(read_vigor_text(crop))
    return resolve_vigor_minutes(raw)


def extract_stats(full_frame) -> dict:
    lp = LEVEL_POWER_REGION
    lvl_power_crop = full_frame[lp["top"]:lp["top"] + lp["height"], lp["left"]:lp["left"] + lp["width"]]
    lvl_power_text = pytesseract.image_to_string(lvl_power_crop, lang="por")

    lvl_match = re.search(r"Nv\.?\s*(\d+)", lvl_power_text)
    power_match = re.search(r"(\d{1,3}(?:,\d{3})+|\d{4,})", lvl_power_text)

    level = int(lvl_match.group(1)) if lvl_match else None
    if level is not None and not (LEVEL_MIN <= level <= LEVEL_MAX):
        level = None  # implausivel -- nao deixa vazar pro calculo de xp/min

    return {
        "level": level,
        "power": power_match.group(1) if power_match else None,
        "exp_pct": extract_exp_pct(full_frame),
        "zone": extract_zone(full_frame),
        "vigor_minutes": extract_vigor_minutes(full_frame),
    }


def scan_copper_matches(feed_crop_img):
    text = pytesseract.image_to_string(feed_crop_img, lang="por")
    return re.findall(r"Cobre\s*\+\s*([\d,]+)", text)


def record_copper_tick(feed_crop_img):
    """Chamado a cada verificacao do watcher.py para acumular ganhos de cobre
    vistos no feed de mensagens, evitando contar a mesma linha duas vezes."""
    state = _load_json(COPPER_STATE_PATH, {"total": 0, "since": None, "seen": []})
    seen = state.get("seen", [])
    changed = state.get("since") is None
    if changed:
        state["since"] = time.time()

    for raw in scan_copper_matches(feed_crop_img):
        if raw not in seen:
            state["total"] = state.get("total", 0) + int(raw.replace(",", ""))
            seen.append(raw)
            seen = seen[-20:]
            changed = True

    if changed:
        state["seen"] = seen
        _save_json(COPPER_STATE_PATH, state)


def compute_and_reset_copper_rate():
    """Retorna cobre/minuto acumulado desde a ultima leitura e zera o contador."""
    now = time.time()
    state = _load_json(COPPER_STATE_PATH, {"total": 0, "since": None, "seen": []})

    if state.get("since") is None:
        state["since"] = now
        _save_json(COPPER_STATE_PATH, state)
        return None

    elapsed_minutes = (now - state["since"]) / 60
    if elapsed_minutes < 0.1:
        return None

    rate = state.get("total", 0) / elapsed_minutes
    state["total"] = 0
    state["since"] = now
    _save_json(COPPER_STATE_PATH, state)
    return rate


def compute_xp_per_minute(stats: dict):
    """Compara com a ultima leitura salva e retorna pontos percentuais de XP por minuto.
    Retorna None se nao houver leitura anterior ou se os dados atuais estiverem incompletos.
    Uma leitura atual ruim (OCR falhou) NAO sobrescreve o historico salvo, senao a
    proxima leitura boa tambem ficaria sem referencia pra comparar."""
    if stats["level"] is None or stats["exp_pct"] is None:
        return None

    now = time.time()
    previous = _load_json(XP_STATE_PATH, None)
    _save_json(XP_STATE_PATH, {"timestamp": now, "level": stats["level"], "exp_pct": stats["exp_pct"]})

    if not previous or previous.get("level") is None or previous.get("exp_pct") is None:
        return None

    elapsed_minutes = (now - previous["timestamp"]) / 60
    if elapsed_minutes < 0.1:
        return None

    level_diff = stats["level"] - previous["level"]
    if level_diff == 0:
        delta_pct = stats["exp_pct"] - previous["exp_pct"]
    elif level_diff > 0:
        delta_pct = (100 - previous["exp_pct"]) + stats["exp_pct"] + (level_diff - 1) * 100
    else:
        return None  # nivel diminuiu, leitura inconsistente

    return delta_pct / elapsed_minutes


def _is_plausible_level(level) -> bool:
    return level is not None and LEVEL_MIN <= level <= LEVEL_MAX


def _is_plausible_power(power_raw, cached_power_raw) -> bool:
    if power_raw is None:
        return False
    try:
        value = int(str(power_raw).replace(",", ""))
    except ValueError:
        return False
    if cached_power_raw is None:
        return True
    try:
        cached_value = int(str(cached_power_raw).replace(",", ""))
    except ValueError:
        return True
    if cached_value <= 0:
        return True
    ratio = value / cached_value
    return (1 - POWER_TOLERANCE_RATIO) <= ratio <= (1 + POWER_TOLERANCE_RATIO)


def fill_missing_stats(stats: dict) -> dict:
    """Preenche nivel/poder/XP% que falharam na leitura atual com o ultimo valor
    bom conhecido -- so pra exibicao. Algumas telas de morte (ex: certas areas
    PvP/raid) nao desenham o HUD principal, entao a leitura falha nao por erro
    de OCR, e sim porque a informacao simplesmente nao esta na tela.
    Tambem descarta leituras implausiveis (nivel fora da faixa do jogo, poder
    que destoa demais do ultimo valor bom) antes de aceitar ou cachear."""
    cached = _load_json(LAST_STATS_PATH, {})
    filled = dict(stats)

    if not _is_plausible_level(filled.get("level")):
        filled["level"] = None
    if not _is_plausible_power(filled.get("power"), cached.get("power")):
        filled["power"] = None

    for key in ("level", "power", "exp_pct"):
        if filled.get(key) is None and cached.get(key) is not None:
            filled[key] = cached[key]

    to_save = {k: filled[k] for k in ("level", "power", "exp_pct") if filled.get(k) is not None}
    if to_save:
        cached.update(to_save)
        _save_json(LAST_STATS_PATH, cached)

    return filled


def format_stats_text(stats: dict) -> str:
    xp_rate = compute_xp_per_minute(stats)
    copper_rate = compute_and_reset_copper_rate()

    display = fill_missing_stats(stats)
    level = display["level"] if display["level"] is not None else "?"
    power = display["power"] if display["power"] is not None else "?"
    zone = display.get("zone") or "?"
    vigor = format_vigor(display.get("vigor_minutes"))
    exp_pct = f"{display['exp_pct']:07.4f}%" if display["exp_pct"] is not None else "?"

    xp_rate_line = f"{xp_rate:.4f}%/min" if xp_rate is not None else "calculando (proxima leitura)..."
    copper_rate_line = f"{copper_rate:.0f}/min" if copper_rate is not None else "calculando (proxima leitura)..."

    return (
        f"Zona: {zone}\n"
        f"Nivel: {level}\n"
        f"Poder: {power}\n"
        f"XP: {exp_pct}\n"
        f"Vigor: {vigor}\n"
        f"XP por minuto: {xp_rate_line}\n"
        f"Cobre por minuto: {copper_rate_line}"
    )
