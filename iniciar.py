"""
================================================================================
 Arquivo......: iniciar.py
 Propósito....: Launcher (inicializador) do sistema SASE.
================================================================================

 O QUE FAZ
 ---------
 Este módulo é o ponto de entrada único do SASE (Sistema de Atendimento por
 Senha Eletrônica). Ele prepara todo o ambiente e sobe os quatro processos que
 compõem o sistema distribuído. Em ordem, ele:

   1. Detecta o sistema operacional (Windows/Linux) e, no Linux, cria um
      ambiente virtual (venv) isolado chamado "SASE".
   2. No Linux, usa os.execv para RE-EXECUTAR este próprio script já dentro do
      interpretador Python da venv, sem abrir uma nova janela de terminal.
   3. Instala automaticamente as dependências Python (pygame, fpdf2, pyttsx3)
      via pip, caso ainda não estejam disponíveis.
   4. Lança os 4 módulos do sistema (SRV, TV, TS, TA) como processos
      independentes via subprocess.Popen.
   5. Exibe um terminal estilizado: banner ASCII, spinner animado, barra de
      progresso e cores ANSI para feedback visual ao operador.

 COMO USAR
 ---------
   $ python3 iniciar.py
 Nenhum passo manual é necessário: o próprio launcher cuida da venv e das
 dependências. Basta executar e aguardar a mensagem de "iniciado com sucesso".

 ARQUITETURA / PROTOCOLO DE COMUNICAÇÃO
 --------------------------------------
 O SASE segue uma arquitetura cliente-servidor. O módulo SRV é o servidor
 central; TV, TS e TA são clientes que se comunicam com ele pela rede (sockets
 TCP/IP). Este launcher NÃO participa do protocolo de rede em si — ele apenas
 garante que o servidor suba ANTES dos clientes (ver constante DELAYS), evitando
 que os clientes tentem conectar a um servidor que ainda não abriu o socket de
 escuta. Cada módulo roda em seu próprio processo de SO, isolado, como convém a
 nós distintos de um sistema distribuído rodando na mesma máquina (ou em várias).

 Disciplina..: Sistemas Distribuídos — IFCE Campus Crato
================================================================================
"""

import sys
import os

# =============================================================================
# ── Bootstrap de venv — DEVE ser o primeiro código executado ─────────────────
# No Linux: cria a venv SASE e re-executa este script dentro dela,
# sem que o usuário precise fazer nada além de rodar "python3 iniciar.py".
# No Windows: passa direto, sem criar venv.
# =============================================================================

def _bootstrap_venv():
    """Garante que o script esteja rodando dentro do venv isolado do SASE.

    Mecanismo central do launcher no Linux. A ideia é dar ao usuário uma
    experiência "rode e funciona": ao invocar o interpretador global do sistema,
    o launcher cria uma venv própria e então TROCA o processo atual pelo Python
    dessa venv usando os.execv. Isso é necessário porque não há como "entrar" em
    uma venv já com o interpretador em execução — o isolamento de pacotes é
    determinado no momento em que o interpretador inicia. A re-execução via
    os.execv resolve isso sem abrir um novo terminal (ao contrário de Popen, que
    criaria um processo filho e poderia abrir/duplicar janela).

    Em Windows a função retorna imediatamente: o fluxo de venv não é aplicado
    para manter a simplicidade no ambiente onde os alunos costumam ter o Python
    instalado globalmente.

    Returns:
        None: a função não retorna valor útil. No caminho de sucesso do Linux
        ela NUNCA retorna de fato, pois os.execv substitui a imagem do processo.
    """
    if os.name == 'nt':
        return  # Windows: executa normalmente, sem criar venv

    # Caminhos absolutos derivados da localização deste arquivo, para que o
    # launcher funcione independentemente do diretório de onde foi chamado.
    base     = os.path.dirname(os.path.abspath(__file__))
    venv_dir = os.path.join(base, 'SASE')
    venv_py  = os.path.join(venv_dir, 'bin', 'python')

    # Se sys.prefix já aponta para a venv, então o script JÁ está rodando dentro
    # dela (provavelmente após o os.execv). Evita loop infinito de re-execução.
    if os.path.abspath(sys.prefix) == os.path.abspath(venv_dir):
        return

    # Cria a venv apenas se o interpretador dela ainda não existir no disco.
    if not os.path.isfile(venv_py):
        print("\n  Preparando ambiente virtual SASE...")
        import subprocess as _sp
        # capture_output evita poluir o terminal estilizado com a saída crua do
        # módulo venv; só mostramos algo se houver erro.
        r = _sp.run(
            [sys.executable, '-m', 'venv', venv_dir],
            capture_output=True, text=True,
        )
        if r.returncode != 0:
            # Falha ao criar a venv não é fatal: degradamos graciosamente e
            # seguimos com o interpretador global, avisando o usuário.
            print("  Aviso: nao foi possivel criar o ambiente virtual.")
            print("  " + r.stderr.strip())
            print("  Continuando sem isolamento...\n")
            return
        print("  Ambiente criado. Reiniciando dentro do ambiente isolado...\n")

    # Substitui a imagem do processo atual pelo Python da venv (mesmo PID, mesma
    # janela de terminal). os.execv NÃO retorna em caso de sucesso — a execução
    # recomeça do topo do script, mas agora com sys.prefix == venv_dir, fazendo
    # a checagem acima retornar e o fluxo seguir normalmente já isolado.
    # Passamos sys.argv para preservar quaisquer argumentos de linha de comando.
    os.execv(venv_py, [venv_py] + sys.argv)

