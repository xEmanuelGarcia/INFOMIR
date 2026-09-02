"""
Calibracao: quando a tela de morte do MIR4 estiver visivel (o jogo em modo
janela/borderless, nao tela cheia exclusiva), volte pra este terminal e
aperte ENTER. O script tira um print da tela inteira e abre uma janela pra
voce selecionar (arrastando o mouse) a area da faixa vermelha de morte.
Depois de selecionar, aperte ENTER (ou ESPACO) pra confirmar, ou C pra cancelar.
"""
import json
import sys

import cv2
import mss
import numpy as np

MONITOR_INDEX = 1  # monitor primario
CONFIG_PATH = "config.json"
TEMPLATE_PATH = "templates/death_template.png"

import os
os.makedirs("templates", exist_ok=True)


def grab_full_screen():
    with mss.MSS() as sct:
        monitor = sct.monitors[MONITOR_INDEX]
        shot = sct.grab(monitor)
        img = np.array(shot)[:, :, :3]  # BGRA -> BGR
        return img, monitor


def main():
    print("Va para o jogo (modo janela/borderless, nao tela cheia exclusiva).")
    print("Quando a tela de morte aparecer, volte pra este terminal e aperte ENTER.")

    input()
    print("Print capturado. Selecione a area da tela de morte na janela que abriu...")

    img, monitor = grab_full_screen()

    roi = cv2.selectROI("Selecione a area da tela de morte - ENTER para confirmar", img, showCrosshair=True)
    cv2.destroyAllWindows()

    x, y, w, h = [int(v) for v in roi]
    if w == 0 or h == 0:
        print("Selecao vazia, cancelando.")
        sys.exit(1)

    crop = img[y:y + h, x:x + w]
    cv2.imwrite(TEMPLATE_PATH, crop)

    config = {
        "monitor_index": MONITOR_INDEX,
        "region": {"left": monitor["left"] + x, "top": monitor["top"] + y, "width": w, "height": h},
        "enter_threshold": 0.80,
        "exit_threshold": 0.60,
        "poll_interval_seconds": 1.5,
    }
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)

    print(f"Salvo! Template: {TEMPLATE_PATH} | Config: {CONFIG_PATH}")
    print("Agora rode: python watcher.py")


if __name__ == "__main__":
    main()
