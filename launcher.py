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
from common import account_slug, load_settings, save_settings  # noqa: E402
import window_capture  # noqa: E402

FROZEN = getattr(sys, "frozen", False)
PROJECT_DIR = os.path.dirname(sys.executable) if FROZEN else os.path.dirname(os.path.abspath(__file__))
ENV_PATH = os.path.join(PROJECT_DIR, ".env")
TESSERACT_PATH = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
CREATE_NO_WINDOW = 0x08000000


def pythonw_path() -> str:
    candidate = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    return candidate if os.path.exists(candidate) else sys.executable


def task_action(mode_arg: str, script_name: str, account_id: str = ""):
    """(executavel, argumento) pra registrar/chamar uma tarefa -- usa o proprio
    .exe empacotado com um subcomando quando frozen, ou pythonw+script no
    modo desenvolvimento (rodando direto do codigo-fonte). account_id (slug,
    sem espacos) e passado como argumento extra quando ha mais de uma conta
    monitorada -- ver watcher.py/snapshot.py resolve_account()."""
    if FROZEN:
        arg = f"{mode_arg} {account_id}".strip() if account_id else mode_arg
        return sys.executable, arg
    arg = f"{script_name} {account_id}".strip() if account_id else script_name
    return pythonw_path(), arg


def current_tasks() -> list:
    """Nome das tarefas agendadas que deveriam existir agora, de acordo com
    settings.json["accounts"]. Sem contas configuradas: as 3 tarefas de
    sempre (modo legado, uma conta). Com contas: um par Watcher+Snapshot por
    conta, mais um unico Listener compartilhado (nao da pra ter 2 processos
    puxando getUpdates do mesmo bot ao mesmo tempo)."""
    accounts = load_settings().get("accounts", [])
    if not accounts:
        return ["MIR4Watcher", "MIR4TelegramListener", "MIR4Snapshot"]
    tasks = ["MIR4TelegramListener"]
    for acc in accounts:
        slug = account_slug(acc.get("label", ""))
        tasks += [f"MIR4Watcher_{slug}", f"MIR4Snapshot_{slug}"]
    return tasks


def build_task_specs() -> dict:
    accounts = load_settings().get("accounts", [])
    specs = {"MIR4TelegramListener": task_action("--listener", "telegram_listener.py")}
    if not accounts:
        specs["MIR4Watcher"] = task_action("--watcher", "watcher.py")
        specs["MIR4Snapshot"] = task_action("--snapshot", "snapshot.py")
        return specs
    for acc in accounts:
        slug = account_slug(acc.get("label", ""))
        specs[f"MIR4Watcher_{slug}"] = task_action("--watcher", "watcher.py", slug)
        specs[f"MIR4Snapshot_{slug}"] = task_action("--snapshot", "snapshot.py", slug)
    return specs


def run_schtasks(args):
    # encoding explicito (nao so text=True): o console do Windows gera saida
    # na codificacao OEM (cp850 aqui), diferente da codificacao "ANSI" padrao
    # que o Python usaria por default -- sem isso "execução" vira "execu‡Æo"
    # e a checagem de status nunca bate.
    return subprocess.run(
        ["schtasks"] + args, capture_output=True, encoding="cp850", creationflags=CREATE_NO_WINDOW
    )


# ---------- aba Controle ----------

def is_task_running(stdout: str) -> bool:
    # olha so a linha "Status:" -- o campo "Hora da proxima execucao" tambem
    # contem a palavra "execucao" e dava falso positivo sempre, mesmo parado
    for line in stdout.splitlines():
        if line.strip().startswith("Status:"):
            return "execução" in line or "Running" in line
    return False


def count_running():
    running = 0
    for task in current_tasks():
        result = run_schtasks(["/query", "/tn", task, "/fo", "LIST"])
        if is_task_running(result.stdout):
            running += 1
    return running


def start_all():
    for task in current_tasks():
        run_schtasks(["/run", "/tn", task])
    root.after(1500, refresh_status)


def stop_all():
    for task in current_tasks():
        run_schtasks(["/end", "/tn", task])
    root.after(1500, refresh_status)


LOG_FILES = {"Watcher": "watcher.log", "Telegram": "telegram_listener.log"}
LOG_TAIL_LINES = 300
LOG_REFRESH_MS = 1000


def _tail_lines(path: str, n: int) -> str:
    if not os.path.exists(path):
        return "(esse log ainda nao existe -- a tarefa correspondente nunca rodou aqui)"
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        return "".join(f.readlines()[-n:])


