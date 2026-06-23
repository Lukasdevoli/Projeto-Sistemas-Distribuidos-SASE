import os
import sys
import subprocess
import threading

_arquivo = None
_pygame  = None
_winmm   = None
_lock    = threading.Lock()

# --- Busca o arquivo de som ---
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

# --- pygame (opcional) ---
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

# --- MCI do Windows (fallback sem instalação) ---
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


# =============================================================================
# API pública
# =============================================================================

def tocar_inicio():
    """Toca a música uma vez na inicialização do programa."""
    threading.Thread(target=_musica_thread, daemon=True).start()


def tocar(nome: str = "", guiche: str = ""):
    """Anuncia a chamada por voz (nome + guichê). Sem música."""
    if not nome and not guiche:
        return
    threading.Thread(target=_tts_thread, args=(nome, guiche), daemon=True).start()


# =============================================================================
# Threads internas
# =============================================================================

def _musica_thread():
    if not _lock.acquire(blocking=False):
        return
    try:
        _tocar_som_bloqueante()
    finally:
        _lock.release()


def _tts_thread(nome: str, guiche: str):
    if not _lock.acquire(blocking=False):
        return
    try:
        texto = _montar_anuncio(nome, guiche)
        if texto:
            _falar(texto)
    finally:
        _lock.release()


def _montar_anuncio(nome: str, guiche: str) -> str:
    nome   = nome.strip()
    guiche = guiche.strip()
    if nome and guiche:
        return f"{nome}, dirija-se ao guichê {guiche}."
    elif nome:
        return f"{nome}, compareça ao atendimento."
    elif guiche:
        return f"Dirija-se ao guichê {guiche}."
    return ""


# =============================================================================
# Reprodução de som (bloqueante — já roda dentro de thread separada)
# =============================================================================

def _tocar_som_bloqueante():
    if not _arquivo:
        return
    if _pygame:
        try:
            _pygame.mixer.music.load(_arquivo)
            _pygame.mixer.music.play()
            while _pygame.mixer.music.get_busy():
                threading.Event().wait(0.05)
        except Exception:
            pass
    elif _winmm:
        try:
            caminho = _arquivo.replace('/', '\\')
            _winmm.mciSendStringW('close media', None, 0, None)
            _winmm.mciSendStringW(f'open "{caminho}" type mpegvideo alias media', None, 0, None)
            _winmm.mciSendStringW('play media wait', None, 0, None)
            _winmm.mciSendStringW('close media', None, 0, None)
        except Exception:
            pass


# =============================================================================
# TTS — pyttsx3 (Windows/Linux/macOS) com fallbacks por plataforma
# =============================================================================

def _falar(texto: str):
    # 1. pyttsx3: SAPI5 no Windows, espeak no Linux, NSSpeech no macOS
    try:
        import pyttsx3
        engine = pyttsx3.init()
        engine.setProperty('rate', 145)
        _selecionar_voz_pt(engine)
        engine.say(texto)
        engine.runAndWait()
        engine.stop()
        return
    except Exception:
        pass

    # 2. Windows fallback: PowerShell System.Speech
    if sys.platform == 'win32':
        _falar_powershell(texto)
        return

    # 3. Linux fallback: espeak/espeak-ng via subprocess
    if sys.platform.startswith('linux'):
        _falar_espeak(texto)


def _selecionar_voz_pt(engine):
    try:
        for v in engine.getProperty('voices'):
            vid, vname = v.id.lower(), v.name.lower()
            if any(kw in vid or kw in vname for kw in ('pt', 'brazil', 'brasil', 'portuguese')):
                engine.setProperty('voice', v.id)
                return
    except Exception:
        pass


def _falar_powershell(texto: str):
    texto_safe = texto.replace("'", " ").replace('"', ' ').replace('`', ' ')
    script = (
        "Add-Type -AssemblyName System.Speech; "
        "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
        "$s.Rate = -1; "
        f"$s.Speak('{texto_safe}')"
    )
    try:
        subprocess.run(
            ['powershell', '-NonInteractive', '-Command', script],
            capture_output=True, timeout=30,
        )
    except Exception:
        pass


def _falar_espeak(texto: str):
    import shutil
    exe = shutil.which('espeak-ng') or shutil.which('espeak')
    if not exe:
        return
    try:
        subprocess.run(
            [exe, '-v', 'pt-br', '-s', '140', texto],
            capture_output=True, timeout=30,
        )
    except Exception:
        pass