# Executa o bootstrap imediatamente, antes de qualquer import de terceiros, pois
# tais imports precisam resolver para os pacotes da venv, não os do sistema.
_bootstrap_venv()

# =============================================================================
# ── Imports normais ──────────────────────────────────────────────────────────
# No Linux, a partir daqui já estamos dentro da venv (graças ao os.execv acima),
# então estes imports e os pip installs futuros afetam o ambiente isolado.
# =============================================================================

import subprocess
import time
import threading

# True somente quando a saída padrão é um terminal interativo (TTY). Quando o
# launcher é executado com saída redirecionada (pipe/arquivo), desligamos as
# animações e cores ANSI para não sujar logs com sequências de escape.
_TTY = sys.stdout.isatty()

# No Windows, os.system("") força o console (cmd.exe legado) a habilitar o
# processamento de sequências de escape ANSI; sem isso, as cores apareceriam
# como lixo textual. Inócuo em terminais modernos.
if _TTY and os.name == "nt":
    os.system("")   # habilita ANSI no Windows

# ── Constantes de estilo ANSI ────────────────────────────────────────────────
# Cada constante é uma sequência de escape ANSI usada para colorir/formatar a
# saída. Quando _TTY é False, todas viram string vazia: assim o mesmo código de
# print funciona com e sem terminal, sem precisar de ifs espalhados. O PORQUÊ de
# guardar em constantes curtas é manter as f-strings de saída legíveis.
R  = "\033[0m"  if _TTY else ""   # reset: zera toda formatação aplicada
B  = "\033[1m"  if _TTY else ""   # bold (negrito): destaca títulos/status
D  = "\033[2m"  if _TTY else ""   # dim (esmaecido): texto secundário/detalhes

VD = "\033[92m" if _TTY else ""    # verde   — sucesso/OK
AM = "\033[93m" if _TTY else ""    # amarelo — aviso/em andamento
AZ = "\033[94m" if _TTY else ""    # azul    — destaque informativo
CI = "\033[96m" if _TTY else ""    # ciano   — molduras e títulos de seção
BR = "\033[97m" if _TTY else ""    # branco  — texto principal de alto contraste
VM = "\033[91m" if _TTY else ""    # vermelho— erro/falha

# Diretório raiz do projeto (onde este arquivo vive) e caminho do interpretador
# Python atual. 'py' é reutilizado para lançar subprocessos garantindo que eles
# usem EXATAMENTE o mesmo Python (da venv, no Linux) que está rodando o launcher.
base = os.path.dirname(os.path.abspath(__file__))
py   = sys.executable

# ── Dependências de terceiros ────────────────────────────────────────────────
# Cada item é uma tupla (modulo, pacote, obrigatorio):
#   - modulo:      nome usado em "import <modulo>" para testar se já está presente
#                  (note que pode diferir do nome no PyPI — ex.: fpdf vs fpdf2).
#   - pacote:      nome usado em "pip install <pacote>" (nome de distribuição).
#   - obrigatorio: se True, falha na instalação aborta o launcher; se False, o
#                  sistema segue sem o recurso (degradação graciosa).
# Todas estão como opcionais (False) pois o sistema tolera ausência de áudio
# (pyttsx3), geração de PDF (fpdf2) ou recursos gráficos extras (pygame),
# funcionando em modo reduzido.
DEPENDENCIAS = [
    ("pygame",  "pygame",  False),
    ("fpdf",    "fpdf2",   False),
    ("pyttsx3", "pyttsx3", False),
]