def open_logs():
    # janela estilo console (so leitura -- e um Text widget mostrando o
    # arquivo, nao um terminal de verdade, entao nao tem processo nenhum
    # atras pra um Ctrl+C sem querer conseguir interromper)
    win = tk.Toplevel(root)
    win.title("Logs - MIR4 Companion")
    win.geometry("760x480")
    win.configure(bg="#1e1e1e")

    header = tk.Frame(win, bg="#1e1e1e")
    header.pack(fill=tk.X, padx=8, pady=8)
    tk.Label(header, text="Log:", bg="#1e1e1e", fg="#cccccc", font=("Segoe UI", 9)).pack(side=tk.LEFT)
    log_choice = tk.StringVar(value="Watcher")
    combo = ttk.Combobox(
        header, textvariable=log_choice, values=list(LOG_FILES.keys()), state="readonly", width=18
    )
    combo.pack(side=tk.LEFT, padx=(6, 0))

    body = tk.Frame(win, bg="#1e1e1e")
    body.pack(fill=tk.BOTH, expand=True, padx=8, pady=(0, 8))

    text = tk.Text(
        body, bg="#0c0c0c", fg="#39ff14", font=("Consolas", 9), wrap=tk.NONE,
        state=tk.DISABLED, borderwidth=0, highlightthickness=0,
    )
    scrollbar = ttk.Scrollbar(body, command=text.yview)
    text.configure(yscrollcommand=scrollbar.set)
    scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
    text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

    state = {"active": True}

    def refresh():
        if not state["active"]:
            return
        path = os.path.join(PROJECT_DIR, LOG_FILES[log_choice.get()])
        at_bottom = text.yview()[1] >= 0.999
        text.config(state=tk.NORMAL)
        text.delete("1.0", tk.END)
        text.insert(tk.END, _tail_lines(path, LOG_TAIL_LINES))
        text.config(state=tk.DISABLED)
        if at_bottom:
            text.see(tk.END)
        win.after(LOG_REFRESH_MS, refresh)

    def on_close():
        state["active"] = False
        win.destroy()

    win.protocol("WM_DELETE_WINDOW", on_close)
    combo.bind("<<ComboboxSelected>>", lambda _e: refresh())
    refresh()


def refresh_status():
    running = count_running()
    total = len(current_tasks())
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
    refresh_accounts_summary()
    root.after(10000, periodic_refresh)


# ---------- contas monitoradas (janelas do MIR4) ----------

def refresh_accounts_summary():
    accounts = load_settings().get("accounts", [])
    if not accounts:
        windows = window_capture.list_game_windows()
        if not windows:
            accounts_summary_label.config(text="✘ Janela do MIR4 nao encontrada (capturando a tela toda)", fg="#e74c3c")
        else:
            accounts_summary_label.config(text="✔ Janela do MIR4 detectada (conta unica)", fg="#2ecc71")
        return
    labels = ", ".join(a.get("label", "?") for a in accounts)
    accounts_summary_label.config(text=f"✔ Monitorando: {labels}", fg="#2ecc71")


