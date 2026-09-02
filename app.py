"""
Ponto de entrada unico do MIR4 Companion. Empacotado com PyInstaller num
unico executavel (MIR4Companion.exe); o modo e escolhido por argumento de
linha de comando -- as tarefas agendadas e o proprio painel chamam isso com
--watcher, --listener, --snapshot ou --calibrate. Sem argumentos, abre a
janela de controle.
"""
import os
import sys


def main():
    # garante que arquivos relativos (.env, config.json, logs, etc.) sejam
    # lidos/gravados sempre ao lado do executavel/script, nao de onde o
    # processo foi disparado (importa pro Agendador de Tarefas e pro .exe)
    base_dir = os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else os.path.dirname(os.path.abspath(__file__))
    os.chdir(base_dir)

    mode = sys.argv[1] if len(sys.argv) > 1 else "--gui"

    if mode == "--watcher":
        import watcher
        watcher.main()
    elif mode == "--listener":
        import telegram_listener
        telegram_listener.main()
    elif mode == "--snapshot":
        import snapshot
        snapshot.main()
    elif mode == "--calibrate":
        import calibrate
        calibrate.main()
    else:
        import launcher  # abre a janela (executa o codigo de nivel superior do modulo)


if __name__ == "__main__":
    main()
