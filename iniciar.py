import subprocess
import sys
import os
import time
import threading

if os.name == "nt":
    os.system("")   # habilita ANSI no Windows

R  = "\033[0m"
B  = "\033[1m"
D  = "\033[2m"

VD = "\033[92m"     # verde
AM = "\033[93m"     # amarelo
AZ = "\033[94m"     # azul
CI = "\033[96m"     # ciano
BR = "\033[97m"     # branco
VM = "\033[91m"     # vermelho

base = os.path.dirname(os.path.abspath(__file__))
py   = sys.executable

DEPENDENCIAS = [
    ("pygame", "pygame", False),
    ("fpdf",   "fpdf2",  False),
]

# ---------------------------------------------------------------------------
# Spinner (roda em thread separada enquanto a tarefa bloqueia o main)
# ---------------------------------------------------------------------------

class Spinner:
    _FRAMES = ["|", "/", "-", "\\"]

    def __init__(self, msg):
        self._msg   = msg
        self._stop  = threading.Event()
        self._th    = threading.Thread(target=self._run, daemon=True)
        self._th.start()

    def _run(self):
        i = 0
        while not self._stop.is_set():
            sys.stdout.write("\r  [{}{}{}] {}{}{}   ".format(
                AM, self._FRAMES[i % 4], R, D, self._msg, R))
            sys.stdout.flush()
            time.sleep(0.09)
            i += 1

    def _parar(self):
        self._stop.set()
        self._th.join()

    def ok(self, detalhe=""):
        self._parar()
        extra = "  {}{}{}".format(D, detalhe, R) if detalhe else ""
        print("\r  [{}{}OK{}] {}{}{}{}   ".format(
            B, VD, R, B, self._msg, R, extra))

    def aviso(self, detalhe=""):
        self._parar()
        extra = "  {}{}{}".format(D, detalhe, R) if detalhe else ""
        print("\r  [{}{}!!{}] {}{}{}{}   ".format(
            B, AM, R, B, self._msg, R, extra))

    def erro(self, detalhe=""):
        self._parar()
        extra = "  {}{}{}".format(VM, detalhe, R) if detalhe else ""
        print("\r  [{}{}ERR{}] {}{}{}{}   ".format(
            B, VM, R, B, self._msg, R, extra))


# ---------------------------------------------------------------------------
# Helpers de saída
# ---------------------------------------------------------------------------

def _linha(cor=D, char="=", n=52):
    print("{}{}{}".format(cor, char * n, R))

def _secao(titulo):
    print()
    print("  {}{}{}{} {}".format(B, CI, titulo, R, D + "-" * (48 - len(titulo)) + R))

def _escrever(texto, delay=0.025, cor=BR):
    sys.stdout.write(cor)
    for ch in texto:
        sys.stdout.write(ch)
        sys.stdout.flush()
        time.sleep(delay)
    sys.stdout.write(R + "\n")
    sys.stdout.flush()


# ---------------------------------------------------------------------------
# Banner
# ---------------------------------------------------------------------------

BANNER = [
    r"  ____    _    ____  _____",
    r" / ___|  / \  / ___|| ____|",
    r" \___ \ / _ \ \___ \|  _|",
    r"  ___) / ___ \ ___) | |___",
    r" |____/_/   \_\____/|_____|",
]

def _banner():
    os.system("cls" if os.name == "nt" else "clear")
    _linha(cor=B + CI)
    for row in BANNER:
        sys.stdout.write(B + BR)
        for ch in row:
            sys.stdout.write(ch)
            sys.stdout.flush()
            time.sleep(0.004)
        sys.stdout.write(R + "\n")
        time.sleep(0.05)
    print()
    _escrever("  Sistema de Atendimento por Senha Eletronica", delay=0.015, cor=B + BR)
    _escrever("  Instituto Federal do Ceara  |  Campus Crato  |  Sistemas Distribuidos",
              delay=0.008, cor=D)
    _linha(cor=B + CI)


# ---------------------------------------------------------------------------
# Verificação do Python
# ---------------------------------------------------------------------------

def _verificar_python():
    _secao("Ambiente")
    sp = Spinner("Python")
    major, minor = sys.version_info[:2]
    time.sleep(0.5)

    if major < 3 or (major == 3 and minor < 8):
        sp.erro("versao {}.{} — necessario 3.8+".format(major, minor))
        print()
        print("  Download: https://www.python.org/downloads/")
        print()
        input("Pressione ENTER para sair...")
        sys.exit(1)

    sp.ok("versao {}.{}".format(major, minor))