# ---------------------------------------------------------------------------
# ── Spinner ─────────────────────────────────────────────────────────────────
# Indicador de "carregando" animado que roda em uma thread separada enquanto a
# tarefa principal (instalar pacote, checar import, etc.) bloqueia a main thread.
# ---------------------------------------------------------------------------

class Spinner:
    """Spinner textual animado executado em thread de background.

    Responsabilidade: dar feedback visual de "trabalho em progresso" durante
    operações bloqueantes (subprocessos pip, verificações, delays), sem congelar
    a percepção do usuário. A animação roda numa thread daemon dedicada; a thread
    principal continua executando a tarefa real e, ao terminar, chama um dos
    métodos de finalização (ok/aviso/erro) que param a animação e imprimem o
    status final na mesma linha.

    Padrão de design: encapsula o par "thread de animação + Event de parada",
    funcionando como um pequeno gerenciador de recurso. Em ambiente sem TTY, o
    spinner se degrada para simples prints, mantendo a mesma interface pública.
    """

    # Quadros da animação clássica de "barra giratória" ASCII; ciclados em loop.
    _FRAMES = ["|", "/", "-", "\\"]

    def __init__(self, msg):
        """Inicia o spinner e, em TTY, dispara a thread de animação.

        Args:
            msg (str): rótulo exibido ao lado do spinner, descrevendo a tarefa
                em andamento (ex.: nome do pacote sendo instalado).
        """
        self._msg = msg
        if _TTY:
            # Event funciona como flag thread-safe para sinalizar parada.
            self._stop = threading.Event()
            # daemon=True garante que a thread não impeça o processo de encerrar.
            self._th   = threading.Thread(target=self._run, daemon=True)
            self._th.start()

    def _run(self):
        """Loop de animação executado na thread de background.

        Reescreve continuamente a mesma linha do terminal usando o retorno de
        carro "\\r", trocando o quadro do spinner a cada ciclo até que o Event
        de parada seja acionado.
        """
        i = 0
        while not self._stop.is_set():
            # "\r" volta o cursor ao início da linha para sobrescrever o quadro
            # anterior, criando a ilusão de animação no lugar.
            sys.stdout.write("\r  [{}{}{}] {}{}{}   ".format(
                AM, self._FRAMES[i % 4], R, D, self._msg, R))
            sys.stdout.flush()
            time.sleep(0.09)  # ~11 fps: rápido o bastante para parecer fluido
            i += 1

    def _parar(self):
        """Sinaliza a thread de animação para parar e aguarda seu término.

        Faz join() para garantir que a thread não escreva mais nada na linha
        depois que o status final for impresso (evita corrida visual).
        """
        if _TTY:
            self._stop.set()
            self._th.join()

    def ok(self, detalhe=""):
        """Finaliza o spinner com status de sucesso (verde, [OK]).

        Args:
            detalhe (str): texto opcional anexado após a mensagem, esmaecido,
                com informação extra (ex.: "ja instalado").
        """
        self._parar()
        det = ("  " + detalhe) if detalhe else ""
        if _TTY:
            extra = "  {}{}{}".format(D, detalhe, R) if detalhe else ""
            print("\r  [{}{}OK{}] {}{}{}{}   ".format(B, VD, R, B, self._msg, R, extra))
        else:
            print("  [ OK ] {}{}".format(self._msg, det))

    def aviso(self, detalhe=""):
        """Finaliza o spinner com status de aviso (amarelo, [!!]).

        Usado quando a tarefa não falhou de forma fatal, mas algo merece atenção
        (ex.: pacote opcional ausente, backend de voz não encontrado).

        Args:
            detalhe (str): texto opcional com a explicação do aviso.
        """
        self._parar()
        det = ("  " + detalhe) if detalhe else ""
        if _TTY:
            extra = "  {}{}{}".format(D, detalhe, R) if detalhe else ""
            print("\r  [{}{}!!{}] {}{}{}{}   ".format(B, AM, R, B, self._msg, R, extra))
        else:
            print("  [ !! ] {}{}".format(self._msg, det))

    def erro(self, detalhe=""):
        """Finaliza o spinner com status de erro (vermelho, [ERR]).

        Args:
            detalhe (str): texto opcional descrevendo a causa da falha.
        """
        self._parar()
        det = ("  " + detalhe) if detalhe else ""
        if _TTY:
            extra = "  {}{}{}".format(VM, detalhe, R) if detalhe else ""
            print("\r  [{}{}ERR{}] {}{}{}{}   ".format(B, VM, R, B, self._msg, R, extra))
        else:
            print("  [ERR] {}{}".format(self._msg, det))


