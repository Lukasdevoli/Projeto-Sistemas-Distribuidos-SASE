# =============================================================================
# VERSÃO ORIGINAL (CLI) — antes da interface gráfica
# =============================================================================
#
# # clientes/ta.py
# import socket, sys, os
# sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
# from utils import conexao
#
# def iniciar_ta():
#     id_guiche = input("Digite o número deste guichê (ex: 1, 2, 3): ").strip()
#     while True:
#         acao = input("\nAguardando comando... ")
#         if acao.strip().upper() == 'S': break
#         cliente_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
#         try:
#             cliente_socket.connect((conexao.HOST, conexao.PORTA_SRV))
#             cliente_socket.send(f"TA|{id_guiche}".encode('utf-8'))
#             print(f">>> {cliente_socket.recv(1024).decode('utf-8')}")
#         except ConnectionRefusedError:
#             print("Erro: Servidor offline.")
#         finally:
#             cliente_socket.close()
#
# if __name__ == "__main__":
#     iniciar_ta()
#
# =============================================================================
# VERSÃO ATUAL — GUI com chassi físico desenhado em Canvas (terminal de balcão)
# =============================================================================

"""clientes/ta.py — Terminal de Atendimento (TA) do sistema SASE.

PROPÓSITO
    Aplicação cliente operada pelo ATENDENTE no guichê. Sua única função
    operacional é "chamar a próxima senha" da fila gerenciada pelo servidor
    central (SRV). Cada instância representa fisicamente um guichê (1, 2, 3...).

O QUE FAZ
    1. Identifica o guichê (via argumento --guiche=X ou diálogo ao usuário).
    2. Abre uma conexão TCP PERSISTENTE com o SRV e registra o guichê enviando
       "TA_CONECTAR|<id_guiche>".
    3. A cada clique em "CHAMAR PRÓXIMA SENHA", envia "TA_SOLICITAR|<id_guiche>"
       e aguarda a resposta do SRV com a senha a ser atendida.
    4. Atualiza o display (senha grande) e o histórico da sessão.
    5. Permite gerar relatório (TXT/PDF) dos atendimentos do guichê.

COMO USA / EXECUÇÃO
    - Lançado manualmente: `python3 clientes/ta.py` (pergunta o nº do guichê).
    - Lançado pelo SRV: `python3 clientes/ta.py --guiche=2`, permitindo que o
      servidor abra várias instâncias com o número de guichê pré-configurado.

PROTOCOLO DE COMUNICAÇÃO (camada de aplicação sobre TCP/IP)
    Mensagens são strings UTF-8 no formato "COMANDO|ARGUMENTO":
        TA_CONECTAR|<id>    -> registra o guichê na sessão (uma vez, ao abrir).
        TA_SOLICITAR|<id>   -> pede a próxima senha (a cada chamada).
    Resposta esperada do SRV (texto livre), tipicamente:
        "Guichê X chama: N1 — Nome Aqui"  ou  "...Fila vazia..."

    ENQUADRAMENTO ('\n'):
        TCP é um fluxo de bytes sem fronteira de mensagem. Por isso TODA mensagem
        do protocolo (enviada e recebida) termina com '\n'. O receptor acumula os
        bytes em um buffer e processa uma linha por vez, evitando que dois
        TA_SOLICITAR/respostas coalescidos sejam lidos como uma string única.

    DIFERENÇA-CHAVE EM RELAÇÃO AO TS (Terminal de Senha):
        O TS abre/fecha uma conexão a cada operação (curta e descartável).
        O TA mantém UMA conexão persistente durante toda a sessão, pois o
        atendente executa múltiplas chamadas e o socket precisa ficar vivo
        para o ciclo recv()/send() contínuo (ver _loop_conexao).

ARQUITETURA DE THREADS
    Tkinter NÃO é thread-safe. Por isso a thread de rede (_loop_conexao) nunca
    toca em widgets diretamente: ela publica eventos em uma queue.Queue, e a
    thread principal (UI) os consome via root.after (padrão Queue + polling),
    o mesmo padrão usado no TV (Terminal de Visualização).

Disciplina: Sistemas Distribuídos — IFCE Campus Crato.
"""

import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog
import socket
import threading
import queue
import sys
import os
import random
from datetime import datetime

# Permite importar o pacote utils/ a partir da raiz do projeto, mesmo quando
# o script é executado de dentro de clientes/. Sobe um nível e injeta no path
# ANTES dos imports de utils — caso contrário o import abaixo falharia.
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from utils import conexao, audio, relatorio  # conexao: HOST/PORTA; relatorio: TXT/PDF; audio: efeitos

