import subprocess
import sys
import os
import time

# Habilita cores ANSI no terminal do Windows
if os.name == "nt":
    os.system("")

V  = "\033[92m"   # verde
A  = "\033[93m"   # amarelo
VM = "\033[91m"   # vermelho
R  = "\033[0m"    # reset

base = os.path.dirname(os.path.abspath(__file__))
py   = sys.executable

DEPENDENCIAS = [
    ("pygame", "pygame", False),  # (modulo, pacote pip, obrigatorio)
]

# ---------------------------------------------------------------------------
# Helpers de saida
# ---------------------------------------------------------------------------

def ok(msg):
    print("{}  [OK] {}{}".format(V, msg, R))

def aviso(msg):
    print("{}  [!]  {}{}".format(A, msg, R))

def erro(msg, detalhe=""):
    print("{}  [ERRO] {}{}".format(VM, msg, R))
    if detalhe:
        for linha_d in detalhe.strip().splitlines():
            print("{}         {}{}".format(VM, linha_d.strip(), R))


# ---------------------------------------------------------------------------
# Animacoes de terminal
# ---------------------------------------------------------------------------

def escrever(texto, delay=0.03, end="\n"):
    for char in texto:
        sys.stdout.write(char)
        sys.stdout.flush()
        time.sleep(delay)
    sys.stdout.write(end)
    sys.stdout.flush()


def barra(mensagem, duracao, largura=30):
    sys.stdout.write("  {}\n".format(mensagem))
    sys.stdout.flush()
    for i in range(largura + 1):
        preenchido = "=" * i
        vazio      = " " * (largura - i)
        pct        = int((i / largura) * 100)
        sys.stdout.write("\r  [{}{}] {}%".format(preenchido, vazio, pct))
        sys.stdout.flush()
        time.sleep(duracao / largura)
    sys.stdout.write("\n")
    sys.stdout.flush()


def linha(char="-", largura=50):
    print(char * largura)


# ---------------------------------------------------------------------------
# Banner
# ---------------------------------------------------------------------------

BANNER = [
    "  ____    _    ____  _____",
    " / ___|  / \\  / ___|| ____|",
    " \\___ \\ / _ \\ \\___ \\|  _|",
    "  ___) / ___ \\ ___) | |___",
    " |____/_/   \\_\\____/|_____|",
]

def mostrar_banner():
    os.system("cls" if os.name == "nt" else "clear")
    linha("=")
    for row in BANNER:
        escrever(row, delay=0.005)
        time.sleep(0.04)
    print()
    escrever("  Sistema de Atendimento por Senha Eletronica", delay=0.02)
    escrever("  IF Crato  |  Sistemas Distribuidos", delay=0.02)
    linha("=")
    print()


# ---------------------------------------------------------------------------
# Verificacao do Python
# ---------------------------------------------------------------------------

def verificar_python():
    major, minor = sys.version_info[:2]
    sys.stdout.write("  Verificando Python")
    sys.stdout.flush()
    for _ in range(5):
        time.sleep(0.12)
        sys.stdout.write(".")
        sys.stdout.flush()

    if major < 3 or (major == 3 and minor < 8):
        erro("Python 3.8+ necessario. Versao atual: {}.{}".format(major, minor))
        print("  Download: https://www.python.org/downloads/")
        print()
        input("Pressione ENTER para sair...")
        sys.exit(1)

    print("  {}{}.{} [OK]{}".format(V, major, minor, R))


# ---------------------------------------------------------------------------
# Verificacao e instalacao de dependencias
# ---------------------------------------------------------------------------

def _instalar(pacote):
    """Roda pip install e retorna (sucesso, stderr)."""
    try:
        r = subprocess.run(
            [py, "-m", "pip", "install", pacote, "--quiet", "--no-input"],
            capture_output=True,
            text=True,
            timeout=180,
        )
        return r.returncode == 0, r.stderr
    except subprocess.TimeoutExpired:
        return False, "pip demorou mais de 3 minutos — verifique sua conexao."
    except Exception as e:
        return False, str(e)