# ---------------------------------------------------------------------------
# Dependências
# ---------------------------------------------------------------------------

def _pip(pacote):
    """Roda pip install. O spinner já está em thread, então bloquear aqui é ok."""
    try:
        r = subprocess.run(
            [py, "-m", "pip", "install", pacote, "-q", "--no-input"],
            capture_output=True, text=True, timeout=180,
        )
        return r.returncode == 0, r.stderr
    except subprocess.TimeoutExpired:
        return False, "pip demorou mais de 3 minutos."
    except Exception as e:

        
        return False, str(e)


def _import_ok(modulo):
    return subprocess.run(
        [py, "-c", "import {}".format(modulo)], capture_output=True
    ).returncode == 0


def _verificar_dependencias():
    _secao("Dependencias")

    for modulo, pacote, obrigatorio in DEPENDENCIAS:
        try:
            __import__(modulo)
            sp = Spinner(pacote)
            time.sleep(0.25)
            sp.ok("ja instalado")
            continue
        except ImportError:
            pass

        sp = Spinner("{} — instalando...".format(pacote))
        sucesso, stderr = _pip(pacote)

        if not sucesso:
            sp.erro("falha na instalacao")
            if stderr.strip():
                for ln in stderr.strip().splitlines()[:4]:
                    print("  {}  {}{}".format(VM, ln.strip(), R))
            if obrigatorio:
                input("\n  Pressione ENTER para sair...")
                sys.exit(1)
            else:
                print("  {}{}Continuando sem '{}' (opcional).{}".format(D, AM, pacote, R))
            continue

        if _import_ok(modulo):
            sp.ok("instalado com sucesso")
        else:
            sp.aviso("instalado mas nao carregou — funcoes podem falhar")


# ---------------------------------------------------------------------------
# Módulos
# ---------------------------------------------------------------------------

MODULOS = [
    ("servidor/srv.py", "SRV", "Servidor central"),
    ("clientes/tv.py",  "TV",  "Terminal de Visualizacao"),
    ("clientes/ts.py",  "TS",  "Terminal de Senhas"),
    ("clientes/ta.py",  "TA",  "Terminal de Atendimento"),
]

DELAYS = [2.0, 0.6, 0.4, 0.0]


def _proc(caminho):
    try:
        return subprocess.Popen([py, os.path.join(base, caminho)])
    except FileNotFoundError:
        return None
    except Exception:
        return None


def _barra(duracao, largura=34):
    for i in range(largura + 1):
        pct  = int((i / largura) * 100)
        fill = VD + "=" * i + R
        vaz  = D + " " * (largura - i) + R
        sys.stdout.write("\r     [{}{}] {}{}%{}   ".format(fill, vaz, B + VD, pct, R))
        sys.stdout.flush()
        time.sleep(duracao / largura)
    print()


def _abrir_modulos():
    _secao("Iniciando modulos")
    falhas = []

    for idx, ((caminho, sigla, nome), delay) in enumerate(zip(MODULOS, DELAYS), start=1):
        proc = _proc(caminho)

        if proc is None:
            print("  [{}{}ERR{}] {}{}{} — {}{}{}".format(
                B, VM, R, B, sigla, R, D, nome, R))
            falhas.append("{} — {}".format(sigla, nome))
            continue

        if idx == 1:
            sp = Spinner("{} — {}".format(sigla, nome))
            _barra.__doc__  # warmup
            sp._parar()
            sys.stdout.write("\r  [{}{}..{}] {}{}{} — {}{}{}   \n".format(
                B, AM, R, B, sigla, R, D, nome, R))
            _barra(delay)
            # reimprime como OK
            sys.stdout.write("\033[2A")        # sobe 2 linhas
            print("  [{}{}OK{}] {}{}{} — {}{}{}   ".format(
                B, VD, R, B, sigla, R, D, nome, R))
            print()                            # ocupa a linha da barra
        else:
            sp = Spinner("{} — {}".format(sigla, nome))
            time.sleep(delay if delay > 0 else 0.35)
            sp.ok()

    print()
    _linha(cor=B + CI)

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
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    _banner()
    _verificar_python()
    _verificar_dependencias()
    _abrir_modulos()
