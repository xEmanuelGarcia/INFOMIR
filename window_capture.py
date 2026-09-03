"""Localiza a janela do jogo MIR4 (processo Mir4G.exe) na tela, pra capturar
so ela em vez do monitor inteiro -- assim as notificacoes/leitura de HUD nao
pegam a area de trabalho, outros apps ou outro monitor por engano, e
continuam certas mesmo se a janela nao estiver encostada no canto (0,0) da
tela ou o jogo estiver rodando num monitor secundario."""
import psutil
import win32gui
import win32process

GAME_PROCESS_NAMES = ("Mir4G.exe", "Mir4S.exe")  # instancias extras (multi-conta) rodam como Mir4S.exe


def _process_name(pid: int) -> str:
    try:
        return psutil.Process(pid).name()
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return ""


def list_game_windows() -> list:
    """Lista as janelas visiveis do processo do jogo, como
    [{"hwnd": ..., "title": ...}, ...]. Normalmente tem 1 item; pode ter mais
    de uma se houver mais de uma instancia do jogo aberta ao mesmo tempo."""
    found = []

    def _enum(hwnd, _):
        if not win32gui.IsWindowVisible(hwnd) or win32gui.IsIconic(hwnd):
            return  # janela invisivel ou minimizada nao tem um retangulo util pra capturar
        title = win32gui.GetWindowText(hwnd)
        if not title:
            return
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        if _process_name(pid) in GAME_PROCESS_NAMES:
            found.append({"hwnd": hwnd, "title": title})

    win32gui.EnumWindows(_enum, None)
    return found


def resolve_game_hwnd(preferred_title: str = ""):
    """Escolhe qual janela do jogo capturar. Sem titulo preferido: a primeira
    janela encontrada (modo legado, uma unica conta). Com titulo preferido
    (monitorando uma conta especifica, entre varias abertas): so essa janela
    -- se ela nao for encontrada (ex: foi fechada), retorna None em vez de
    "adivinhar" e capturar a janela de OUTRA conta por engano."""
    windows = list_game_windows()
    if not windows:
        return None
    if preferred_title:
        for w in windows:
            if w["title"] == preferred_title:
                return w["hwnd"]
        return None
    return windows[0]["hwnd"]


def get_window_client_rect(hwnd) -> dict:
    """Retangulo da area de conteudo da janela (sem borda/barra de titulo),
    em coordenadas de tela -- e onde o HUD do jogo de fato e desenhado."""
    left, top, right, bottom = win32gui.GetClientRect(hwnd)
    left, top = win32gui.ClientToScreen(hwnd, (left, top))
    right, bottom = win32gui.ClientToScreen(hwnd, (right, bottom))
    return {"left": left, "top": top, "width": right - left, "height": bottom - top}