def _verificar_import(modulo):
    """Tenta importar o modulo em um subprocesso limpo (evita cache desta sessao)."""
    r = subprocess.run(
        [py, "-c", "import {}".format(modulo)],
        capture_output=True,
    )
    return r.returncode == 0


def verificar_dependencias():
    print()
    escrever("  Verificando dependencias...", delay=0.025)
    time.sleep(0.1)

    for modulo, pacote, obrigatorio in DEPENDENCIAS:
        sys.stdout.write("    {} ".format(pacote))
        sys.stdout.flush()

        # Tenta importar primeiro
        try:
            __import__(modulo)
            time.sleep(0.2)
            print("{}ja instalado{}".format(V, R))
            continue
        except ImportError:
            pass

        # Nao encontrado — instala
        print("{}nao encontrado — instalando...{}".format(A, R))
        print()

        sucesso, stderr = _instalar(pacote)

        if not sucesso:
            erro("Falha ao instalar '{}'.".format(pacote), detalhe=stderr)
            if obrigatorio:
                print()
                input("Pressione ENTER para sair...")
                sys.exit(1)
            else:
                aviso("'{}' e opcional — continuando sem ele.".format(pacote))
            continue

        # Verifica se o import funciona agora
        if _verificar_import(modulo):
            ok("'{}' instalado com sucesso.".format(pacote))
        else:
            erro(
                "Instalacao de '{}' relatou sucesso mas o modulo nao carrega.".format(pacote),
                detalhe=stderr or "Tente rodar:  pip install {}".format(pacote),
            )
            if obrigatorio:
                print()
                input("Pressione ENTER para sair...")
                sys.exit(1)
            else:
                aviso("Continuando sem '{}'.".format(pacote))

    print()


# ---------------------------------------------------------------------------
# Abertura dos modulos
# ---------------------------------------------------------------------------

MODULOS = [
    ("servidor/srv.py",  "SRV  Servidor central"),
    ("clientes/tv.py",   "TV   Terminal de Visualizacao"),
    ("clientes/ts.py",   "TS   Terminal de Senhas"),
    ("clientes/ta.py",   "TA   Terminal de Atendimento"),
]

DELAYS = [2.0, 0.6, 0.4, 0.0]


def _abrir(caminho):
    """Abre o modulo e retorna o processo, ou None se falhar."""
    try:
        return subprocess.Popen([py, os.path.join(base, caminho)])
    except FileNotFoundError:
        erro("Arquivo nao encontrado: {}".format(caminho))
        return None
    except Exception as e:
        erro("Nao foi possivel abrir '{}':".format(caminho), detalhe=str(e))
        return None


def abrir_modulos():
    escrever("  Iniciando modulos...", delay=0.03)
    print()
    falhas = []

    for idx, ((caminho, nome), delay) in enumerate(zip(MODULOS, DELAYS), start=1):
        sys.stdout.write("  [{}/{}] {}".format(idx, len(MODULOS), nome))
        sys.stdout.flush()

        proc = _abrir(caminho)

        if proc is None:
            falhas.append(nome)
            continue

        if idx == 1:
            # Servidor: barra de progresso durante a espera
            print()
            barra("  Aguardando servidor ficar pronto...", duracao=delay)
        else:
            for _ in range(4):
                time.sleep(delay / 4 if delay > 0 else 0.1)
                sys.stdout.write(".")
                sys.stdout.flush()
            print(" {}aberto{}".format(V, R))

    print()
    linha("=")

    if falhas:
        for f in falhas:
            erro("Modulo nao abriu: {}".format(f))
        print()
        aviso("O sistema pode funcionar parcialmente. Verifique os erros acima.")
    else:
        escrever("{}  Tudo pronto! Pode fechar este terminal.{}".format(V, R), delay=0.04)

    linha("=")
    print()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def iniciar():
    mostrar_banner()
    verificar_python()
    verificar_dependencias()
    abrir_modulos()


if __name__ == "__main__":
    iniciar()
