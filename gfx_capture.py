"""Captura o conteudo real de uma janela do MIR4 mesmo quando ela esta atras
de outra janela (ex: monitorando 2 contas ao mesmo tempo, uma em cima da
outra). Um print de tela comum (mss, usado no resto do projeto como
fallback) so pega o que esta visivelmente por cima na tela naquele pixel --
se a janela estiver coberta, ele captura a janela QUE ESTA por cima, nao a
de baixo. A Windows.Graphics.Capture API (a mesma que o OBS/Xbox Game Bar
usam pra gravar uma janela especifica) captura o conteudo real da janela
direto, independente do que esta visivel na tela.

PrintWindow (API mais antiga/simples) foi tentada primeiro mas devolve uma
imagem preta nesse jogo -- comum em clientes com renderizacao via GPU."""
import ctypes
import threading
import time

import win32gui
from windows_capture import Frame, InternalCaptureControl, WindowsCapture

_sessions = {}
_sessions_lock = threading.Lock()


class _RECT(ctypes.Structure):
    _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long), ("right", ctypes.c_long), ("bottom", ctypes.c_long)]


_DWMWA_EXTENDED_FRAME_BOUNDS = 9


def _capture_frame_origin(hwnd):
    """GetWindowRect inclui uma margem de sombra invisivel ao redor da janela
    (a largura muda dependendo do tema/DPI) que a Windows.Graphics.Capture
    NAO inclui no frame capturado -- usar GetWindowRect pra calcular onde
    fica a area de conteudo dentro do frame gera um recorte desalinhado.
    DWMWA_EXTENDED_FRAME_BOUNDS da o retangulo "visivel de verdade", que bate
    exatamente com o tamanho do frame que a captura devolve."""
    rect = _RECT()
    result = ctypes.windll.dwmapi.DwmGetWindowAttribute(
        hwnd, _DWMWA_EXTENDED_FRAME_BOUNDS, ctypes.byref(rect), ctypes.sizeof(rect)
    )
    if result == 0:
        return rect.left, rect.top
    return win32gui.GetWindowRect(hwnd)[:2]  # fallback se a chamada falhar


class _Session:
    def __init__(self, hwnd):
        self.hwnd = hwnd
        self.alive = True
        self._frame = None
        self._frame_lock = threading.Lock()

        window_left, window_top = _capture_frame_origin(hwnd)
        client_left, client_top, client_right, client_bottom = win32gui.GetClientRect(hwnd)
        client_screen_left, client_screen_top = win32gui.ClientToScreen(hwnd, (client_left, client_top))
        self._offset_x = client_screen_left - window_left
        self._offset_y = client_screen_top - window_top
        self._width = client_right - client_left
        self._height = client_bottom - client_top

        capture = WindowsCapture(
            cursor_capture=False,
            draw_border=False,
            minimum_update_interval=1000,  # nao precisamos de mais que ~1 frame/s
            window_hwnd=hwnd,
        )

        @capture.event
        def on_frame_arrived(frame: Frame, capture_control: InternalCaptureControl):
            ox, oy = self._offset_x, self._offset_y
            w, h = self._width, self._height
            cropped = frame.frame_buffer[oy:oy + h, ox:ox + w, :3]  # BGRA -> BGR, so a area de conteudo (sem borda/titulo)
            with self._frame_lock:
                self._frame = cropped.copy()

        @capture.event
        def on_closed():
            self.alive = False

        self._control = capture.start_free_threaded()

    def get_frame(self, timeout: float = 2.0):
        deadline = time.time() + timeout
        while self._frame is None and self.alive and time.time() < deadline:
            time.sleep(0.02)
        with self._frame_lock:
            return self._frame

    def stop(self):
        try:
            self._control.stop()
        except Exception:
            pass
        self.alive = False


def get_frame(hwnd: int, timeout: float = 2.0):
    """Retorna o frame mais recente da janela (area de conteudo, sem
    borda/titulo), capturado mesmo se ela estiver atras de outra janela.
    Mantem uma sessao de captura viva por hwnd (mais eficiente que abrir uma
    nova a cada chamada) -- criada na primeira vez que esse hwnd e pedido, e
    recriada automaticamente se a janela fechar e outra abrir no lugar (novo
    hwnd)."""
    with _sessions_lock:
        session = _sessions.get(hwnd)
        if session is None or not session.alive:
            session = _Session(hwnd)
            _sessions[hwnd] = session
    return session.get_frame(timeout=timeout)


def stop_all():
    with _sessions_lock:
        for session in _sessions.values():
            session.stop()
        _sessions.clear()