# ---------------------------------------------------------------------------
# ── Helpers de saída ─────────────────────────────────────────────────────────
# Pequenas funções utilitárias para desenhar a interface de texto do launcher.
# ---------------------------------------------------------------------------

def _linha(cor=D, char="=", n=52):
    """Imprime uma linha horizontal divisória.

    Args:
        cor (str): sequência ANSI de cor aplicada à linha (padrão: dim).
        char (str): caractere que compõe a linha (padrão: "=").
        n (int): quantidade de caracteres / largura da linha. 52 foi escolhido
            para alinhar com a largura do banner e das molduras do menu.
    """
    print("{}{}{}".format(cor, char * n, R))

def _secao(titulo):
    """Imprime um cabeçalho de seção com título em ciano e régua à direita.

    Args:
        titulo (str): nome da seção (ex.: "Dependencias"). A régua de traços é
            dimensionada para preencher até a coluna 48, mantendo alinhamento
            visual consistente entre seções de títulos de tamanhos diferentes.
    """
    print()
    print("  {}{}{}{} {}".format(B, CI, titulo, R, D + "-" * (48 - len(titulo)) + R))

def _escrever(texto, delay=0.025, cor=BR):
    """Imprime texto com efeito de "máquina de escrever" (caractere a caractere).

    Em ambientes sem TTY, imprime de uma vez só (sem efeito) para não desperdiçar
    tempo nem inserir atrasos em logs não interativos.

    Args:
        texto (str): conteúdo a ser exibido.
        delay (float): atraso em segundos entre cada caractere; controla a
            "velocidade de digitação".
        cor (str): sequência ANSI de cor aplicada a todo o texto.
    """
    if not _TTY:
        print(texto)
        return
    sys.stdout.write(cor)
    for ch in texto:
        sys.stdout.write(ch)
        sys.stdout.flush()  # flush por caractere é o que torna o efeito visível
        time.sleep(delay)
    sys.stdout.write(R + "\n")
    sys.stdout.flush()


# ---------------------------------------------------------------------------
# ── Banner ───────────────────────────────────────────────────────────────────
# ---------------------------------------------------------------------------

# Arte ASCII com a sigla "SASE" exibida na abertura. Strings raw (r"...") para
# que as contrabarras da arte não sejam interpretadas como escapes.
BANNER = [
    r"  ____    _    ____  _____",
    r" / ___|  / \  / ___|| ____|",
    r" \___ \ / _ \ \___ \|  _|",
    r"  ___) / ___ \ ___) | |___",
    r" |____/_/   \_\____/|_____|",
]

def _banner():
    """Limpa a tela e desenha o banner de abertura do SASE com animação.

    Em TTY, cada linha da arte é "digitada" caractere a caractere para um efeito
    de revelação; sem TTY, as linhas são impressas direto. Inclui as legendas da
    instituição e da disciplina.
    """
    # Limpa a tela usando o comando apropriado ao SO.
    os.system("cls" if os.name == "nt" else "clear")
    _linha(cor=B + CI)
    for row in BANNER:
        if _TTY:
            sys.stdout.write(B + BR)
            for ch in row:
                sys.stdout.write(ch)
                sys.stdout.flush()
                time.sleep(0.004)  # bem rápido: revela a arte sem demorar
            sys.stdout.write(R + "\n")
            time.sleep(0.05)       # pausa curta entre linhas da arte
        else:
            print(row)
    print()
    _escrever("  Sistema de Atendimento por Senha Eletronica", delay=0.015, cor=B + BR)
    _escrever("  Instituto Federal do Ceara  |  Campus Crato  |  Sistemas Distribuidos",
              delay=0.008, cor=D)
    _linha(cor=B + CI)


# ---------------------------------------------------------------------------
# ── Verificação do ambiente Python ───────────────────────────────────────────
# ---------------------------------------------------------------------------