# ── PALETA — Terminal de Balcão (antracito escuro + verde) ──────────────────
# Cores definidas como constantes para manter identidade visual consistente em
# todos os widgets (chassi simulando um equipamento físico de balcão). O verde
# fosforescente remete a displays de painéis de senha reais.
PAREDE     = "#0a0a0a"    # fundo externo (preto da "parede" atrás da máquina)
CORPO      = "#2a2a2a"    # chassi antracito escuro
CORPO_HI   = "#484848"    # cor de bevel/realce das bordas (efeito 3D)
DISPLAY_BG = "#050e05"    # fundo do display (verde quase preto, p/ contraste)
COR_VERDE  = "#00e676"    # verde brilhante (estado conectado / senha ativa)
COR_BOTAO  = "#0d3a1a"    # fundo do botão CHAMAR (verde escuro)
COR_BTN_HI = "#1a7038"    # realce do botão ao passar/pressionar (hover)
COR_TEXTO  = "#e8f5e9"    # texto claro padrão
COR_SUBTEX = "#3a5a3a"    # subtexto / estados neutros
BADGE_BG   = "#060e06"    # fundo do cabeçalho de guichê (placa de identificação)

# ── EASTER EGGS ─────────────────────────────────────────────────────────────
# _PIADAS: acervo de piadas de programador exibidas no TERMINAL (stdout) quando
# o atendente abre o TA mas não informa nenhum número de guichê. É um brinde
# de bom humor da equipe — não tem efeito sobre o protocolo nem sobre a UI.
_PIADAS = [
    "Por que C recebe todas as meninas e Java nao?\nPorque C nao as trata como objetos.",
    "Dois programadores falam sobre vida social.\nUm diz: 'A unica data que recebo e o Java Update.'",
    "Um aluno tenta olhar por baixo da camisa de uma colega.\nEla: 'Ei! O que voce esta fazendo?'\nEle: 'Membros da mesma classe podem acessar a area privada!'",
    "Uma senhora ve um programador fumando e diz:\n'Voce nao deveria fumar, veja o aviso na caixa!'\nEle responde: 'Eu sou programador Java.\nNao nos preocupamos com avisos, apenas com erros.'",
    "Por que os desenvolvedores Java usam oculos?\nPorque eles nao C#!",
    "Eu tive um problema. Usei Java para resolve-lo.\nAgora eu tenho um ProblemFactory.",
    "Quantos programadores sao necessarios para trocar uma lampada?\nZero. Esse e um problema de hardware.",
    "Qual e a maneira orientada a objetos para se tornar rico?\nHeranca.",
    "Programadores C nunca morrem.\nEles sao apenas colocados em VOID.",
    "O que e um programador?\nUm organismo que transforma cafeina e fast food em software.",
    "Um otimista diz: 'O copo esta meio cheio.'\nUm pessimista diz: 'O copo esta meio vazio.'\nUm programador diz: 'O copo e duas vezes maior que o necessario!'",
    "Por que o programador deixou o emprego?\nEle nunca conseguiu arrays.",
    "Programacao e como sexo.\nUm erro e voce deve dar suporte pelo resto da sua vida.",
    "O que e um algoritmo?\nA palavra que programadores usam quando nao querem\nexplicar o que fizeram.",
    "O que e hardware?\nUma parte do computador que voce pode chutar.",
    "Uma consulta SQL entra em um bar, se aproxima de duas tabelas e pergunta:\n'Posso me juntar a voces?'",
    "Um programador ve escrito na parede: 'Enquanto ha esperanca, ha vida.'\nEle edita e escreve: 'Enquanto houver codigo, ha bug.'",
    "Java, Python, C++ e C estao em uma reuniao.\nJava: 'Como fazer as mulheres se interessarem por nos?'\nC++: 'Talvez mais excecoes?'\nPython: 'Devemos definir melhor nossos metodos?'\nC: 'Talvez parar de trata-las como objetos?'",
    "Knock knock.\nQuem esta ai?\nJava!\n... ainda carregando.",
]

# _NOMES_TRISTES: nomes de guichê "de castigo". Quando o usuário deixa o campo
# em branco, o TA não trava: sorteia um destes rótulos bem-humorados e segue
# normalmente. Garante que self.id_guiche nunca fique vazio (o que quebraria a
# montagem das mensagens de protocolo "TA_CONECTAR|<id>").
_NOMES_TRISTES = [
    "Guiche Sem Nome", "Ninguem me nomeou", "Alguem teve preguica de mim",
    "Guiche do Esquecido", "Eu Precisava de um Nome",
    "Sem Identidade S/A", "Por favor me da um nome",
]

def _piada_terminal():
    """Imprime uma piada aleatória no terminal (stdout).

    Chamada exclusivamente quando o atendente abre o TA e não digita o número
    do guichê. Funciona como "castigo" bem-humorado por deixar o campo vazio.
    É puramente cosmético: não afeta a conexão nem a lógica de atendimento.

    Returns:
        None: apenas escreve no stdout.
    """
    sep = "=" * 52
    piada = random.choice(_PIADAS)
    print("\n" + sep)
    print("  Piada do dia (voce nao digitou nada, merece):")
    print()
    for linha in piada.splitlines():
        print("  " + linha)
    print(sep + "\n")


