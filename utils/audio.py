import os
import sys
import threading

_arquivo = None
_pygame  = None
_winmm   = None
_lock    = threading.Lock()

# --- Busca o arquivo de som (sempre roda, independente de libs) ---
def _encontrar_arquivo():
    global _arquivo
    raiz     = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    formatos = ('.mp3', '.wav', '.ogg', '.flac')
    pastas   = [os.path.join(raiz, 'sons'), raiz]

    for pasta in pastas:
        if not os.path.isdir(pasta):
            continue
        for nome in sorted(os.listdir(pasta)):
            if nome.lower().endswith(formatos):
                _arquivo = os.path.join(pasta, nome)
                return

_encontrar_arquivo()

# --- Tenta inicializar pygame (opcional) ---
def _init_pygame():
    global _pygame
    try:
        os.environ.setdefault('PYGAME_HIDE_SUPPORT_PROMPT', '1')
        import pygame
        pygame.mixer.pre_init(44100, -16, 2, 512)
        pygame.mixer.init()
        _pygame = pygame
    except Exception:
        pass

# --- Tenta MCI do Windows como fallback (sem instalação) ---
def _init_winmm():
    global _winmm
    if sys.platform == 'win32':
        try:
            import ctypes
            _winmm = ctypes.windll.winmm
        except Exception:
            pass

_init_pygame()
if not _pygame:
    _init_winmm()


# --- API pública ---

def tocar():
    """Toca o arquivo de som sem bloquear a interface."""
    if not _arquivo:
        return
    if _pygame:
        threading.Thread(target=_play_pygame, daemon=True).start()
    elif _winmm:
        threading.Thread(target=_play_mci, daemon=True).start()


def _play_pygame():
    if not _lock.acquire(blocking=False):
        return
    try:
        _pygame.mixer.music.load(_arquivo)
        _pygame.mixer.music.play()
        while _pygame.mixer.music.get_busy():
            threading.Event().wait(0.05)
    except Exception:
        pass
    finally:
        _lock.release()


def _play_mci():
    """Toca usando o MCI nativo do Windows — funciona com MP3 sem instalar nada."""
    if not _lock.acquire(blocking=False):
        return
    try:
        caminho = _arquivo.replace('/', '\\')
        _winmm.mciSendStringW('close media', None, 0, None)
        _winmm.mciSendStringW(f'open "{caminho}" type mpegvideo alias media', None, 0, None)
        _winmm.mciSendStringW('play media wait', None, 0, None)
        _winmm.mciSendStringW('close media', None, 0, None)
    except Exception:
        pass
    finally:
        _lock.release()