def _verificar_python():
    """Verifica se a versão do interpretador atende ao mínimo exigido (3.8+).

    Recursos de sintaxe e bibliotecas usados pelo projeto exigem Python 3.8 ou
    superior. Se a versão for inferior, exibe instruções de download e encerra o
    launcher com código de saída 1, pois nada mais funcionaria corretamente.

    Raises:
        SystemExit: encerra o processo com status 1 quando a versão é antiga.
    """
    _secao("Ambiente")
    sp = Spinner("Python")
    major, minor = sys.version_info[:2]
    time.sleep(0.5)  # pequena pausa só para o spinner ser perceptível

    if major < 3 or (major == 3 and minor < 8):
        sp.erro("versao {}.{} — necessario 3.8+".format(major, minor))
        print()
        print("  Download: https://www.python.org/downloads/")
        print()
        input("Pressione ENTER para sair...")
        sys.exit(1)

    sp.ok("versao {}.{}".format(major, minor))


def _verificar_tkinter():
    """Verifica a disponibilidade do tkinter e tenta instalá-lo se faltar.

    O tkinter fornece a interface gráfica usada pelos terminais do SASE. Por ser
    um binding para a biblioteca Tk do SISTEMA (não um pacote pip puro), sua
    ausência precisa ser resolvida pelo gerenciador de pacotes do SO. A função
    testa "import tkinter" num subprocesso e, se falhar, tenta instalar via
    pacman/apt/dnf usando "sudo -n" (não interativo: só funciona se já houver
    credencial em cache; nunca trava pedindo senha).

    Returns:
        bool: True se o tkinter está disponível (originalmente ou após instalar);
        False se não foi possível garantir a presença (o sistema seguirá, mas a
        GUI pode não abrir).
    """
    import shutil
    _secao("Verificando interface grafica")
    sp = Spinner("tkinter")
    time.sleep(0.3)
    # Testa o import num subprocesso isolado para não importar Tk neste processo.
    resultado = subprocess.run(
        [py, "-c", "import tkinter"],
        capture_output=True
    )
    if resultado.returncode == 0:
        sp.ok("disponivel")
        return True
    sp.erro("libtk nao encontrada")
    print()
    print("  {}{}A interface grafica (tkinter) requer o pacote Tk do sistema.{}".format(VM, B, R))
    print("  Instalando automaticamente...")
    # Mapeia o comando de instalação para os gerenciadores de pacote mais comuns
    # em distribuições Linux. Tentamos na ordem; o primeiro presente é usado.
    gerenciadores = [
        (['pacman', '-S', '--noconfirm', 'tk'],   'pacman'),
        (['apt-get', 'install', '-y', 'python3-tk'], 'apt'),
        (['dnf', 'install', '-y', 'python3-tkinter'], 'dnf'),
    ]
    for cmd_args, nome_mgr in gerenciadores:
        # shutil.which detecta se o gerenciador existe no PATH; pula os ausentes.
        exe = shutil.which(cmd_args[0])
        if not exe:
            continue
        sp2 = Spinner("instalando tk via {}".format(nome_mgr))
        # "sudo -n": modo não interativo. Se não houver sudo sem senha em cache,
        # falha de imediato em vez de bloquear o launcher aguardando digitação.
        r = subprocess.run(
            ['sudo', '-n'] + cmd_args,
            capture_output=True, text=True
        )
        if r.returncode == 0:
            # Reconfirma que o import passa a funcionar após a instalação.
            res = subprocess.run([py, "-c", "import tkinter"], capture_output=True)
            if res.returncode == 0:
                sp2.ok("instalado com sucesso")
                return True
        sp2.erro("falhou (execute manualmente: sudo {} {})".format(nome_mgr, ' '.join(cmd_args[1:])))
        break  # achamos o gerenciador certo mas falhou: não tentar os outros
    # Caminho final: orienta o usuário a instalar manualmente por distribuição.
    print()
    print("  {}{}ACAO NECESSARIA:{} Instale o Tk manualmente:".format(AM, B, R))
    print("    Arch Linux:    {}sudo pacman -S tk{}".format(B, R))
    print("    Ubuntu/Debian: {}sudo apt install python3-tk{}".format(B, R))
    print("    Fedora:        {}sudo dnf install python3-tkinter{}".format(B, R))
    print()
    return False


# ---------------------------------------------------------------------------
# ── Dependências ─────────────────────────────────────────────────────────────
# ---------------------------------------------------------------------------

