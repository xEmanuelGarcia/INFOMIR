"""
Janela de controle do MIR4 Companion: Play/Pause pras tarefas agendadas
(MIR4Watcher, MIR4TelegramListener, MIR4Snapshot) + atalho pra calibracao.
"""
import os
import subprocess
import tkinter as tk

TASKS = ["MIR4Watcher", "MIR4TelegramListener", "MIR4Snapshot"]
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
CREATE_NO_WINDOW = 0x08000000


def run_schtasks(args):
    return subprocess.run(
        ["schtasks"] + args,
        capture_output=True,
        text=True,
        creationflags=CREATE_NO_WINDOW,
    )


def count_running():
    running = 0
    for task in TASKS:
        result = run_schtasks(["/query", "/tn", task, "/fo", "LIST"])
        if "execução" in result.stdout or "Running" in result.stdout:
            running += 1
    return running


def start_all():
    for task in TASKS:
        run_schtasks(["/run", "/tn", task])
    root.after(1500, refresh_status)


def stop_all():
    for task in TASKS:
        run_schtasks(["/end", "/tn", task])
    root.after(1500, refresh_status)


def open_calibrate():
    subprocess.Popen(
        ["cmd", "/c", "start", "cmd", "/k", "python calibrate.py"],
        cwd=PROJECT_DIR,
        shell=False,
    )


def open_logs():
    log_path = os.path.join(PROJECT_DIR, "watcher.log")
    if os.path.exists(log_path):
        os.startfile(log_path)


def refresh_status():
    running = count_running()
    total = len(TASKS)
    if running == total:
        status_label.config(text="● Rodando", fg="#2ecc71")
        play_button.config(state=tk.DISABLED)
        pause_button.config(state=tk.NORMAL)
    elif running == 0:
        status_label.config(text="● Parado", fg="#e74c3c")
        play_button.config(state=tk.NORMAL)
        pause_button.config(state=tk.DISABLED)
    else:
        status_label.config(text=f"● Parcial ({running}/{total})", fg="#f39c12")
        play_button.config(state=tk.NORMAL)
        pause_button.config(state=tk.NORMAL)


def periodic_refresh():
    refresh_status()
    root.after(10000, periodic_refresh)


root = tk.Tk()
root.title("MIR4 Companion")
root.geometry("320x340")
root.resizable(False, False)

tk.Label(root, text="MIR4 Companion", font=("Segoe UI", 16, "bold")).pack(pady=(15, 5))
status_label = tk.Label(root, text="Verificando...", font=("Segoe UI", 12))
status_label.pack(pady=(0, 15))

play_button = tk.Button(
    root, text="▶  Play", command=start_all, bg="#2ecc71", fg="white",
    font=("Segoe UI", 12, "bold"), width=18, height=2, relief=tk.FLAT,
)
play_button.pack(pady=5)

pause_button = tk.Button(
    root, text="⏸  Pause", command=stop_all, bg="#e74c3c", fg="white",
    font=("Segoe UI", 12, "bold"), width=18, height=2, relief=tk.FLAT,
)
pause_button.pack(pady=5)

tk.Button(root, text="Calibrar morte", command=open_calibrate, width=18, height=1).pack(pady=(20, 5))
tk.Button(root, text="Ver logs", command=open_logs, width=18, height=1).pack(pady=5)

periodic_refresh()
root.mainloop()
