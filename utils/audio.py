"""
audio.py — Saída sonora do SASE (música de abertura + anúncio de senhas por voz).

O QUE FAZ:
    1. Toca uma música/efeito UMA vez na inicialização do programa.
    2. Anuncia por voz (TTS — Text To Speech) a chamada de cada senha,
       dizendo o nome da pessoa e o guichê para onde ela deve se dirigir.

COMO USA / POR QUE EXISTE:
    Em um sistema de atendimento por senha, o feedback sonoro é parte da
    experiência: a música sinaliza que o painel está ativo e a voz garante
    acessibilidade (quem não está olhando o painel ouve a chamada).

ARQUITETURA — HIERARQUIA DE BACKENDS (degradação graciosa):
    O módulo é escrito para funcionar em qualquer máquina dos alunos sem exigir
    instalação obrigatória de dependências. Por isso ele tenta, em ordem, o
    melhor recurso disponível e cai para alternativas mais simples:

    Música:  pygame  >  winmm/MCI (nativo do Windows)
    Voz:     pyttsx3 >  PowerShell System.Speech (Windows) > espeak (Linux)

    Se nada estiver disponível, as funções simplesmente não fazem nada (falham
    em silêncio) — o sistema de senhas continua funcionando normalmente.

CONCORRÊNCIA:
    Toda reprodução roda em thread separada (daemon) para NÃO travar a interface
    enquanto o som toca. Um threading.Lock garante que apenas UM som toque por
    vez, evitando sobreposição de áudios (ver detalhes nas threads internas).

NOTA: Este arquivo NÃO usa a rede — é um utilitário local de mídia. A
comunicação distribuída do SASE acontece via sockets TCP (ver utils/conexao.py).

Disciplina: Sistemas Distribuídos — IFCE Campus Crato
"""

import os
import sys
import subprocess
import threading

# ── Estado global do módulo ─────────────────────────────────────────────────

# Caminho do arquivo de música encontrado em disco (None se nenhum existir).
_arquivo = None
# Referência ao módulo pygame, se conseguir inicializar (None caso contrário).
_pygame  = None
# Handle da DLL winmm do Windows, usada como fallback de áudio (None se indisp.).
_winmm   = None
# Trava que serializa a reprodução: garante UM som por vez (anti-sobreposição).
# É criada já no import porque é compartilhada por todas as threads de áudio.
_lock    = threading.Lock()


# ── Descoberta do arquivo de som ────────────────────────────────────────────

def _encontrar_arquivo():
    """Procura o primeiro arquivo de áudio disponível e guarda em ``_arquivo``.

    A busca é feita por convenção (não há caminho fixo no código) para que o
    aluno possa apenas largar um arquivo de som na pasta ``sons/`` sem editar
    nada. Procura primeiro em ``<raiz>/sons`` e depois na própria raiz do
    projeto, aceitando os formatos de áudio mais comuns.

    Returns:
        None: o resultado é escrito na variável global ``_arquivo``.
    """
    global _arquivo
    # Sobe um nível a partir de utils/ para chegar à raiz do projeto.
    raiz     = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    formatos = ('.mp3', '.wav', '.ogg', '.flac')
    pastas   = [os.path.join(raiz, 'sons'), raiz]
    for pasta in pastas:
        if not os.path.isdir(pasta):
            continue
        # sorted() torna a escolha determinística (sempre o mesmo arquivo se
        # houver mais de um), em vez de depender da ordem do sistema de arquivos.
        for nome in sorted(os.listdir(pasta)):
            if nome.lower().endswith(formatos):
                _arquivo = os.path.join(pasta, nome)
                return

# Executa a busca já no import para que _arquivo esteja pronto ao tocar.
_encontrar_arquivo()


# ── Inicialização dos backends de áudio ─────────────────────────────────────

def _init_pygame():
    """Tenta inicializar o pygame como backend PRINCIPAL de música.

    Por que pygame primeiro? É multiplataforma (Windows/Linux/macOS), toca
    MP3/OGG/WAV e dá controle fino sobre a reprodução (ex.: saber quando o som
    terminou via ``get_busy()``). Se a biblioteca não estiver instalada ou o
    sistema não tiver dispositivo de áudio, a exceção é engolida e o módulo
    seguirá para o fallback.
    """
    global _pygame
    try:
        # Evita o banner de boas-vindas do pygame poluindo o terminal.
        os.environ.setdefault('PYGAME_HIDE_SUPPORT_PROMPT', '1')
        import pygame
        # pre_init define qualidade/buffer ANTES de abrir o dispositivo:
        # 44100 Hz, 16 bits assinado, estéreo, buffer pequeno (512) para baixa
        # latência ao iniciar o som.
        pygame.mixer.pre_init(44100, -16, 2, 512)
        pygame.mixer.init()
        _pygame = pygame
    except Exception:
        pass