def _pip(pacote):
    """Instala um pacote via pip, priorizando wheels binárias (sem compilar C).

    Estratégia em duas tentativas:
      1) "--only-binary :all:": força o pip a baixar apenas wheels pré-compiladas.
         Isso EVITA a compilação de extensões C na máquina do usuário (que exige
         toolchain de build, é lenta e frequentemente falha em ambientes
         acadêmicos sem compilador). Timeout curto (90s) porque baixar wheel é
         rápido.
      2) Fallback sem restrição: se não houver wheel para a plataforma, permite
         a instalação normal (que pode compilar do source), com timeout bem maior
         (360s) por ser potencialmente demorada.

    Args:
        pacote (str): nome de distribuição do pacote no PyPI (ex.: "fpdf2").

    Returns:
        tuple[bool, str]: (sucesso, mensagem_de_erro). Em caso de sucesso, a
        segunda posição é string vazia; em falha, traz o stderr ou a causa.
    """
    # Tentativa 1 — wheel pré-compilada (sem compilação C, muito mais rápido).
    try:
        r = subprocess.run(
            [py, "-m", "pip", "install", pacote, "-q", "--no-input",
             "--only-binary", ":all:"],
            capture_output=True, text=True, timeout=90,
        )
        if r.returncode == 0:
            return True, ""
    except Exception:
        # Qualquer problema aqui (timeout, sem wheel) cai no fallback abaixo.
        pass

    # Tentativa 2 — instalação normal (pode compilar do source), timeout maior.
    try:
        r = subprocess.run(
            [py, "-m", "pip", "install", pacote, "-q", "--no-input"],
            capture_output=True, text=True, timeout=360,
        )
        return r.returncode == 0, r.stderr
    except subprocess.TimeoutExpired:
        return False, "pip demorou mais de 6 minutos."
    except Exception as e:
        return False, str(e)


def _import_ok(modulo):
    """Confirma, em subprocesso isolado, se um módulo pode ser importado.

    Roda o import num processo separado para que um eventual import com efeitos
    colaterais (ou que trave) não afete o processo do launcher.

    Args:
        modulo (str): nome do módulo a testar (ex.: "pygame").

    Returns:
        bool: True se "import <modulo>" retorna código 0; False caso contrário.
    """
    return subprocess.run(
        [py, "-c", "import {}".format(modulo)], capture_output=True
    ).returncode == 0


def _verificar_voz_linux():
    """Verifica, no Linux, a disponibilidade completa do TTS (espeak-ng + pyttsx3).

    Testa se o binário espeak-ng existe E se o pyttsx3 consegue inicializar
    o motor de voz sem erro (subprocesso com timeout, para não bloquear o
    launcher). Exibe [OK] voz disponivel ou um aviso com a causa.
    """
    import shutil
    sp = Spinner("voz (TTS)")
    time.sleep(0.2)
    exe = shutil.which('espeak-ng') or shutil.which('espeak')
    if not exe:
        sp.aviso("espeak-ng nao encontrado — instale: sudo pacman -S espeak-ng")
        return
    # Testa se pyttsx3 consegue inicializar o engine sem produzir audio.
    r = subprocess.run(
        [py, "-c", "import pyttsx3; e=pyttsx3.init(); e.stop()"],
        capture_output=True, timeout=8,
    )
    if r.returncode == 0:
        sp.ok("disponivel")
    else:
        sp.ok("disponivel  (via espeak-ng direto)")


def _verificar_dependencias():
    """Verifica e, se necessário, instala cada dependência da lista DEPENDENCIAS.

    Para cada (modulo, pacote, obrigatorio): tenta importar; se já presente,
    marca OK; senão, instala via _pip e revalida com _import_ok. Falha em pacote
    obrigatório encerra o launcher; em opcional, apenas avisa e continua. Ao
    final, no Linux, checa também o backend de voz (espeak).

    Raises:
        SystemExit: encerra com status 1 se uma dependência obrigatória falhar.
    """
    _secao("Dependencias")

    for modulo, pacote, obrigatorio in DEPENDENCIAS:
        # Caminho rápido: se já dá para importar aqui mesmo, não há o que instalar.
        try:
            __import__(modulo)
            sp = Spinner(pacote)
            time.sleep(0.25)
            sp.ok("ja instalado")
            continue
        except ImportError:
            pass

        # Em saída não interativa, registra a intenção de instalar (sem spinner).
        if not _TTY:
            print("  [ .. ] {} — instalando...".format(pacote))
        sp = Spinner(pacote)
        sucesso, stderr = _pip(pacote)

        if not sucesso:
            sp.erro("falha na instalacao")
            # Mostra no máximo 4 linhas do stderr para dar pista sem inundar a tela.
            if stderr.strip():
                for ln in stderr.strip().splitlines()[:4]:
                    print("  {}  {}{}".format(VM, ln.strip(), R))
            if obrigatorio:
                input("\n  Pressione ENTER para sair...")
                sys.exit(1)
            else:
                print("  {}{}Continuando sem '{}' (opcional).{}".format(D, AM, pacote, R))
            continue

        # Instalou: confirma que o módulo realmente carrega (wheel pode estar
        # quebrada ou faltar dependência de sistema).
        if _import_ok(modulo):
            sp.ok("instalado com sucesso")
        else:
            sp.aviso("instalado mas nao carregou — funcoes podem falhar")

    # No Linux, verifica TTS (espeak-ng + pyttsx3).
    if sys.platform.startswith('linux'):
        _verificar_voz_linux()


