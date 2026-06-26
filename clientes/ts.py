# =============================================================================
# VERSÃO ORIGINAL (CLI) — antes da interface gráfica
# =============================================================================
#
# import socket, sys, os
# sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
# from utils import conexao
#
# def iniciar_ts():
#     print("--- TERMINAL DE SENHAS (TS) INICIADO ---")
#     print("Digite 'N' para Normal, 'P' para Prioritária ou 'S' para Sair.")
#     while True:
#         escolha = input("\nGerar qual senha? ").strip().upper()
#         if escolha == 'S': break
#         elif escolha not in ['N', 'P']:
#             print("Opção inválida! Use N ou P."); continue
#         cliente_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
#         try:
#             cliente_socket.connect((conexao.HOST, conexao.PORTA_SRV))
#             cliente_socket.send(f"TS|GERAR_{escolha}".encode('utf-8'))
#             print(f"Resposta: {cliente_socket.recv(1024).decode('utf-8')}")
#         except ConnectionRefusedError:
#             print("Erro: Servidor offline.")
#         finally:
#             cliente_socket.close()
#
# if __name__ == "__main__":
#     iniciar_ts()
#
# =============================================================================
# VERSÃO ATUAL — GUI com chassi físico desenhado em Canvas (totem kiosk)
# =============================================================================

"""ts.py — Terminal de Senhas (TS) do sistema SASE.

PROPÓSITO
    Cliente de autoatendimento (estilo totem/kiosk) usado pelo PÚBLICO para
    emitir senhas de atendimento. O usuário pressiona um de dois botões físicos
    desenhados na tela — N (Normal) ou P (Prioritária) — e o terminal solicita
    ao servidor central (SRV) a geração de uma nova senha, exibindo-a num
    display estilizado como um LCD de equipamento real.

    A interface NÃO é uma janela comum: o chassi inteiro da máquina (corpo
    cinza, parafusos Phillips, slots de ventilação, knobs, botão power, LED de
    status e placa institucional) é DESENHADO à mão num tkinter.Canvas, dando
    a aparência de um equipamento físico de balcão.

O QUE FAZ / COMO SE USA
    - N = Senha Normal (público geral).
    - P = Senha Prioritária (idosos, gestantes, PCDs — atendimento preferencial,
      conforme legislação de prioridade).
    - Cada toque dispara UMA requisição de rede; a senha retornada aparece no
      display e o LED de status pisca verde em caso de sucesso.

PROTOCOLO DE COMUNICAÇÃO (rede)
    Transporte : TCP/IP (socket AF_INET / SOCK_STREAM).
    Endereço   : conexao.HOST : conexao.PORTA_SRV (definidos em utils/conexao.py).
    Padrão     : CONEXÃO CURTA (short-lived) — abre o socket, envia UMA mensagem,
                 lê UMA resposta e fecha imediatamente. Diferente do TA (Terminal
                 de Atendimento), que mantém conexão persistente, o TS não guarda
                 estado entre requisições: "uma requisição = uma senha = fecha".
    Mensagem   : texto UTF-8 no formato  "TS|GERAR_<TIPO>"  (ex.: "TS|GERAR_N").
                 O prefixo "TS|" identifica a origem para o servidor multiplexar
                 os diferentes tipos de cliente sobre a mesma porta.
    Enquadramento : TCP é um fluxo de bytes sem fronteira de mensagem; por isso
                 toda mensagem termina com '\n'. O TS envia "TS|GERAR_<TIPO>\n" e,
                 ao ler a resposta, acumula bytes até encontrar o '\n' que marca
                 o fim da mensagem (remonta respostas fragmentadas).
    Resposta   : texto livre tipo "Senha gerada: N1 — Nome Aqui", do qual o
                 terminal extrai apenas o código da senha para o display.

ARQUITETURA DE CONCORRÊNCIA (GUI x rede)
    O tkinter é single-thread: qualquer chamada de socket bloqueante feita no
    mainloop congelaria a interface. Por isso a I/O de rede roda numa thread
    separada (daemon) e devolve o resultado à thread da UI por uma fila
    thread-safe (queue.Queue), drenada periodicamente via root.after()
    (padrão producer/consumer + polling). Ver _gerar/_requisitar/_poll_queue.

Disciplina: Sistemas Distribuídos — IFCE Campus Crato.
"""