def _init_winmm():
    """Inicializa o MCI/winmm do Windows como FALLBACK de música.

    Vantagem: ``winmm.dll`` já vem no Windows, então funciona sem instalar nada.
    Só é usado quando o pygame falhou. Em sistemas não-Windows não faz nada.
    """
    global _winmm
    if sys.platform == 'win32':
        try:
            import ctypes
            _winmm = ctypes.windll.winmm
        except Exception:
            pass

# Tenta o backend preferido (pygame). Só recorre ao nativo do Windows se falhar.
_init_pygame()
if not _pygame:
    _init_winmm()


# =============================================================================
# API pública
# =============================================================================

def tocar_inicio():
    """Toca a música de abertura UMA vez, na inicialização do programa.

    Diferença para ``tocar()``: esta função reproduz o ARQUIVO de música e é
    usada apenas no boot do sistema (ambientação). Não fala nada por voz.
    A reprodução roda em thread daemon para não bloquear a inicialização da UI.
    """
    threading.Thread(target=_musica_thread, daemon=True).start()


def tocar(nome: str = "", guiche: str = ""):
    """Anuncia uma chamada de senha por VOZ (TTS) — sem música.

    Usada a cada chamada de senha durante o atendimento. Monta uma frase com o
    nome e/ou o guichê e a sintetiza em fala. Diferença para ``tocar_inicio()``:
    aqui o conteúdo é dinâmico (voz) e ocorre muitas vezes ao longo da sessão.

    Args:
        nome (str): nome da pessoa a ser chamada. Opcional.
        guiche (str): identificação do guichê de destino. Opcional.

    Returns:
        None: se nome e guichê forem ambos vazios, não faz nada.
    """
    if not nome and not guiche:
        return
    threading.Thread(target=_tts_thread, args=(nome, guiche), daemon=True).start()


# =============================================================================
# Threads internas
# =============================================================================

def _musica_thread():
    """Corpo da thread de música: adquire a trava e reproduz o arquivo.

    O ``acquire(blocking=False)`` é a chave da política anti-sobreposição: se
    OUTRO som já está tocando (trava ocupada), esta chamada é simplesmente
    DESCARTADA (return) em vez de enfileirada. Em um painel de senhas, anúncios
    empilhados ficariam atrasados e confusos — é melhor ignorar o novo do que
    falar tudo acumulado.
    """
    if not _lock.acquire(blocking=False):
        return
    try:
        _tocar_som_bloqueante()
    finally:
        # finally garante que a trava seja liberada mesmo se houver erro.
        _lock.release()


def _tts_thread(nome: str, guiche: str):
    """Corpo da thread de voz: adquire a trava, monta e fala o anúncio.

    Mesma política do ``_musica_thread``: se já há som tocando, descarta este
    anúncio (não enfileira) para evitar vozes sobrepostas.

    Args:
        nome (str): nome a anunciar.
        guiche (str): guichê a anunciar.
    """
    if not _lock.acquire(blocking=False):
        return
    try:
        texto = _montar_anuncio(nome, guiche)
        if texto:
            _falar(texto)
    finally:
        _lock.release()


def _montar_anuncio(nome: str, guiche: str) -> str:
    """Monta a frase de chamada conforme os dados disponíveis.

    Args:
        nome (str): nome da pessoa (pode vir vazio).
        guiche (str): guichê de destino (pode vir vazio).

    Returns:
        str: frase pronta para o TTS, ou string vazia se nada foi informado.
    """
    nome   = nome.strip()
    guiche = guiche.strip()
    # As três combinações geram frases naturais diferentes; sem dados, "".
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
    """Reproduz ``_arquivo`` e BLOQUEIA até terminar.

    É "bloqueante" de propósito: como roda dentro de uma thread e segura a
    trava, manter a função ativa até o fim do som é justamente o que impede
    outro áudio de começar no meio. Escolhe o backend disponível (pygame ou
    winmm). Sem arquivo ou sem backend, retorna em silêncio.
    """
    if not _arquivo:
        return
    if _pygame:
        try:
            _pygame.mixer.music.load(_arquivo)
            _pygame.mixer.music.play()
            # Poll a cada 50ms enquanto o som toca. Event().wait é usado em vez
            # de time.sleep por ser uma espera "amigável" para threads.
            while _pygame.mixer.music.get_busy():
                threading.Event().wait(0.05)
        except Exception:
            pass
    elif _winmm:
        try:
            # A API MCI do Windows trabalha com comandos de texto e exige
            # caminhos no formato Windows (barras invertidas).
            caminho = _arquivo.replace('/', '\\')
            # 'close media' antes de abrir limpa qualquer mídia anterior presa.
            _winmm.mciSendStringW('close media', None, 0, None)
            _winmm.mciSendStringW(f'open "{caminho}" type mpegvideo alias media', None, 0, None)
            # 'play media wait' bloqueia até o fim — coerente com a função.
            _winmm.mciSendStringW('play media wait', None, 0, None)
            _winmm.mciSendStringW('close media', None, 0, None)
        except Exception:
            pass


