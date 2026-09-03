"""
Tira um print da janela do jogo periodicamente e sobrescreve snapshot.png.
Usado para inspecao remota (nao envia nada, so salva localmente).
"""
import sys
import time

import cv2

from common import account_slug, load_settings, get_frame

INTERVAL_SECONDS = 4


def resolve_account(account_id: str):
    if not account_id:
        return None
    for acc in load_settings().get("accounts", []):
        if account_slug(acc.get("label", "")) == account_id:
            return acc.get("window_title", "")
    return None


def main(account_id: str = ""):
    window_title = resolve_account(account_id)
    out_path = f"snapshot_{account_id}.png" if account_id else "snapshot.png"

    while True:
        # recalculada a cada volta -- a janela do jogo pode ainda nao ter
        # aberto quando o snapshot iniciou, ou pode ter sido movida (ou
        # coberta por outra janela -- get_frame pega o conteudo real dela
        # mesmo assim, ver gfx_capture.py)
        frame = get_frame(window_title)
        cv2.imwrite(out_path, frame)
        time.sleep(INTERVAL_SECONDS)


if __name__ == "__main__":
    main(*sys.argv[1:])