# ---------------------------------------------------------------------------
# ── Módulos do sistema ───────────────────────────────────────────────────────
# ---------------------------------------------------------------------------

# Os quatro processos que compõem o SASE, em ORDEM DE INICIALIZAÇÃO.
# Cada item: (caminho_relativo_do_script, sigla, nome_legível).
#   SRV — servidor central (deve subir primeiro: abre o socket de escuta).
#   TV  — Terminal de Visualização (painel que mostra as senhas chamadas).
#   TS  — Terminal de Senhas (emite/retira senhas).
#   TA  — Terminal de Atendimento (operador chama a próxima senha).
MODULOS = [
    ("servidor/srv.py", "SRV", "Servidor central"),
    ("clientes/tv.py",  "TV",  "Terminal de Visualizacao"),
    ("clientes/ts.py",  "TS",  "Terminal de Senhas"),
    ("clientes/ta.py",  "TA",  "Terminal de Atendimento"),
]

# Atraso (em segundos) APÓS lançar cada módulo, posição a posição alinhada com
# MODULOS. O SRV tem o maior delay (2.0s) porque é o servidor: os clientes só
# conseguem conectar depois que ele terminou de inicializar e abriu o socket de
# escuta. Sem essa folga, TV/TS/TA poderiam disparar antes do servidor estar
# pronto e falhar na conexão (connection refused). Os clientes têm delays
# decrescentes (apenas para um arranque visual escalonado) e o último (TA) é 0.0
# pois não há mais ninguém esperando por ele.
DELAYS = [2.0, 0.6, 0.4, 0.0]


def _proc(caminho):
    """Lança um módulo como processo independente e detecta crash imediato.

    Usa subprocess.Popen (NÃO subprocess.run nem proc.wait): cada módulo do SASE
    é uma aplicação GUI de vida longa que deve rodar em paralelo e sobreviver ao
    encerramento deste launcher. Popen dispara o processo e retorna na hora, sem
    bloquear — o launcher segue lançando os demais módulos. Esperar pelo processo
    (run/wait) travaria o launcher até a GUI fechar, o que é justamente o
    oposto do desejado num sistema distribuído de processos concorrentes.

    Após lançar, aguarda ~1.2s e consulta poll(): se o processo já morreu nesse
    intervalo, trata-se de crash imediato (erro de import, exceção no startup) —
    capturamos o stderr para exibir a última linha do traceback.

    Args:
        caminho (str): caminho relativo do script do módulo a partir de 'base'.

    Returns:
        subprocess.Popen | None: o objeto do processo em execução, ou None se
        o lançamento falhou (arquivo inexistente) ou o processo morreu logo.
    """
    try:
        proc = subprocess.Popen(
            [py, os.path.join(base, caminho)],
            stderr=subprocess.PIPE,  # capturado para diagnosticar crash imediato
        )
        # Aguarda brevemente para detectar crash imediato no startup do módulo.
        time.sleep(1.2)
        if proc.poll() is not None:
            # poll() != None significa que o processo já terminou -> falhou.
            try:
                _, err = proc.communicate(timeout=1)
                # Exibe a última linha do stderr (normalmente a mensagem do erro).
                print("\n  {}{}ERRO:{} {}".format(VM, B, R, err.decode('utf-8', errors='replace').strip().splitlines()[-1] if err and err.strip() else "processo encerrado imediatamente"))
            except Exception:
                pass
            return None
        return proc
    except FileNotFoundError:
        # O arquivo do módulo não existe no caminho esperado.
        return None
    except Exception:
        # Qualquer outra falha de lançamento é tratada como módulo indisponível.
        return None