import tkinter as tk      # toolkit gráfico nativo (sem dependências externas)
import socket             # API de sockets TCP para falar com o SRV
import threading          # thread daemon p/ não bloquear o mainloop do tkinter
import queue              # fila thread-safe: ponte thread-de-rede -> thread-de-UI
import sys
import os

# Garante que o pacote-raiz do projeto esteja no sys.path mesmo quando o TS é
# executado diretamente de dentro de clientes/. Permite importar utils/ que fica
# um nível acima deste arquivo.
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from utils import conexao, audio  # conexao: HOST/PORTA do SRV; audio: efeitos sonoros

# ── PALETA DE CORES ───────────────────────────────────────────────────────────
# Constantes hexadecimais centralizadas para garantir consistência visual e
# permitir "retematizar" o totem alterando um único ponto. As escolhas seguem
# uma lógica física: tons cinza-neutros para o metal do chassi e cores vivas
# (neon) apenas nos elementos "iluminados" (display e botões), reforçando a
# ilusão de um equipamento real com luz própria.
PAREDE     = "#0a0a0a"    # fundo externo (parede/balcão) — quase preto, faz o chassi "saltar"
CORPO      = "#525252"    # chassi cinza médio — tom neutro que contrasta com displays escuros
CORPO_DARK = "#2e2e2e"    # sombra do chassi (faces voltadas para longe da luz)
CORPO_HI   = "#787878"    # highlight do chassi (bevel superior-esquerdo, lado iluminado)
DISPLAY_BG = "#040b14"    # fundo do display LCD — azul quase preto, simula vidro apagado
DISPLAY_BD = "#0a1828"    # borda do display
BTN_N_BG   = "#0d3a1a"    # verde MUITO escuro — corpo do botão Normal (apagado/repouso)
BTN_N_TXT  = "#00ff7f"    # verde brilhante — letra "N" acesa (associa Normal ao verde "siga")
BTN_N_HI   = "#1a7038"    # verde de realce ao pressionar/hover do botão Normal
BTN_P_BG   = "#4a1800"    # laranja-escuro — corpo do botão Prioritária (apagado/repouso)
BTN_P_TXT  = "#ff9f33"    # laranja brilhante — letra "P" acesa (laranja = atenção/preferencial)
BTN_P_HI   = "#7a2a00"    # laranja de realce ao pressionar/hover do botão Prioritária
DIGIT_N    = "#00e5ff"    # ciano — cor da senha Normal exibida no display
DIGIT_P    = "#ff9f33"    # laranja — cor da senha Prioritária exibida no display
DIGIT_OFF  = "#050e18"    # dígito "apagado" — quase invisível sobre o fundo, simula LCD sem sinal
BADGE_BG   = "#080c1a"    # fundo da placa institucional (azul-escuro tipo crachá oficial)
STATUS_FG  = "#5a5a5a"    # cinza discreto — texto de status em repouso (instruções neutras)