class AppTerminalAtendimento:
    """Aplicação GUI do Terminal de Atendimento (um guichê = uma instância).

    Responsabilidade:
        Orquestrar a interface do atendente e a conexão persistente com o SRV,
        traduzindo cliques em mensagens de protocolo e respostas do servidor em
        atualizações de display/histórico.

    Padrões de design empregados:
        - Producer/Consumer com fila thread-safe: a thread de rede (produtora)
          publica eventos em self._fila_ui; a thread Tk (consumidora) os aplica
          em _poll_queue. Isola operações de socket do laço de eventos da UI.
        - Reconexão automática (retry com backoff fixo) em _loop_conexao.

    Relação com outros módulos:
        - utils.conexao: fornece HOST e PORTA_SRV do servidor.
        - utils.relatorio: gera TXT/PDF a partir de self._historico.
        - SRV: contraparte servidora que mantém a fila e responde às chamadas.
    """

    def __init__(self):
        """Inicializa a aplicação: identifica o guichê, monta a UI e conecta.

        Resolve o número do guichê em duas etapas (argv tem prioridade sobre o
        diálogo), prepara o estado da sessão, constrói a interface e dispara
        tanto o consumidor da fila (_poll_queue) quanto a thread de rede, e por
        fim entra no laço de eventos do Tkinter (bloqueante).
        """
        self.root = tk.Tk()
        # Esconde a janela enquanto resolvemos o nº do guichê: o simpledialog
        # abaixo precisa de uma raiz Tk viva, mas não queremos mostrar a janela
        # principal ainda vazia/sem título correto.
        self.root.withdraw()

        # ── Resolução do identificador do guichê ──────────────────────────
        # Prioridade 1: argumento --guiche=X. O SRV usa exatamente esta forma
        # para lançar várias instâncias do TA já com o número pré-configurado,
        # sem intervenção humana (ex.: subprocess: python ta.py --guiche=3).
        id_guiche = None
        for arg in sys.argv[1:]:
            if arg.startswith("--guiche="):
                id_guiche = arg.split("=", 1)[1].strip()
                break

        # Prioridade 2: execução manual — pergunta ao atendente.
        if not id_guiche:
            id_guiche = simpledialog.askstring(
                "Terminal de Atendimento",
                "Digite o numero deste guiche (ex: 1, 2, 3):",
                parent=self.root
            )
            # Campo vazio/cancelado: dispara o easter egg e atribui um nome
            # "de castigo" para que id_guiche nunca seja vazio/None (evita
            # quebrar as mensagens de protocolo que embutem o id).
            if not id_guiche or not id_guiche.strip():
                _piada_terminal()
                # replace(' ', '-'): o id vira UM único token sem espaços, senão
                # o parsing de guichê na TV (que separa por espaços) extrairia o
                # nome em vez do guichê, exibindo "DIRIJA-SE AO GUICHÊ <nome>".
                id_guiche = random.choice(_NOMES_TRISTES).replace(' ', '-')

        # ── Estado da sessão ──────────────────────────────────────────────
        self.id_guiche     = id_guiche.strip()   # identidade enviada no protocolo
        self._socket       = None                # socket persistente (None = desconectado)
        self._fila_ui      = queue.Queue()       # ponte thread-rede -> thread-UI
        self._ativo        = True                # flag de vida; encerra threads no fechar
        self._historico    = []                  # lista de dicts p/ o relatório
        self._contador_seq = 0                   # nº sequencial de chamadas na sessão

        self.root.deiconify()
        self.root.title(f"TA — Guichê {self.id_guiche}")
        self.root.geometry("460x640")
        self.root.configure(bg=PAREDE)
        self.root.resizable(False, False)
        self.root.protocol("WM_DELETE_WINDOW", self._fechar)

        self._build_ui()      # monta widgets
        self._poll_queue()    # inicia o consumidor de eventos da fila (na thread UI)
        self._conectar()      # dispara a thread de rede
        self.root.mainloop()  # entrega o controle ao laço de eventos do Tkinter

    # ── CORPO DA MÁQUINA (desenhado no Canvas) ────────────────────────────────

    def _build_ui(self):
        """Cria o Canvas de fundo (chassi) e o Frame de conteúdo sobreposto.

        Args:
            (sem argumentos além de self)
        Returns:
            None: popula self._cvs e os widgets internos.
        """
        W, H = 460, 640  # dimensões fixas; a janela não é redimensionável

        self._cvs = tk.Canvas(
            self.root, bg=PAREDE, width=W, height=H,
            highlightthickness=0
        )
        self._cvs.place(x=0, y=0, width=W, height=H)

        self._desenhar_corpo(W, H)

        fc = tk.Frame(self.root, bg=CORPO)
        fc.place(x=22, y=60, width=W - 44, height=510)
        self._build_content(fc)

    def _desenhar_corpo(self, W, H):
        """Desenha, no Canvas, o "chassi físico" do terminal (puramente estético).

        Renderiza sombra, corpo, bevels 3D, parafusos, faixa de marca, LEDs,
        ventilação e knobs. Nada aqui afeta a rede; é a casca visual que faz a
        aplicação parecer um equipamento de balcão real.

        Args:
            W (int): largura útil do canvas em pixels.
            H (int): altura útil do canvas em pixels.
        Returns:
            None: tudo é desenhado diretamente em self._cvs.
        """
        c = self._cvs

        # Sombra
        c.create_rectangle(20, 20, W - 12, H - 12, fill="#050505", outline="")

        # Corpo principal (antracito escuro)
        c.create_rectangle(14, 14, W - 14, H - 14,
                            fill=CORPO, outline="#141414", width=3)

        # Bevel: topo + esquerda
        for i in range(4):
            clr = "#484848" if i < 2 else "#383838"
            c.create_line(17 + i, 17 + i, W - 17 - i, 17 + i, fill=clr, width=1)
            c.create_line(17 + i, 17 + i, 17 + i, H - 17 - i, fill=clr, width=1)

        # Bevel: baixo + direita
        for i in range(4):
            clr = "#0a0a0a" if i < 2 else "#141414"
            c.create_line(17 + i, H - 17 - i, W - 17 - i, H - 17 - i, fill=clr, width=1)
            c.create_line(W - 17 - i, 17 + i, W - 17 - i, H - 17 - i, fill=clr, width=1)

        # Parafusos Phillips em cada canto
        for sx, sy in [(32, 32), (W - 32, 32), (32, H - 32), (W - 32, H - 32)]:
            r = 9
            c.create_oval(sx - r, sy - r, sx + r, sy + r,
                           fill="#1e1e1e", outline="#4a4a4a", width=1)
            c.create_oval(sx - 4, sy - 4, sx + 4, sy + 4,
                           fill="#0a0a0a", outline="")
            c.create_line(sx - 6, sy, sx + 6, sy, fill="#4a4a4a", width=1)
            c.create_line(sx, sy - 6, sx, sy + 6, fill="#4a4a4a", width=1)

        # Faixa de marca (topo do chassi)
        c.create_rectangle(18, 18, W - 18, 56, fill="#1e1e1e", outline="")
        c.create_text(W // 2 - 30, 37,
                      text="IF CRATO  ·  SASE  ·  TERMINAL DE ATENDIMENTO  ·  TA-2026",
                      fill="#3a3a3a", font=("Consolas", 7, "bold"), anchor="center")

        # LED de status na faixa
        self._id_led = c.create_oval(W - 52, 28, W - 38, 42,
                                      fill="#003300", outline="#005500", width=1)
        c.create_oval(W - 68, 28, W - 54, 42, fill="#330000", outline="#550000", width=1)

        # Botão Relatório na faixa: como é desenhado no Canvas (não é um widget
        # Button), o clique é capturado via tag_bind no retângulo -> abre a
        # janela de relatório da sessão.
        self._btn_rel_cvs_x = 26
        self._btn_rel_cvs_y = 28
        self._btn_rel = c.create_rectangle(22, 26, 80, 46,
                                            fill="#1a0a3a", outline="#6630aa", width=1)
        c.create_text(51, 36, text="Relatório",
                      fill="#9966ff", font=("Consolas", 7, "bold"), anchor="center")
        c.tag_bind(self._btn_rel, "<Button-1>", lambda e: self._abrir_relatorio())

        # Linha separadora
        c.create_line(18, 58, W - 18, 58, fill="#1e1e1e", width=2)

        # Slots de ventilação (inferior)
        for i in range(6):
            y0 = H - 65 + i * 8
            c.create_rectangle(60, y0, W - 60, y0 + 5,
                                fill="#1e1e1e", outline="#0a0a0a", width=1)

        # Linha separadora acima dos slots
        c.create_line(18, H - 72, W - 18, H - 72, fill="#1e1e1e", width=2)

        # Etiqueta inferior
        c.create_text(W // 2, H - 18,
                      text=f"[ SASE — TA — GUICHÊ {self.id_guiche} ]",
                      fill="#353535", font=("Consolas", 7, "bold"), anchor="center")

        # Knobs decorativos
        for kx in (34, 60):
            c.create_oval(kx - 9, H - 50, kx + 9, H - 32,
                           fill="#1e1e1e", outline="#3a3a3a", width=2)
            c.create_line(kx, H - 46, kx, H - 34, fill="#3a3a3a", width=2)

        # Botão power
        c.create_oval(W - 54, H - 52, W - 32, H - 30,
                       fill="#111111", outline="#333333", width=2)
        c.create_arc(W - 51, H - 49, W - 35, H - 33,
                      start=50, extent=260, style="arc", outline="#3a3a3a", width=2)
        c.create_line(W - 43, H - 49, W - 43, H - 41, fill="#3a3a3a", width=2)

    # ── CONTEÚDO (Frame sobre o Canvas) ───────────────────────────────────────

    def _build_content(self, parent):
        """Monta os widgets interativos sobre o chassi (Frame de conteúdo).

        Cria o cabeçalho do guichê, o display da senha, o botão CHAMAR (já
        desabilitado até a conexão ser confirmada), o rótulo de status e a
        lista de histórico. Guarda referências (self.lbl_*, self.btn_chamar,
        self.listbox) usadas posteriormente por _poll_queue para atualizar a UI.

        Args:
            parent (tk.Frame): contêiner onde os widgets são empacotados.
        Returns:
            None
        """
        # ── CABEÇALHO GUICHÊ ──────────────────────────────────────────────
        frame_guiche_outer = tk.Frame(parent, bg="#0a1a0a", bd=4, relief="sunken")
        frame_guiche_outer.pack(fill="x", padx=8, pady=(8, 0))

        frame_guiche = tk.Frame(frame_guiche_outer, bg=BADGE_BG)
        frame_guiche.pack(fill="x", padx=3, pady=3)

        frame_row = tk.Frame(frame_guiche, bg=BADGE_BG)
        frame_row.pack(fill="x", padx=10, pady=8)

        tk.Label(
            frame_row, text="GUICHÊ",
            bg=BADGE_BG, fg="#0d2a0d",
            font=("Consolas", 9, "bold")
        ).pack(side="left", pady=4)

        tk.Label(
            frame_row, text=f"  {self.id_guiche}  ",
            bg="#0a2a0a", fg=COR_VERDE,
            font=("Consolas", 20, "bold"),
            padx=8, pady=2
        ).pack(side="left", padx=(8, 0))

        self.lbl_conexao = tk.Label(
            frame_row, text="● Conectando...",
            bg=BADGE_BG, fg="#ff9800",
            font=("Consolas", 8)
        )
        self.lbl_conexao.pack(side="right")

        # LEDs
        self._cvs_led = tk.Canvas(
            frame_row, bg=BADGE_BG,
            width=40, height=26, highlightthickness=0
        )
        self._id_led_btn = self._cvs_led.create_oval(
            4, 6, 16, 18, fill="#003300", outline="#005500", width=1
        )
        self._cvs_led.create_oval(20, 6, 32, 18, fill="#330000", outline="#550000", width=1)
        self._cvs_led.pack(side="right", padx=4)

        # ── DISPLAY DA SENHA ──────────────────────────────────────────────
        frame_disp_outer = tk.Frame(parent, bg="#060e06", bd=4, relief="sunken")
        frame_disp_outer.pack(fill="x", padx=8, pady=(8, 0))

        frame_display = tk.Frame(frame_disp_outer, bg=DISPLAY_BG)
        frame_display.pack(fill="x", padx=3, pady=3)

        tk.Label(
            frame_display, text="ATENDENDO",
            bg=DISPLAY_BG, fg="#0d2a0d",
            font=("Consolas", 8, "bold")
        ).pack(pady=(8, 0))

        self.lbl_senha = tk.Label(
            frame_display, text="---",
            bg=DISPLAY_BG, fg="#0d2a0d",
            font=("Consolas", 60, "bold")
        )
        self.lbl_senha.pack(pady=(0, 8))

        # ── BOTÃO CHAMAR (3 camadas de relevo) ────────────────────────────
        frame_btn_area = tk.Frame(parent, bg=CORPO)
        frame_btn_area.pack(fill="x", padx=8, pady=(12, 0))

        frame_sombra = tk.Frame(frame_btn_area, bg="#020602")
        frame_sombra.pack(fill="x", padx=2, pady=2)

        frame_moldura = tk.Frame(frame_sombra, bg="#082208", bd=10, relief="raised")
        frame_moldura.pack(fill="x", padx=1, pady=1)

        frame_int = tk.Frame(frame_moldura, bg=COR_BOTAO, bd=4, relief="raised")
        frame_int.pack(fill="x", padx=2, pady=2)

        self.btn_chamar = tk.Button(
            frame_int,
            text="CHAMAR PRÓXIMA SENHA",
            bg=COR_BOTAO, fg="#00ff7f",
            font=("Consolas", 12, "bold"),
            relief="flat", cursor="hand2", height=2,
            # Começa desabilitado: só é liberado quando _poll_queue recebe o
            # evento ("conexao", "ok"), garantindo que não se chame uma senha
            # antes de o socket estar de fato registrado no SRV.
            state="disabled",
            command=self._chamar,
            activebackground=COR_BTN_HI, activeforeground="white"
        )
        self.btn_chamar.pack(fill="x")

        # ── STATUS ─────────────────────────────────────────────────────────
        self.lbl_status = tk.Label(
            parent,
            text="Aguardando conexão com o servidor...",
            bg=CORPO, fg=COR_SUBTEX,
            font=("Consolas", 8)
        )
        self.lbl_status.pack(pady=(8, 2))

        # ── HISTÓRICO ─────────────────────────────────────────────────────
        frame_hist = tk.Frame(parent, bg=CORPO)
        frame_hist.pack(fill="both", expand=True, padx=8, pady=(4, 0))

        tk.Frame(frame_hist, bg="#0d2a0d", height=1).pack(fill="x")

        tk.Label(
            frame_hist, text="HISTÓRICO DE CHAMADAS",
            bg=CORPO, fg="#1e3a1e",
            font=("Consolas", 7, "bold")
        ).pack(anchor="w", pady=(3, 2))

        self.listbox = tk.Listbox(
            frame_hist,
            bg=DISPLAY_BG, fg="#1a5a1a",
            font=("Consolas", 9),
            selectbackground="#0d2a0d",
            relief="flat", bd=0, height=6,
            highlightthickness=0
        )
        self.listbox.pack(fill="both", expand=True, pady=(0, 6))

    # ── LED ───────────────────────────────────────────────────────────────────

    def _set_led(self, ok: bool):
        """Atualiza a cor dos LEDs de status (chassi e cabeçalho).

        Args:
            ok (bool): True pinta verde (conectado); False pinta verde-apagado
                (sem conexão).
        Returns:
            None
        """
        self._cvs.itemconfig(
            self._id_led,
            fill="#00bb44" if ok else "#003300",
            outline="#00ff66" if ok else "#005500"
        )
        self._cvs_led.itemconfig(
            self._id_led_btn,
            fill="#00bb44" if ok else "#003300",
            outline="#00ff66" if ok else "#005500"
        )

    # ── CICLO DE VIDA ─────────────────────────────────────────────────────────

    def _fechar(self):
        """Handler do botão fechar (WM_DELETE_WINDOW): encerra com segurança.

        Baixa a flag self._ativo para que a thread de rede saia de seus laços
        na próxima iteração, e então destrói a janela Tk.

        Returns:
            None
        """
        self._ativo = False
        self.root.destroy()

    def _conectar(self):
        """Inicia a thread de rede em modo daemon.

        Usa-se uma thread separada porque o ciclo connect/recv é bloqueante e
        travaria o laço de eventos do Tkinter. Como daemon, ela não impede o
        processo de terminar quando a janela é fechada.

        Returns:
            None
        """
        threading.Thread(target=self._loop_conexao, daemon=True).start()

    def _loop_conexao(self):
        """Mantém a conexão PERSISTENTE com o SRV e reconecta automaticamente.

        Executa em thread separada. O laço externo cuida da (re)conexão; o laço
        interno faz a leitura contínua do socket. Diferentemente do TS — que
        abre e fecha o socket a cada operação — aqui o socket permanece aberto
        durante toda a sessão, pois o atendente fará várias chamadas e o SRV
        empurra respostas pelo mesmo canal.

        Fluxo do protocolo:
            1. Conecta em (HOST, PORTA_SRV) com timeout de 5s só para o connect
               (evita travar indefinidamente se o SRV estiver fora do ar).
            2. Remove o timeout (settimeout(None)) para que o recv() seja
               bloqueante durante a operação normal.
            3. Registra o guichê: envia "TA_CONECTAR|<id_guiche>".
            4. Notifica a UI ("conexao", "ok") e entra no loop de recv().
            5. recv() retornando b"" indica que o SRV fechou a conexão -> sai
               do loop interno para tentar reconectar.

        Recuperação de falhas:
            Qualquer erro de socket é silenciado; em seguida publica-se
            ("reconectando",) e aguarda-se 3s (backoff fixo) antes de tentar de
            novo. O loop só termina quando self._ativo vira False (app fechando).

        Returns:
            None: comunica resultados exclusivamente via self._fila_ui.
        """
        import time
        while self._ativo:
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                # Timeout apenas na fase de conexão: se o SRV estiver offline,
                # falha rápido (5s) e cai no fluxo de reconexão.
                s.settimeout(5)
                s.connect((conexao.HOST, conexao.PORTA_SRV))
                # A partir daqui o recv deve bloquear normalmente (sem timeout).
                s.settimeout(None)
                # Handshake de registro: identifica este guichê para o SRV.
                # sendall garante o envio completo; '\n' delimita a mensagem.
                s.sendall(f"TA_CONECTAR|{self.id_guiche}\n".encode("utf-8"))
                self._socket = s
                self._fila_ui.put(("conexao", "ok"))

                # Loop de recepção: lê respostas do SRV até a conexão cair.
                # Acumula bytes em `buffer` e processa UMA linha por vez
                # (enquadramento '\n'), remontando/separando mensagens.
                buffer = ""
                while self._ativo:
                    dados = s.recv(1024)
                    if not dados:
                        # Peer encerrou a conexão (FIN): força reconexão.
                        break
                    buffer += dados.decode("utf-8")
                    while "\n" in buffer:
                        linha, buffer = buffer.split("\n", 1)
                        if linha:
                            self._fila_ui.put(("resposta", linha))

            except (ConnectionRefusedError, TimeoutError, OSError):
                # Falhas esperadas de rede (SRV fora, timeout, socket inválido).
                pass
            except Exception:
                # Salvaguarda: nenhuma exceção deve matar a thread de rede.
                pass
            finally:
                # Invalida o socket para que _chamar() saiba que está offline.
                self._socket = None

            if not self._ativo:
                break
            # Backoff fixo de 3s entre tentativas para não martelar o servidor.
            self._fila_ui.put(("reconectando",))
            time.sleep(3)

    def _chamar(self):
        """Solicita ao SRV a próxima senha (callback do botão CHAMAR).

        Envia "TA_SOLICITAR|<id_guiche>" pelo socket persistente. A resposta
        NÃO é lida aqui — ela chega de forma assíncrona pelo recv() em
        _loop_conexao e é tratada em _poll_queue.

        O botão é desabilitado IMEDIATAMENTE antes do envio para prevenir
        duplo clique: sem isso, o atendente poderia disparar dois
        "TA_SOLICITAR" em sequência e consumir/pular uma senha da fila sem
        querer. O botão só volta a "normal" quando a resposta correspondente é
        processada em _poll_queue.

        Returns:
            None: efeitos colaterais na UI e no socket; erros vão p/ a fila.
        """
        # Guarda: se a thread de rede invalidou o socket, não há o que enviar.
        if not self._socket:
            self.lbl_status.config(text="Sem conexão com o servidor.", fg="#e74c3c")
            return
        # Desabilita ANTES do envio -> trava anti-duplo-clique (ver docstring).
        self.btn_chamar.config(state="disabled")
        self.lbl_status.config(text="Solicitando próxima senha...", fg="#f39c12")
        try:
            # sendall garante o envio completo; '\n' delimita a mensagem.
            self._socket.sendall(f"TA_SOLICITAR|{self.id_guiche}\n".encode("utf-8"))
        except Exception as e:
            # Falha no send: reporta via fila (será tratado como evento "erro").
            self._fila_ui.put(("erro", f"Falha ao enviar: {e}"))

    # ── RELATÓRIO ─────────────────────────────────────────────────────────────

    def _abrir_relatorio(self):
        """Abre a janela de relatório dos atendimentos desta sessão/guichê.

        Monta o texto do relatório a partir de self._historico (delegando a
        formatação e as estatísticas ao módulo utils.relatorio), exibe-o em uma
        Toplevel somente-leitura e oferece botões para exportar em PDF ou TXT.

        Detalhes:
            - com_guiche=False: o relatório é de um único guichê, então a coluna
              de guichê é redundante; a identidade já vai no título/extras.
            - A geração de PDF é feita sob demanda (ao clicar em "Salvar PDF"),
              via relatorio.gerar_pdf, que retorna (ok, msg) p/ tratamento de erro.

        Returns:
            None: cria uma janela Tk Toplevel.
        """
        titulo = "RELATORIO DE ATENDIMENTOS - GUICHE {}".format(self.id_guiche)
        # extras: pares chave/valor exibidos no cabeçalho do relatório.
        # Identidade do guichê + estatísticas agregadas da sessão (totais,
        # tempos médios etc.) calculadas pelo módulo relatorio.
        extras = {"Guiche": self.id_guiche}
        extras.update(relatorio._stats_sessao(self._historico))
        texto  = relatorio.gerar_txt(titulo, self._historico, com_guiche=False, extras=extras)

        janela = tk.Toplevel(self.root)
        janela.title("Relatorio — Guiche {}".format(self.id_guiche))
        janela.geometry("640x480")
        janela.configure(bg=PAREDE)
        janela.resizable(True, True)

        frame_txt = tk.Frame(janela, bg=PAREDE)
        frame_txt.pack(fill="both", expand=True, padx=12, pady=(12, 0))

        sb = tk.Scrollbar(frame_txt, orient="vertical")
        sb.pack(side="right", fill="y")

        txt = tk.Text(
            frame_txt,
            bg=DISPLAY_BG, fg=COR_TEXTO,
            font=("Consolas", 10),
            relief="flat", bd=0, wrap="none",
            highlightthickness=0, padx=10, pady=10,
            yscrollcommand=sb.set,
        )
        txt.pack(side="left", fill="both", expand=True)
        sb.config(command=txt.yview)
        txt.insert("1.0", texto)
        txt.config(state="disabled")

        frame_btns = tk.Frame(janela, bg=PAREDE)
        frame_btns.pack(fill="x", padx=12, pady=10)

        def salvar_pdf():
            """Exporta o relatório atual para PDF via diálogo "salvar como"."""
            path = filedialog.asksaveasfilename(
                defaultextension=".pdf",
                filetypes=[("PDF", "*.pdf")],
                initialfile="relatorio_guiche{}_{}.pdf".format(
                    self.id_guiche, datetime.now().strftime("%Y%m%d_%H%M%S")),
                parent=janela,
            )
            if not path:
                return
            ok, msg = relatorio.gerar_pdf(
                path, titulo, self._historico, com_guiche=False, extras=extras)
            if ok:
                messagebox.showinfo("PDF salvo", "Arquivo salvo em:\n{}".format(path), parent=janela)
            else:
                messagebox.showerror("Erro ao gerar PDF", msg, parent=janela)

        def salvar_txt():
            """Salva o texto já renderizado do relatório em um arquivo .txt."""
            path = filedialog.asksaveasfilename(
                defaultextension=".txt",
                filetypes=[("Arquivo de texto", "*.txt")],
                initialfile="relatorio_guiche{}_{}.txt".format(
                    self.id_guiche, datetime.now().strftime("%Y%m%d_%H%M%S")),
                parent=janela,
            )
            if path:
                with open(path, "w", encoding="utf-8") as f:
                    f.write(texto)

        tk.Button(frame_btns, text="Salvar PDF",
                  bg="#c0392b", fg="white", font=("Segoe UI", 10, "bold"),
                  relief="flat", cursor="hand2", command=salvar_pdf,
                  padx=16, pady=6, activebackground="#922b21", activeforeground="white",
                  ).pack(side="left", padx=(0, 6))

        tk.Button(frame_btns, text="Salvar .txt",
                  bg="#2980b9", fg="white", font=("Segoe UI", 10),
                  relief="flat", cursor="hand2", command=salvar_txt,
                  padx=16, pady=6, activebackground="#1a5276", activeforeground="white",
                  ).pack(side="left", padx=(0, 6))

        tk.Button(frame_btns, text="Fechar",
                  bg="#7f8c8d", fg="white", font=("Segoe UI", 10),
                  relief="flat", cursor="hand2", command=janela.destroy,
                  padx=16, pady=6, activebackground="#626567", activeforeground="white",
                  ).pack(side="left")

    # ── POLL ──────────────────────────────────────────────────────────────────

    def _poll_queue(self):
        """Consome eventos da fila e atualiza a UI (padrão Queue + root.after).

        Tkinter não é thread-safe, então a thread de rede nunca mexe em widgets;
        ela apenas enfileira tuplas de evento em self._fila_ui. Este método roda
        SEMPRE na thread principal: drena a fila, aplica as mudanças visuais e se
        reagenda com root.after(100, ...) — um "polling" de 100 ms. É exatamente
        o mesmo mecanismo usado no TV (Terminal de Visualização).

        Tipos de evento tratados:
            ("conexao", "ok")   -> marca conectado e habilita o botão CHAMAR.
            ("reconectando",)    -> mostra estado de reconexão, desabilita botão.
            ("resposta", msg)    -> processa a senha vinda do SRV (ver abaixo).
            ("erro", msg)        -> exibe erro e desabilita o botão.

        Returns:
            None: reagenda a si mesmo indefinidamente enquanto a janela existir.
        """
        # Drena TODOS os eventos pendentes a cada ciclo (não só um), evitando
        # acúmulo/atraso quando várias mensagens chegam entre dois polls.
        while not self._fila_ui.empty():
            evento = self._fila_ui.get()
            tipo = evento[0]

            if tipo == "conexao":
                if evento[1] == "ok":
                    self.lbl_conexao.config(text="● Conectado", fg=COR_VERDE)
                    self.lbl_status.config(text="Pronto. Clique para chamar.", fg=COR_TEXTO)
                    self.btn_chamar.config(state="normal")
                    self._set_led(True)

            elif tipo == "reconectando":
                self.lbl_conexao.config(text="● Reconectando...", fg="#f39c12")
                self.lbl_status.config(text="Servidor indisponível. Tentando reconectar...", fg="#f39c12")
                self.btn_chamar.config(state="disabled")
                self._set_led(False)

            elif tipo == "resposta":
                msg = evento[1]
                # Resposta recebida: reabilita o botão (fecha o ciclo iniciado
                # pela trava anti-duplo-clique em _chamar).
                self.btn_chamar.config(state="normal")
                if "Fila vazia" in msg:
                    # Não há senha a chamar: mantém o display em "---".
                    self.lbl_senha.config(text="---", fg=COR_SUBTEX)
                    self.lbl_status.config(text=msg, fg="#e67e22")
                else:
                    # Parsing do protocolo de resposta do SRV.
                    # Formato esperado: "Guichê X chama: N1 — Nome Aqui"
                    # 1) descarta o prefixo até ": " para isolar "senha — nome";
                    parte_senha = msg.split(": ", 1)[-1] if ": " in msg else msg
                    # 2) separa senha e nome pelo travessão " — " (pode não vir).
                    if " — " in parte_senha:
                        senha, nome = parte_senha.split(" — ", 1)
                        senha = senha.strip()
                        nome  = nome.strip()
                    else:
                        senha = parte_senha.strip()
                        nome  = ""
                    # Atualiza o display grande e a linha de status.
                    self.lbl_senha.config(text=senha, fg="#2ecc71")
                    self.lbl_status.config(
                        text=f"{senha} — {nome}" if nome else senha,
                        fg=COR_TEXTO
                    )
                    # Registra no histórico visual (topo da lista) e no log de
                    # sessão usado pelo relatório. O tipo é inferido pelo prefixo
                    # da senha: "P..." = Prioritário, demais = Normal.
                    self.listbox.insert(0, msg)
                    self._contador_seq += 1
                    self._historico.append({
                        "ordem": self._contador_seq,
                        "senha": senha,
                        "nome":  nome,
                        "tipo":  "Prioritario" if senha.startswith("P") else "Normal",
                        "hora":  datetime.now(),
                    })

            elif tipo == "erro":
                self.lbl_conexao.config(text="● Erro", fg="#e74c3c")
                self.lbl_status.config(text=evento[1], fg="#e74c3c")
                self.btn_chamar.config(state="disabled")
                self._set_led(False)

        # Reagenda o próximo ciclo de polling (100 ms) na thread da UI.
        self.root.after(100, self._poll_queue)


# ── PONTO DE ENTRADA ────────────────────────────────────────────────────────
# Instancia a aplicação quando o arquivo é executado diretamente
# (ex.: `python3 clientes/ta.py` ou `python3 clientes/ta.py --guiche=2`).
# O construtor chama mainloop(), então esta linha bloqueia até a janela fechar.
if __name__ == "__main__":
    AppTerminalAtendimento()
