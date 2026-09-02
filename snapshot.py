"""
Tira um print da tela inteira periodicamente e sobrescreve snapshot.png.
Usado para inspecao remota (nao envia nada, so salva localmente).
"""
import time

import mss
import numpy as np
import cv2

MONITOR_INDEX = 1
OUT_PATH = "snapshot.png"
INTERVAL_SECONDS = 4

with mss.MSS() as sct:
    monitor = sct.monitors[MONITOR_INDEX]
    while True:
        shot = sct.grab(monitor)
        frame = np.array(shot)[:, :, :3]
        cv2.imwrite(OUT_PATH, frame)
        time.sleep(INTERVAL_SECONDS)