class AppTerminalSenhas:
    """Aplicação-totem do Terminal de Senhas (TS).

    Responsabilidade
        Encapsular toda a janela do TS: a montagem da interface (chassi
        desenhado + widgets), a captura dos toques nos botões N/P e a
        comunicação de rede com o servidor SRV para obtenção de senhas.

    Papel na arquitetura distribuída
        É um dos clientes "folha" do sistema SASE. Não conversa com outros
        clientes diretamente — toda coordenação passa pelo SRV central. Atua
        apenas como PRODUTOR de senhas (gera demanda); a chamada e o
        atendimento ocorrem nos terminais TV (painel) e TA (atendente).

    Padrões de projeto
        - Producer/Consumer com fila: a thread de rede (produtor) deposita
          resultados em self._fila_ui e a thread da UI (consumidor) os lê.
        - Event-loop polling: _poll_queue se reagenda via root.after() para
          consumir a fila sem travar o mainloop do tkinter.
    """

    def __init__(self):
        # ── Janela principal ────────────────────────────────────────────────
        self.root = tk.Tk()
        self.root.title("SASE — Terminal de Senhas (TS)")
        self.root.geometry("420x680")           # proporção alta/estreita imita um totem
        self.root.configure(bg=PAREDE)
        self.root.resizable(False, False)       # layout em Canvas é desenhado em px fixos: travar evita distorção

        # Fila thread-safe que liga a thread de rede à thread da UI (ver classe).
        self._fila_ui = queue.Queue()

        self._build_ui()      # monta chassi + widgets
        self._poll_queue()    # inicia o consumidor periódico da fila
        self.root.mainloop()  # entra no loop de eventos (bloqueia até fechar a janela)

    # ── CORPO DA MÁQUINA (desenhado no Canvas) ────────────────────────────────

    def _build_ui(self):
        """Monta a interface em duas camadas sobrepostas.

        Camada de fundo: um Canvas do tamanho da janela onde o chassi físico é
        desenhado (_desenhar_corpo). Camada da frente: um Frame com os widgets
        interativos (display, botões, status) posicionado por cima via place().
        Usar place() com coordenadas absolutas é o que permite encaixar os
        widgets exatamente sobre o desenho do chassi.
        """
        W, H = 420, 680  # dimensões fixas (devem casar com geometry() da janela)

        # Canvas cobre a janela inteira e serve de "parede" + corpo da máquina.
        # highlightthickness=0 remove a borda de foco padrão do tkinter, que
        # quebraria a ilusão de superfície contínua.
        self._cvs = tk.Canvas(
            self.root, bg=PAREDE, width=W, height=H,
            highlightthickness=0
        )
        self._cvs.place(x=0, y=0, width=W, height=H)

        self._desenhar_corpo(W, H)  # pinta chassi, parafusos, ventilação etc.

        # Frame de conteúdo posicionado SOBRE o Canvas. As coordenadas (22, 64)
        # e o tamanho deixam livres as faixas do chassi (marca no topo, slots de
        # ventilação embaixo) desenhadas no Canvas.
        fc = tk.Frame(self.root, bg=CORPO)
        fc.place(x=22, y=64, width=W - 44, height=546)
        self._build_content(fc)

    def _desenhar_corpo(self, W, H):
        """Desenha o chassi físico do totem inteiramente com primitivas do Canvas.

        Técnica geral
            tkinter.Canvas não tem "estilo 3D" nativo; o relevo é simulado à mão
            com a regra clássica de iluminação: linhas CLARAS nas bordas
            voltadas para a luz (topo/esquerda) e ESCURAS nas opostas
            (baixo/direita). Isso cria o efeito de bevel (bisel) que faz o painel
            parecer ter profundidade.

        Args:
            W (int): largura útil do Canvas em pixels.
            H (int): altura útil do Canvas em pixels.
        """
        c = self._cvs  # alias local p/ encurtar as muitas chamadas create_*

        # Sombra projetada: retângulo escuro levemente deslocado p/ baixo-direita,
        # desenhado ANTES do corpo para ficar "atrás" e dar sensação de elevação.
        c.create_rectangle(20, 20, W - 12, H - 12, fill="#050505", outline="")

        # Corpo principal (chassi cinza) — a "chapa" frontal do equipamento.
        c.create_rectangle(14, 14, W - 14, H - 14,
                            fill=CORPO, outline="#1e1e1e", width=3)

        # Bevel iluminado: 4 linhas concêntricas no topo + esquerda, em tons
        # claros, simulando a luz incidindo de cima-esquerda (canto chanfrado).
        for i in range(4):
            clr = "#787878" if i < 2 else "#686868"  # degradê: mais claro na borda externa
            c.create_line(17 + i, 17 + i, W - 17 - i, 17 + i, fill=clr, width=1)  # aresta superior
            c.create_line(17 + i, 17 + i, 17 + i, H - 17 - i, fill=clr, width=1)  # aresta esquerda

        # Bevel sombreado: mesmas 4 linhas, mas embaixo + direita em tons escuros,
        # completando a ilusão de relevo (faces afastadas da luz).
        for i in range(4):
            clr = "#1a1a1a" if i < 2 else "#2a2a2a"
            c.create_line(17 + i, H - 17 - i, W - 17 - i, H - 17 - i, fill=clr, width=1)  # aresta inferior
            c.create_line(W - 17 - i, 17 + i, W - 17 - i, H - 17 - i, fill=clr, width=1)  # aresta direita

        # Parafusos Phillips nos quatro cantos. Cada parafuso é composto por:
        #   1) disco externo cinza (cabeça metálica),
        #   2) disco interno escuro (recesso/sombra central),
        #   3) duas linhas cruzadas em "+" (a fenda Phillips).
        for sx, sy in [(32, 32), (W - 32, 32), (32, H - 32), (W - 32, H - 32)]:
            r = 9
            c.create_oval(sx - r, sy - r, sx + r, sy + r,
                           fill="#404040", outline="#707070", width=1)  # cabeça
            c.create_oval(sx - 4, sy - 4, sx + 4, sy + 4,
                           fill="#1a1a1a", outline="")                  # recesso
            c.create_line(sx - 6, sy, sx + 6, sy, fill="#707070", width=1)  # fenda horizontal
            c.create_line(sx, sy - 6, sx, sy + 6, fill="#707070", width=1)  # fenda vertical (forma o "+")

        # Faixa de marca (topo do chassi) — barra horizontal mais clara que
        # serve de "etiqueta serigrafada" com a identificação do equipamento.
        c.create_rectangle(18, 18, W - 18, 60, fill="#3a3a3a", outline="")
        c.create_text(W // 2 - 16, 39,
                      text="INSTITUTO FEDERAL  ·  CAMPUS CRATO  ·  SASE  ·  TS-2026",
                      fill="#5a5a5a", font=("Consolas", 7, "bold"), anchor="center")

        # LED de status na faixa de marca. Guardamos o ID do item (item handle)
        # em self._id_led porque ele será reconfigurado em tempo real por
        # _set_led() (verde quando uma senha é emitida com sucesso).
        self._id_led = c.create_oval(W - 52, 29, W - 38, 43,
                                      fill="#003300", outline="#005500", width=1)
        # LED vermelho decorativo (sempre "aceso", apenas estético) ao lado.
        c.create_oval(W - 68, 29, W - 54, 43, fill="#440000", outline="#660000", width=1)

        # Linha separadora abaixo da faixa de marca
        c.create_line(18, 62, W - 18, 62, fill="#3a3a3a", width=2)

        # Slots de ventilação (parte inferior do chassi): 6 ranhuras horizontais
        # espaçadas de 8px, simulando as grelhas de refrigeração de um gabinete.
        for i in range(6):
            y0 = H - 62 + i * 8
            c.create_rectangle(60, y0, W - 60, y0 + 5,
                                fill="#3e3e3e", outline="#2a2a2a", width=1)

        # Linha separadora acima dos slots
        c.create_line(18, H - 70, W - 18, H - 70, fill="#3a3a3a", width=2)

        # Etiqueta inferior
        c.create_text(W // 2, H - 18,
                      text="[ SASE — TERMINAL DE SENHAS — TS ]",
                      fill="#404040", font=("Consolas", 7, "bold"), anchor="center")

        # Knobs decorativos (barra inferior): dois "potenciômetros" — disco com
        # um traço indicando a posição do giro. Puramente estéticos.
        for kx in (34, 58):
            c.create_oval(kx - 9, H - 46, kx + 9, H - 28,
                           fill="#3a3a3a", outline="#606060", width=2)
            c.create_line(kx, H - 42, kx, H - 30, fill="#606060", width=2)  # traço indicador

        # Botão power decorativo (canto inferior direito): círculo + arco aberto
        # + traço vertical, formando o símbolo IEC universal de liga/desliga.
        c.create_oval(W - 50, H - 48, W - 30, H - 28,
                       fill="#2a2a2a", outline="#4a4a4a", width=2)
        c.create_arc(W - 47, H - 45, W - 33, H - 31,
                      start=50, extent=260, style="arc", outline="#5a5a5a", width=2)  # anel do símbolo
        c.create_line(W - 40, H - 45, W - 40, H - 37, fill="#5a5a5a", width=2)        # haste do símbolo

    # ── CONTEÚDO (Frame sobre o Canvas) ───────────────────────────────────────

    def _build_content(self, parent):
        """Cria os widgets interativos sobre o chassi.

        Layout (de cima p/ baixo): placa institucional, display LCD da última
        senha, par de botões físicos N/P, rótulos, linha de status e o slot de
        retirada do ticket. O encadeamento de Frames com relief="raised"/"sunken"
        é o truque usado para dar volume 3D aos botões e molduras.

        Args:
            parent (tk.Frame): contêiner já posicionado sobre o Canvas onde
                todos estes widgets são empacotados (pack).
        """
        # ── PLACA INSTITUCIONAL ────────────────────────────────────────────
        # Moldura externa "afundada" (sunken) + interna escura = placa de metal
        # gravada, no estilo de uma identificação oficial parafusada no painel.
        frame_placa_outer = tk.Frame(parent, bg="#3a3a3a", bd=3, relief="sunken")
        frame_placa_outer.pack(fill="x", padx=8, pady=(8, 0))

        frame_placa = tk.Frame(frame_placa_outer, bg=BADGE_BG)
        frame_placa.pack(fill="x", padx=2, pady=2)

        tk.Label(
            frame_placa,
            text="INSTITUTO FEDERAL DE EDUCAÇÃO, CIÊNCIA E TECNOLOGIA",
            bg=BADGE_BG, fg="#1e3a6a",
            font=("Segoe UI", 7, "bold")
        ).pack(pady=(10, 0))

        tk.Label(
            frame_placa,
            text="CAMPUS CRATO  —  BACHARELADO EM SISTEMAS DE INFORMAÇÃO",
            bg=BADGE_BG, fg="#152a50",
            font=("Segoe UI", 7)
        ).pack()

        tk.Frame(frame_placa, bg="#1a3060", height=1).pack(fill="x", padx=28, pady=6)

        tk.Label(
            frame_placa, text="S  A  S  E",
            bg=BADGE_BG, fg="#3a5a9a",
            font=("Consolas", 22, "bold")
        ).pack()

        tk.Label(
            frame_placa, text="TERMINAL DE SENHAS",
            bg=BADGE_BG, fg="#1e3a6a",
            font=("Segoe UI", 9, "bold")
        ).pack(pady=(0, 10))

        # ── DISPLAY LCD ────────────────────────────────────────────────────
        # Moldura grossa afundada (bd=5, sunken) sobre fundo quase preto cria a
        # aparência de um visor de LCD encaixado no painel.
        frame_bd = tk.Frame(parent, bg="#1e1e1e", bd=5, relief="sunken")
        frame_bd.pack(fill="x", padx=8, pady=(10, 0))

        frame_display = tk.Frame(frame_bd, bg=DISPLAY_BG)
        frame_display.pack(fill="x", padx=3, pady=3)

        tk.Label(
            frame_display, text="ÚLTIMA SENHA GERADA",
            bg=DISPLAY_BG, fg=DIGIT_OFF,
            font=("Consolas", 8, "bold")
        ).pack(pady=(8, 0))

        # Label gigante que mostra o código da senha. Começa com "- - -" na cor
        # DIGIT_OFF (visor apagado). _poll_queue() atualiza o texto e troca a cor
        # para DIGIT_N/DIGIT_P ao receber a resposta do servidor.
        self.lbl_senha = tk.Label(
            frame_display, text="- - -",
            bg=DISPLAY_BG, fg=DIGIT_OFF,
            font=("Consolas", 64, "bold")
        )
        self.lbl_senha.pack(pady=(0, 8))

        # ── BOTÕES FÍSICOS (N e P) ─────────────────────────────────────────
        frame_btns = tk.Frame(parent, bg=CORPO)
        frame_btns.pack(fill="x", padx=8, pady=(12, 0))

        # Botão N — Normal. A profundidade de "tecla saliente" é obtida
        # aninhando 3 Frames: sombra projetada (fundo escuro) -> bisel externo
        # (raised, bd=10) -> bisel interno (raised, bd=4) -> Button no centro.
        frame_n_sombra = tk.Frame(frame_btns, bg="#040d08")
        frame_n_sombra.pack(side="left", expand=True, fill="both", padx=(0, 8))

        frame_n_ext = tk.Frame(frame_n_sombra, bg=BTN_N_BG, bd=10, relief="raised")
        frame_n_ext.pack(fill="both", padx=2, pady=2)

        frame_n_int = tk.Frame(frame_n_ext, bg=BTN_N_BG, bd=4, relief="raised")
        frame_n_int.pack(fill="both", padx=3, pady=3)

        # command=lambda: usa lambda para passar o argumento "N" sem invocar
        # _gerar imediatamente (callback de clique do tkinter recebe função, não
        # resultado). O mesmo padrão vale para o botão P.
        self.btn_n = tk.Button(
            frame_n_int, text="N",
            bg=BTN_N_BG, fg=BTN_N_TXT,
            font=("Consolas", 62, "bold"),
            relief="flat", cursor="hand2", bd=0,
            activebackground=BTN_N_HI, activeforeground="white",
            command=lambda: self._gerar("N")
        )
        self.btn_n.pack(fill="both", expand=True, ipady=8)

        # Botão P — Prioritária (mesma construção em 3 camadas, cores laranja).
        frame_p_sombra = tk.Frame(frame_btns, bg="#180800")
        frame_p_sombra.pack(side="left", expand=True, fill="both")

        frame_p_ext = tk.Frame(frame_p_sombra, bg=BTN_P_BG, bd=10, relief="raised")
        frame_p_ext.pack(fill="both", padx=2, pady=2)

        frame_p_int = tk.Frame(frame_p_ext, bg=BTN_P_BG, bd=4, relief="raised")
        frame_p_int.pack(fill="both", padx=3, pady=3)

        self.btn_p = tk.Button(
            frame_p_int, text="P",
            bg=BTN_P_BG, fg=BTN_P_TXT,
            font=("Consolas", 62, "bold"),
            relief="flat", cursor="hand2", bd=0,
            activebackground=BTN_P_HI, activeforeground="white",
            command=lambda: self._gerar("P")
        )
        self.btn_p.pack(fill="both", expand=True, ipady=8)

        # Labels dos botões
        frame_lbl = tk.Frame(parent, bg=CORPO)
        frame_lbl.pack(fill="x", padx=8, pady=(6, 0))

        tk.Label(
            frame_lbl, text="NORMAL",
            bg=CORPO, fg=BTN_N_TXT,
            font=("Consolas", 9, "bold")
        ).pack(side="left", expand=True)

        tk.Label(
            frame_lbl, text="PRIORITÁRIA",
            bg=CORPO, fg=BTN_P_TXT,
            font=("Consolas", 9, "bold")
        ).pack(side="left", expand=True)

        # ── STATUS ─────────────────────────────────────────────────────────
        # Linha de feedback ao usuário. Seu texto/cor é alterado dinamicamente:
        # instrução neutra em repouso, amarelo ao conectar, branco em sucesso e
        # vermelho em erro (ver _gerar e _poll_queue).
        self.lbl_status = tk.Label(
            parent,
            text="Pressione  N  para Normal  ·  P  para Prioritária",
            bg=CORPO, fg=STATUS_FG,
            font=("Segoe UI", 8), wraplength=360  # wraplength quebra textos de erro longos
        )
        self.lbl_status.pack(pady=(8, 0))

        # ── SLOT DE TICKET ─────────────────────────────────────────────────
        # Representação da fenda de saída do papel (estético): moldura afundada
        # + um pequeno Canvas com listras horizontais que imitam a abertura.
        frame_slot_outer = tk.Frame(parent, bg="#2a2a2a", bd=3, relief="sunken")
        frame_slot_outer.pack(fill="x", padx=8, pady=(10, 8))

        tk.Label(
            frame_slot_outer,
            text="◂  RETIRE SUA SENHA AQUI  ▸",
            bg="#2a2a2a", fg="#404040",
            font=("Consolas", 7, "bold")
        ).pack(pady=(4, 2))

        cvs_slot = tk.Canvas(
            frame_slot_outer, bg="#0a0a0a", height=22,
            highlightbackground="#1e1e1e", highlightthickness=1
        )
        cvs_slot.pack(fill="x", padx=6, pady=(0, 6))

        def _draw_slot(evt=None):
            """Redesenha as listras da fenda ajustando-as à largura atual.

            Como a largura do Canvas só é conhecida após o tkinter calcular o
            layout, as linhas são desenhadas em função de winfo_width(). Apagar
            antes (delete por tag) evita acúmulo de linhas a cada redesenho.

            Args:
                evt: evento <Configure> (ignorado); o handler também é chamado
                    manualmente via after(), por isso o parâmetro é opcional.
            """
            cvs_slot.delete("slot_lines")
            # winfo_width() retorna 1 antes do 1º layout; o "or 340" dá um
            # fallback razoável para o primeiro desenho.
            w = cvs_slot.winfo_width() or 340
            for y in (7, 11, 15):
                cvs_slot.create_line(12, y, w - 12, y,
                                      fill="#1e1e1e", width=1, tags="slot_lines")
            cvs_slot.create_line(12, 11, w - 12, 11,
                                  fill="#2a2a2a", width=2, tags="slot_lines")  # linha central mais grossa (a fenda)

        # <Configure> dispara sempre que o Canvas muda de tamanho (ex.: janela
        # redimensionada), mantendo as listras sempre na largura correta.
        cvs_slot.bind("<Configure>", _draw_slot)
        # Desenho inicial agendado: garante que ocorra após o tkinter ter
        # calculado as dimensões reais do widget.
        self.root.after(50, _draw_slot)

    # ── LED ───────────────────────────────────────────────────────────────────

    def _set_led(self, ok: bool):
        """Atualiza o LED de status no chassi via itemconfig do Canvas.

        Args:
            ok (bool): True acende o LED em verde (operação bem-sucedida);
                False o deixa verde-escuro/apagado (repouso ou erro).
        """
        self._cvs.itemconfig(
            self._id_led,
            fill="#00bb44" if ok else "#003300",
            outline="#00ff66" if ok else "#005500"
        )

    # ── LÓGICA ────────────────────────────────────────────────────────────────

    def _gerar(self, tipo):
        """Handler de clique dos botões N/P — dispara a emissão de uma senha.

        Roda na thread da UI. Para não congelar o mainloop do tkinter enquanto a
        rede responde, ele apenas prepara a interface (desabilita botões, avisa
        "conectando", apaga o LED) e DELEGA a I/O bloqueante a uma thread
        separada. Os botões ficam desabilitados para impedir cliques duplos
        gerando senhas indevidas em paralelo; são reabilitados em _poll_queue
        quando o resultado chega.

        Args:
            tipo (str): "N" para senha Normal ou "P" para Prioritária. Esse
                valor entra na mensagem de protocolo "TS|GERAR_<tipo>".
        """
        self.btn_n.config(state="disabled")
        self.btn_p.config(state="disabled")
        self.lbl_status.config(text="Conectando ao servidor...", fg="#f39c12")
        self._set_led(False)
        # daemon=True: a thread morre junto com o programa se a janela for
        # fechada durante uma requisição, evitando travar o encerramento.
        threading.Thread(target=self._requisitar, args=(tipo,), daemon=True).start()

    def _requisitar(self, tipo):
        """Executa a requisição de rede ao SRV (roda em thread separada).

        Implementa o padrão de CONEXÃO TCP CURTA (short-lived): abre o socket,
        envia exatamente uma mensagem, lê uma resposta e fecha. O TS, ao
        contrário do TA (que mantém uma conexão persistente para receber
        múltiplos eventos de atendimento), é stateless: cada toque é uma
        transação independente — "uma requisição = uma senha = fecha" — então
        não há motivo para manter o socket aberto.

        NÃO toca em widgets diretamente (tkinter não é thread-safe): o resultado
        é entregue à thread da UI publicando uma tupla na fila self._fila_ui,
        consumida por _poll_queue.

        Protocolo
            Envia "TS|GERAR_<tipo>" em UTF-8 e lê até 1024 bytes de resposta.

        Args:
            tipo (str): "N" ou "P", repassado de _gerar.

        Raises:
            (capturadas internamente) ConnectionRefusedError quando o SRV está
            offline; demais exceções são empacotadas como evento de erro na
            fila. O método nunca propaga exceção para a thread.
        """
        try:
            # AF_INET + SOCK_STREAM = IPv4 + TCP (entrega confiável e ordenada).
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.connect((conexao.HOST, conexao.PORTA_SRV))
            # sendall garante o envio completo; '\n' delimita a mensagem.
            s.sendall(f"TS|GERAR_{tipo}\n".encode("utf-8"))
            # Enquadramento '\n': acumula bytes até a mensagem completa chegar
            # (a resposta pode vir fragmentada em mais de um segmento TCP).
            buffer = ""
            while "\n" not in buffer:
                dados = s.recv(1024)
                if not dados:
                    break  # SRV fechou a conexão sem terminar a mensagem
                buffer += dados.decode("utf-8")
            resposta = buffer.split("\n", 1)[0]
            s.close()  # fecha imediatamente: conexão curta concluída
            # Resultado para a thread da UI: (tag, payload, tipo) p/ escolher a cor.
            self._fila_ui.put(("ok", resposta, tipo))
        except ConnectionRefusedError:
            # Caso mais comum em sala: o servidor SRV não foi iniciado.
            self._fila_ui.put(("erro", "Servidor offline. Inicie o SRV primeiro."))
        except Exception as e:
            # Rede de segurança para qualquer outra falha (timeout, decode etc.).
            self._fila_ui.put(("erro", f"Erro: {e}"))

    def _poll_queue(self):
        """Consumidor periódico da fila — ponte segura rede -> interface.

        Padrão Queue + root.after: como só a thread da UI pode mexer em widgets
        do tkinter, este método (que roda nessa thread) drena tudo que a thread
        de rede depositou em self._fila_ui e aplica as mudanças visuais. Ao
        final, reagenda a si mesmo com after(100, ...), criando um loop de
        polling de 100ms que coexiste com o mainloop sem bloqueá-lo.

        Para cada evento:
            ("ok", resposta, tipo) -> extrai o código da senha, exibe no display
                com a cor do tipo, mostra a resposta no status e acende o LED.
            ("erro", mensagem)     -> mostra a mensagem em vermelho e apaga o LED.
        Em ambos os casos os botões N/P voltam a ficar habilitados.
        """
        # Drena toda a fila de uma vez (pode haver mais de um evento acumulado).
        while not self._fila_ui.empty():
            evento = self._fila_ui.get()
            # Requisição concluída: reabilita os botões travados em _gerar.
            self.btn_n.config(state="normal")
            self.btn_p.config(state="normal")

            if evento[0] == "ok":
                _, resposta, tipo = evento
                # A resposta do SRV vem como texto livre, ex.: "Senha gerada: N1 — Nome".
                # 1) descarta o rótulo antes de ": " (se houver) -> "N1 — Nome".
                parte = resposta.split(": ", 1)[-1] if ": " in resposta else resposta
                # 2) fica só com o código antes de " — " -> "N1" para o display.
                senha = parte.split(" — ")[0].strip() if " — " in parte else parte.strip()
                cor = DIGIT_N if tipo == "N" else DIGIT_P  # ciano p/ Normal, laranja p/ Prioritária
                self.lbl_senha.config(text=senha, fg=cor)
                self.lbl_status.config(text=resposta, fg="#ecf0f1")
                self._set_led(True)
            else:
                # evento[1] = mensagem de erro montada em _requisitar.
                self.lbl_status.config(text=evento[1], fg="#e74c3c")
                self._set_led(False)

        # Reagenda o próximo polling; 100ms é responsivo ao usuário e barato em CPU.
        self.root.after(100, self._poll_queue)


if __name__ == "__main__":
    # Ponto de entrada: instanciar a classe já dispara o mainloop (ver __init__),
    # então esta única linha sobe o totem quando o arquivo é executado direto.
    AppTerminalSenhas()
