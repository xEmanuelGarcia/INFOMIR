"""
Painel de controle do MIR4 Companion: Play/Pause, configuracao do Telegram,
ajustes de threshold, e instalacao/registro das tarefas agendadas (pra
configurar do zero num PC novo).
"""
import os
import subprocess
import sys
import tkinter as tk
from tkinter import messagebox, ttk

import requests
from dotenv import get_key, set_key

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import load_settings, save_settings  # noqa: E402

TASKS = ["MIR4Watcher", "MIR4TelegramListener", "MIR4Snapshot"]
FROZEN = getattr(sys, "frozen", False)
PROJECT_DIR = os.path.dirname(sys.executable) if FROZEN else os.path.dirname(os.path.abspath(__file__))
ENV_PATH = os.path.join(PROJECT_DIR, ".env")
TESSERACT_PATH = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
CREATE_NO_WINDOW = 0x08000000


def pythonw_path() -> str:
    candidate = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    return candidate if os.path.exists(candidate) else sys.executable


def task_action(mode_arg: str, script_name: str):
    """(executavel, argumento) pra registrar/chamar uma tarefa -- usa o proprio
    .exe empacotado com um subcomando quando frozen, ou pythonw+script no
    modo desenvolvimento (rodando direto do codigo-fonte)."""
    if FROZEN:
        return sys.executable, mode_arg
    return pythonw_path(), script_name


def run_schtasks(args):
    return subprocess.run(
        ["schtasks"] + args, capture_output=True, text=True, creationflags=CREATE_NO_WINDOW
    )


# ---------- aba Controle ----------

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
    if FROZEN:
        subprocess.Popen([sys.executable, "--calibrate"], cwd=PROJECT_DIR)
    else:
        subprocess.Popen([sys.executable, "app.py", "--calibrate"], cwd=PROJECT_DIR)


def open_logs():
    log_path = os.path.join(PROJECT_DIR, "watcher.log")
    if os.path.exists(log_path):
        os.startfile(log_path)
    else:
        messagebox.showinfo("Logs", "Ainda nao existe watcher.log (o watcher nunca rodou aqui).")


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


# ---------- aba Telegram ----------

def load_env_field(key: str) -> str:
    if not os.path.exists(ENV_PATH):
        return ""
    return get_key(ENV_PATH, key) or ""


def save_telegram_settings():
    token = token_entry.get().strip()
    chat_id = chatid_entry.get().strip()
    if not token or not chat_id:
        messagebox.showwarning("Telegram", "Preencha o token e o chat_id antes de salvar.")
        return
    if not os.path.exists(ENV_PATH):
        open(ENV_PATH, "w", encoding="utf-8").close()
    set_key(ENV_PATH, "TELEGRAM_TOKEN", token)
    set_key(ENV_PATH, "TELEGRAM_CHAT_ID", chat_id)
    messagebox.showinfo("Telegram", "Salvo. Reinicie (Pause + Play) pra aplicar.")


def test_telegram():
    token = token_entry.get().strip()
    chat_id = chatid_entry.get().strip()
    if not token or not chat_id:
        messagebox.showwarning("Telegram", "Preencha o token e o chat_id antes de testar.")
        return
    try:
        resp = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data={"chat_id": chat_id, "text": "[TESTE] MIR4 Companion conectado com sucesso!"},
            timeout=10,
        )
        if resp.ok and resp.json().get("ok"):
            messagebox.showinfo("Telegram", "Mensagem de teste enviada! Confere no Telegram.")
        else:
            messagebox.showerror("Telegram", f"Falha: {resp.text}")
    except requests.RequestException as exc:
        messagebox.showerror("Telegram", f"Erro de conexao: {exc}")


def toggle_token_visibility():
    token_entry.config(show="" if show_token_var.get() else "*")


# ---------- aba Ajustes ----------