def open_accounts_manager():
    windows = window_capture.list_game_windows()
    saved_by_title = {a["window_title"]: a.get("label", "") for a in load_settings().get("accounts", [])}

    win = tk.Toplevel(root)
    win.title("Contas monitoradas")
    win.resizable(False, False)

    if not windows:
        tk.Label(
            win, text="Nenhuma janela do MIR4 encontrada agora.\nAbra o jogo e abra esta janela de novo.",
            fg="#e74c3c", justify=tk.LEFT,
        ).pack(padx=16, pady=16)
        tk.Button(win, text="Fechar", command=win.destroy, width=14).pack(pady=(0, 12))
        return

    tk.Label(win, text="Janelas do MIR4 detectadas:", font=("Segoe UI", 10, "bold")).pack(
        padx=12, pady=(12, 6), anchor="w"
    )

    rows = []
    body = tk.Frame(win)
    body.pack(fill=tk.BOTH, expand=True, padx=12)
    for w in windows:
        title = w["title"]
        row = tk.Frame(body)
        row.pack(fill=tk.X, pady=4)
        check_var = tk.BooleanVar(value=title in saved_by_title)
        tk.Checkbutton(row, variable=check_var).pack(side=tk.LEFT)
        tk.Label(row, text=title, width=11, anchor="w", font=("Consolas", 9)).pack(side=tk.LEFT)
        entry = tk.Entry(row, width=18)
        entry.insert(0, saved_by_title.get(title, ""))
        entry.pack(side=tk.LEFT, padx=(4, 0))
        rows.append((title, check_var, entry))

    tk.Label(
        win,
        text="Digite um nome pro personagem em cada janela que quiser\nmonitorar (o que preferir -- so identifica os avisos).\nDeixe desmarcado pra ignorar essa janela.",
        font=("Segoe UI", 8), fg="#888888", justify=tk.LEFT,
    ).pack(padx=12, pady=(8, 4), anchor="w")

    def save_accounts():
        accounts = []
        seen_slugs = set()
        for title, check_var, entry in rows:
            if not check_var.get():
                continue
            label = entry.get().strip()
            if not label:
                messagebox.showwarning("Contas", f"Digite um nome pra janela {title} (ou desmarque ela).")
                return
            slug = account_slug(label)
            if slug in seen_slugs:
                messagebox.showwarning("Contas", f'O nome "{label}" ja esta em uso -- use nomes diferentes.')
                return
            seen_slugs.add(slug)
            accounts.append({"window_title": title, "label": label})
        save_settings({"accounts": accounts})
        messagebox.showinfo(
            "Contas",
            "Salvo. Va em Instalação → Registrar tarefas agendadas pra aplicar\n"
            "(e reinicie com Pause + Play se ja estiver rodando).",
        )
        win.destroy()
        refresh_accounts_summary()

    tk.Button(win, text="Salvar", command=save_accounts, width=14).pack(pady=(6, 12))


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


def check_tasks_registered() -> bool:
    return all(run_schtasks(["/query", "/tn", task]).returncode == 0 for task in current_tasks())


def register_tasks():
    task_specs = build_task_specs()
    desired_names = '", "'.join(task_specs.keys())
    # sem trigger nenhum -- as tarefas nao iniciam sozinhas com o Windows, so
    # quando o Play do launcher chama schtasks /run (o launcher e quem cuida
    # de iniciar/parar)
    per_task_blocks = "\n".join(
        f'$action = New-ScheduledTaskAction -Execute "{exe}" -Argument \'{arg}\' -WorkingDirectory $workdir\n'
        f'Register-ScheduledTask -TaskName "{name}" -Action $action '
        f"-Settings $settings -Principal $principal -Force | Out-Null"
        for name, (exe, arg) in task_specs.items()
    )
    ps_script = f"""
$workdir = "{PROJECT_DIR}"
$user = "$env:USERDOMAIN\\$env:USERNAME"
$settings = New-ScheduledTaskSettingsSet -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit ([TimeSpan]::Zero) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
$principal = New-ScheduledTaskPrincipal -UserId $user -LogonType Interactive -RunLevel Limited
$desired = @("{desired_names}")
Get-ScheduledTask | Where-Object {{ $_.TaskName -like "MIR4*" -and $desired -notcontains $_.TaskName }} | Unregister-ScheduledTask -Confirm:$false
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
        (check_tasks_registered(), "Tarefas agendadas registradas"),
    ]
    for label, (ok, text) in zip(check_labels, checks):
        label.config(text=("✔ " if ok else "✘ ") + text, fg="#2ecc71" if ok else "#e74c3c")
    register_button.config(state=tk.DISABLED if check_tasks_registered() else tk.NORMAL)


# ---------- janela ----------

root = tk.Tk()
root.title("MIR4 Companion")
root.geometry("360x470")
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

tk.Button(tab_controle, text="Ver logs", command=open_logs, width=18).pack(pady=(20, 5))

accounts_summary_label = tk.Label(tab_controle, text="Verificando janela do jogo...", font=("Segoe UI", 8))
accounts_summary_label.pack(pady=(15, 2))
tk.Button(tab_controle, text="Contas monitoradas", command=open_accounts_manager, width=18).pack()

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
for _ in range(3):
    lbl = tk.Label(tab_instalacao, text="", font=("Segoe UI", 9), anchor="w")
    lbl.pack(fill=tk.X, padx=20, pady=2)
    check_labels.append(lbl)

register_button = tk.Button(
    tab_instalacao, text="Registrar tarefas agendadas", command=register_tasks, width=25
)
register_button.pack(pady=(20, 5))
tk.Button(tab_instalacao, text="Atualizar checklist", command=refresh_install_checklist, width=25).pack(pady=5)

refresh_install_checklist()
refresh_accounts_summary()
periodic_refresh()
root.mainloop()