# =============================================================================
# TTS — pyttsx3 (Windows/Linux/macOS) com fallbacks por plataforma
# =============================================================================

def _falar(texto: str):
    """Sintetiza ``texto`` em voz, tentando os backends em ordem de preferência.

    Estratégia em cascata (cada nível só é tentado se o anterior falhar):
        1. Linux: espeak-ng direto via subprocess — mais confiável no Arch/Wayland,
           onde pyttsx3 pode falhar silenciosamente sem lançar exceção.
        2. pyttsx3 — preferido no Windows/macOS (SAPI5 / NSSpeech).
        3. PowerShell System.Speech — fallback nativo do Windows.
        4. espeak/espeak-ng direto — fallback final no Linux.

    Args:
        texto (str): frase a ser falada.
    """
    # 1. Linux: espeak-ng direto é mais confiável que o wrapper pyttsx3
    # (no Arch/Wayland o pyttsx3 pode retornar sem exceção mas sem produzir áudio)
    if sys.platform.startswith('linux'):
        if _falar_espeak(texto):
            return

    # 2. pyttsx3: SAPI5 no Windows, NSSpeech no macOS (ou fallback Linux se espeak falhou)
    try:
        import pyttsx3
        engine = pyttsx3.init()
        # rate 145: um pouco mais lento que o padrão para clareza na chamada.
        engine.setProperty('rate', 145)
        _selecionar_voz_pt(engine)
        engine.say(texto)
        engine.runAndWait()
        engine.stop()
        return
    except Exception:
        pass

    # 3. Windows fallback: PowerShell System.Speech
    if sys.platform == 'win32':
        _falar_powershell(texto)


def _selecionar_voz_pt(engine):
    """Tenta selecionar uma voz em PORTUGUÊS no motor pyttsx3.

    Sem isso, o motor usaria a voz padrão do sistema (frequentemente inglês),
    que pronunciaria nomes e palavras em português de forma errada. Varre as
    vozes instaladas e escolhe a primeira cujo id ou nome contenha pistas de
    português/Brasil.

    Args:
        engine: instância já inicializada do motor pyttsx3.
    """
    try:
        for v in engine.getProperty('voices'):
            vid, vname = v.id.lower(), v.name.lower()
            if any(kw in vid or kw in vname for kw in ('pt', 'brazil', 'brasil', 'portuguese')):
                engine.setProperty('voice', v.id)
                return
    except Exception:
        pass


def _falar_powershell(texto: str):
    """Fallback de voz no Windows usando System.Speech via PowerShell.

    Não exige instalar nada além do próprio Windows. Monta um script inline que
    cria um SpeechSynthesizer e fala o texto.

    Args:
        texto (str): frase a falar.
    """
    # Remove aspas e crases que quebrariam a string dentro do script PowerShell
    # (proteção básica contra erro de sintaxe / injeção no comando).
    texto_safe = texto.replace("'", " ").replace('"', ' ').replace('`', ' ')
    script = (
        "Add-Type -AssemblyName System.Speech; "
        "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
        "$s.Rate = -1; "  # levemente mais lento para clareza
        f"$s.Speak('{texto_safe}')"
    )
    try:
        # timeout evita que um PowerShell travado segure a thread para sempre.
        subprocess.run(
            ['powershell', '-NonInteractive', '-Command', script],
            capture_output=True, timeout=30,
        )
    except Exception:
        pass


def _falar_espeak(texto: str) -> bool:
    """Fala ``texto`` via espeak/espeak-ng no Linux.

    Returns:
        True se o binário foi encontrado e executado com sucesso; False caso
        contrário (ausente ou erro), para que o caller tente o próximo backend.
    """
    import shutil
    # Prefere espeak-ng (versão mais moderna) e cai para espeak clássico.
    exe = shutil.which('espeak-ng') or shutil.which('espeak')
    if not exe:
        return False
    try:
        # -v pt-br seleciona a voz brasileira; -s 140 ajusta a velocidade.
        r = subprocess.run(
            [exe, '-v', 'pt-br', '-s', '140', texto],
            capture_output=True, timeout=30,
        )
        return r.returncode == 0
    except Exception:
        return False