def _barra(duracao, largura=34):
    """Anima uma barra de progresso ASCII que se preenche ao longo de 'duracao'.

    Desenha [====    ] crescendo da esquerda para a direita com percentual. A
    cada passo, reescreve a linha com "\\r" e dorme uma fração proporcional, de
    modo que a barra leve exatamente 'duracao' segundos para encher. É puramente
    estética (usada durante o delay do SRV) e não reflete progresso real de I/O.
    Sem TTY, apenas aguarda 'duracao' sem desenhar nada.

    Args:
        duracao (float): tempo total, em segundos, para a barra encher.
        largura (int): número de células da barra (resolução visual). 34 foi
            escolhido para caber confortavelmente e alinhar com o restante da UI.
    """
    if not _TTY:
        time.sleep(duracao)
        return
    for i in range(largura + 1):
        pct  = int((i / largura) * 100)            # percentual concluído
        fill = VD + "=" * i + R                     # parte preenchida (verde)
        vaz  = D + " " * (largura - i) + R          # parte restante (esmaecida)
        sys.stdout.write("\r     [{}{}] {}{}%{}   ".format(fill, vaz, B + VD, pct, R))
        sys.stdout.flush()
        # Divide o tempo total igualmente entre os passos -> velocidade constante.
        time.sleep(duracao / largura)
    print()


def _abrir_modulos():
    """Lança todos os módulos do SASE em ordem, com feedback visual por etapa.

    Itera sobre MODULOS pareado com DELAYS. O primeiro módulo (SRV) ganha
    tratamento especial: enquanto o seu delay de subida corre, mostra a barra de
    progresso animada e depois reescreve a linha como OK (servidor pronto para
    aceitar conexões). Os clientes (TV/TS/TA) usam apenas o spinner curto. Ao
    final, resume eventuais falhas ou confirma a inicialização do sistema.
    """
    _secao("Iniciando modulos")
    falhas = []  # acumula módulos que não subiram, para o resumo final

    for idx, ((caminho, sigla, nome), delay) in enumerate(zip(MODULOS, DELAYS), start=1):
        proc = _proc(caminho)

        if proc is None:
            # Módulo não subiu: registra erro e segue para os demais.
            print("  [{}{}ERR{}] {}{}{} — {}{}{}".format(
                B, VM, R, B, sigla, R, D, nome, R))
            falhas.append("{} — {}".format(sigla, nome))
            continue

        if idx == 1:
            # ── Tratamento especial do SRV (primeiro módulo / servidor) ──
            # Mostra barra de progresso durante o delay de subida do servidor.
            sp = Spinner("{} — {}".format(sigla, nome))
            sp._parar()
            # Linha temporária com status "em andamento" [..].
            sys.stdout.write("\r  [{}{}..{}] {}{}{} — {}{}{}   \n".format(
                B, AM, R, B, sigla, R, D, nome, R))
            _barra(delay)
            # Sobe o cursor 2 linhas para reescrever a linha de status como OK,
            # sobrepondo a versão "[..]" sem deixar duplicatas na tela.
            sys.stdout.write("\033[2A")        # sobe 2 linhas (ANSI cursor up)
            print("  [{}{}OK{}] {}{}{} — {}{}{}   ".format(
                B, VD, R, B, sigla, R, D, nome, R))
            print()                            # ocupa novamente a linha da barra
        else:
            # ── Clientes (TV/TS/TA): apenas spinner por um curto intervalo ──
            sp = Spinner("{} — {}".format(sigla, nome))
            # Usa o delay configurado; se for 0 (caso do TA), aplica um mínimo
            # de 0.35s só para o spinner ser visível ao usuário.
            time.sleep(delay if delay > 0 else 0.35)
            sp.ok()

    print()
    _linha(cor=B + CI)

    # ── Resumo final ──
    if falhas:
        for f in falhas:
            print("  {}{}[ERR]{} {}".format(B, VM, R, f))
        print()
        print("  {}{}Alguns modulos nao abriram. Verifique os arquivos.{}".format(AM, B, R))
    else:
        _escrever("  Sistema SASE iniciado com sucesso!", delay=0.03, cor=B + VD)
        _escrever("  Pode fechar este terminal.", delay=0.02, cor=D)

    _linha(cor=B + CI)
    print()


# ---------------------------------------------------------------------------
# ── Ponto de entrada (Main) ──────────────────────────────────────────────────
# Orquestra a sequência completa: banner -> verificações -> lançamento. A guarda
# __main__ garante que este fluxo só rode quando o arquivo é executado direto,
# não quando importado. (No Linux, neste ponto já estamos dentro da venv.)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    _banner()
    _verificar_python()
    _verificar_tkinter()
    _verificar_dependencias()
    _abrir_modulos()
