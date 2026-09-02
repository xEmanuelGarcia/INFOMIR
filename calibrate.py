"""
Calibracao: quando a tela de morte do MIR4 estiver visivel (o jogo em modo
janela/borderless, nao tela cheia exclusiva), clique OK na caixa de dialogo.
O script tira um print da tela inteira e abre uma janela pra voce selecionar
(arrastando o mouse) a area da faixa vermelha de morte. Depois de selecionar,
aperte ENTER (ou ESPACO) pra confirmar, ou C pra cancelar.
"""
import json
import os
import sys
import tkinter as tk
from tkinter import messagebox

import cv2
import mss
import numpy as np

MONITOR_INDEX = 1  # monitor primario
CONFIG_PATH = "config.json"
TEMPLATE_PATH = "templates/death_template.png"

os.makedirs("templates", exist_ok=True)


def grab_full_screen():
    with mss.MSS() as sct:
        monitor = sct.monitors[MONITOR_INDEX]
        shot = sct.grab(monitor)
        img = np.array(shot)[:, :, :3]  # BGRA -> BGR
        return img, monitor


def wait_for_confirmation() -> bool:
    """Caixa de dialogo em vez de input() no console -- assim nao depende de
    terminal, funciona igual quando empacotado como .exe sem console."""
    root = tk.Tk()
    root.withdraw()
    proceed = messagebox.askokcancel(
        "Calibração MIR4",
        "Vá para o jogo (modo janela/borderless, não tela cheia exclusiva).\n\n"
        "Quando a tela de morte estiver visível, clique OK aqui pra capturar o print.",
    )
    root.destroy()
    return proceed


def main():
    if not wait_for_confirmation():
        return

    img, monitor = grab_full_screen()

    roi = cv2.selectROI("Selecione a area da tela de morte - ENTER para confirmar", img, showCrosshair=True)
    cv2.destroyAllWindows()

    x, y, w, h = [int(v) for v in roi]
    if w == 0 or h == 0:
        messagebox.showwarning("Calibração MIR4", "Seleção vazia, cancelando.")
        return

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

    messagebox.showinfo(
        "Calibração MIR4",
        f"Salvo!\nTemplate: {TEMPLATE_PATH}\nConfig: {CONFIG_PATH}\n\nJá pode dar Play no painel.",
    )


if __name__ == "__main__":
    main()