def load_adjustments():
    settings = load_settings()
    vigor_entry.delete(0, tk.END)
    vigor_entry.insert(0, str(settings["vigor_low_threshold_minutes"]))
    periodic_entry.delete(0, tk.END)
    periodic_entry.insert(0, str(settings["periodic_report_minutes"]))
    quest_notif_var.set(settings["quest_notifications_enabled"])


def save_adjustments():
    try:
        vigor_minutes = float(vigor_entry.get().strip())
        periodic_minutes = float(periodic_entry.get().strip())
    except ValueError:
        messagebox.showwarning("Ajustes", "Os valores precisam ser numeros.")
        return
    save_settings(
        {
            "vigor_low_threshold_minutes": vigor_minutes,
            "periodic_report_minutes": periodic_minutes,
            "quest_notifications_enabled": quest_notif_var.get(),
        }
    )
    messagebox.showinfo("Ajustes", "Salvo. Reinicie (Pause + Play) pra aplicar.")


# ---------- aba Instalacao ----------

def check_tesseract() -> bool:
    return os.path.exists(TESSERACT_PATH)


def check_env() -> bool:
    return bool(load_env_field("TELEGRAM_TOKEN")) and bool(load_env_field("TELEGRAM_CHAT_ID"))


def check_config() -> bool:
    return os.path.exists(os.path.join(PROJECT_DIR, "config.json"))


def check_tasks_registered() -> bool:
    result = run_schtasks(["/query", "/tn", "MIR4Watcher"])
    return result.returncode == 0


def register_tasks():
    task_specs = {
        "MIR4Watcher": task_action("--watcher", "watcher.py"),
        "MIR4TelegramListener": task_action("--listener", "telegram_listener.py"),
        "MIR4Snapshot": task_action("--snapshot", "snapshot.py"),
    }
    per_task_blocks = "\n".join(
        f'$action = New-ScheduledTaskAction -Execute "{exe}" -Argument \'{arg}\' -WorkingDirectory $workdir\n'
        f'Register-ScheduledTask -TaskName "{name}" -Action $action -Trigger $trigger '
        f"-Settings $settings -Principal $principal -Force | Out-Null"
        for name, (exe, arg) in task_specs.items()
    )
    ps_script = f"""
$workdir = "{PROJECT_DIR}"
$user = "$env:USERDOMAIN\\$env:USERNAME"
$settings = New-ScheduledTaskSettingsSet -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit ([TimeSpan]::Zero) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable
$principal = New-ScheduledTaskPrincipal -UserId $user -LogonType Interactive -RunLevel Limited
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $user
{per_task_blocks}
"""
    result = subprocess.run(
        ["powershell", "-NoProfile", "-Command", ps_script],
        capture_output=True, text=True, creationflags=CREATE_NO_WINDOW,
    )
    if result.returncode == 0:
        messagebox.showinfo("Instalação", "Tarefas agendadas registradas com sucesso.")
    else:
        messagebox.showerror("Instalação", f"Falha ao registrar:\n{result.stderr}")
    refresh_install_checklist()


def refresh_install_checklist():
    checks = [
        (check_tesseract(), "Tesseract OCR instalado"),
        (check_env(), "Telegram configurado (.env)"),
        (check_config(), "Calibração feita (config.json)"),
        (check_tasks_registered(), "Tarefas agendadas registradas"),
    ]
    for label, (ok, text) in zip(check_labels, checks):
        label.config(text=("✔ " if ok else "✘ ") + text, fg="#2ecc71" if ok else "#e74c3c")
    register_button.config(state=tk.DISABLED if check_tasks_registered() else tk.NORMAL)


# ---------- janela ----------

root = tk.Tk()
root.title("MIR4 Companion")
root.geometry("360x420")
root.resizable(False, False)

notebook = ttk.Notebook(root)
notebook.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

# Controle
tab_controle = ttk.Frame(notebook)
notebook.add(tab_controle, text="Controle")

