"""
Roda a extracao de stats contra todos os prints salvos (snapshots de eventos +
pasta history) pra revisar onde a leitura ainda falha em condicoes reais.
Nao treina o Tesseract -- serve como conjunto de teste/regressao.
"""
import glob
import os

import cv2

from common import VIGOR_REGION, extract_stats, format_stats_text, parse_vigor_minutes, read_vigor_text

SAMPLE_GLOBS = [
    "death_snapshot.png",
    "periodic_snapshot.png",
    "status_snapshot.png",
    "vigor_snapshot.png",
    "history/*.png",
]


def main():
    paths = []
    for pattern in SAMPLE_GLOBS:
        paths.extend(sorted(glob.glob(pattern)))

    counts = {"level": 0, "power": 0, "exp_pct": 0, "zone": 0, "vigor_minutes": 0}
    total = 0

    for path in paths:
        img = cv2.imread(path)
        if img is None:
            continue
        total += 1
        stats = extract_stats(img)
        problems = []
        for key in counts:
            if stats.get(key) is None:
                counts[key] += 1
                problems.append(key)
        flag = f"  <-- FALHOU (bruto): {', '.join(problems)}" if problems else ""
        display = format_stats_text(stats).replace("\n", " | ")
        v = VIGOR_REGION
        vigor_crop = img[v["top"]:v["top"] + v["height"], v["left"]:v["left"] + v["width"]]
        vigor_raw_text = read_vigor_text(vigor_crop)
        vigor_raw_parsed = parse_vigor_minutes(vigor_raw_text)
        print(f"{os.path.basename(path):45} {stats}{flag}")
        print(f"{'':45} vigor bruto (sem estado): texto={vigor_raw_text!r} -> {vigor_raw_parsed}")
        if problems:
            print(f"{'':45} exibicao apos fallback: {display}")

    print("\n--- resumo ---")
    print(f"total de imagens: {total}")
    for key, n in counts.items():
        print(f"{key}: {n} falhas ({n/total*100:.0f}%)" if total else f"{key}: 0")


if __name__ == "__main__":
    main()