tk.Label(tab_controle, text="MIR4 Companion", font=("Segoe UI", 16, "bold")).pack(pady=(15, 5))
status_label = tk.Label(tab_controle, text="Verificando...", font=("Segoe UI", 12))
status_label.pack(pady=(0, 15))

play_button = tk.Button(
    tab_controle, text="▶  Play", command=start_all, bg="#2ecc71", fg="white",
    font=("Segoe UI", 12, "bold"), width=18, height=2, relief=tk.FLAT,
)
play_button.pack(pady=5)

pause_button = tk.Button(
    tab_controle, text="⏸  Pause", command=stop_all, bg="#e74c3c", fg="white",
    font=("Segoe UI", 12, "bold"), width=18, height=2, relief=tk.FLAT,
)
pause_button.pack(pady=5)

tk.Button(tab_controle, text="Calibrar morte", command=open_calibrate, width=18).pack(pady=(20, 5))
tk.Button(tab_controle, text="Ver logs", command=open_logs, width=18).pack(pady=5)

# Telegram
tab_telegram = ttk.Frame(notebook)
notebook.add(tab_telegram, text="Telegram")

tk.Label(tab_telegram, text="Token do bot", font=("Segoe UI", 10, "bold")).pack(pady=(15, 3))
token_entry = tk.Entry(tab_telegram, width=38, show="*")
token_entry.pack()
token_entry.insert(0, load_env_field("TELEGRAM_TOKEN"))

show_token_var = tk.BooleanVar()
tk.Checkbutton(
    tab_telegram, text="Mostrar token", variable=show_token_var, command=toggle_token_visibility
).pack(pady=(2, 10))

tk.Label(tab_telegram, text="Chat ID", font=("Segoe UI", 10, "bold")).pack(pady=(0, 3))
chatid_entry = tk.Entry(tab_telegram, width=38)
chatid_entry.pack()
chatid_entry.insert(0, load_env_field("TELEGRAM_CHAT_ID"))

tk.Button(tab_telegram, text="Salvar", command=save_telegram_settings, width=18).pack(pady=(20, 5))
tk.Button(tab_telegram, text="Testar conexão", command=test_telegram, width=18).pack(pady=5)

# Ajustes
tab_ajustes = ttk.Frame(notebook)
notebook.add(tab_ajustes, text="Ajustes")

tk.Label(tab_ajustes, text="Avisar vigor baixo com quantos\nminutos restantes:", justify=tk.LEFT).pack(pady=(20, 3))
vigor_entry = tk.Entry(tab_ajustes, width=10)
vigor_entry.pack()

tk.Label(tab_ajustes, text="Relatório periódico a cada\nquantos minutos:", justify=tk.LEFT).pack(pady=(15, 3))
periodic_entry = tk.Entry(tab_ajustes, width=10)
periodic_entry.pack()

quest_notif_var = tk.BooleanVar()
tk.Checkbutton(
    tab_ajustes, text="Avisar progresso da missão primária", variable=quest_notif_var
).pack(pady=(20, 5))

tk.Button(tab_ajustes, text="Salvar", command=save_adjustments, width=18).pack(pady=15)
load_adjustments()

# Instalacao
tab_instalacao = ttk.Frame(notebook)
notebook.add(tab_instalacao, text="Instalação")

tk.Label(tab_instalacao, text="Checklist de instalação", font=("Segoe UI", 11, "bold")).pack(pady=(15, 10))
check_labels = []
for _ in range(4):
    lbl = tk.Label(tab_instalacao, text="", font=("Segoe UI", 9), anchor="w")
    lbl.pack(fill=tk.X, padx=20, pady=2)
    check_labels.append(lbl)

register_button = tk.Button(
    tab_instalacao, text="Registrar tarefas agendadas", command=register_tasks, width=25
)
register_button.pack(pady=(20, 5))
tk.Button(tab_instalacao, text="Atualizar checklist", command=refresh_install_checklist, width=25).pack(pady=5)

refresh_install_checklist()
periodic_refresh()
root.mainloop()
