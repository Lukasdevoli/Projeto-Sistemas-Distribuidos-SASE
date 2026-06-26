"""tv.py — Terminal de Visualização (TV) do sistema SASE.

PROPÓSITO
=========
Este módulo implementa o "TV" (Terminal de Visualização): a tela pública do
SASE (Sistema de Atendimento por Senha Eletrônica), equivalente ao painel de
um aeroporto/banco. Ele NÃO emite nem chama senhas — é apenas um cliente
passivo que escuta o servidor e exibe, em fonte gigante, a última senha
chamada, o guichê de destino e o nome do paciente, além de reproduzir o áudio
da chamada.

O QUE FAZ
=========
1. Conecta ao SRV (servidor central) em um laço persistente, reconectando
   automaticamente caso a conexão caia (servidor reiniciado, rede instável).
2. Recebe os broadcasts de chamada enviados pelo servidor e os exibe na tela.
3. Roda um efeito cosmético de "glitch" de TV defeituosa (apagões, flicker,
   cores trocadas) que é puramente visual e não afeta a lógica.
4. Toca o áudio da chamada via utils.audio (pyttsx3/espeak ou som pré-gravado).
5. Usa queue.Queue como ponte THREAD-SAFE entre a thread de rede (socket) e a
   thread principal do tkinter (única autorizada a tocar widgets).

COMO USAR
=========
    $ python3 clientes/tv.py
Basta executar; a janela abre, conecta sozinha ao SRV e fica em loop até ser
fechada. Vários TVs podem rodar simultaneamente — todos recebem o mesmo
broadcast.

PROTOCOLO DE COMUNICAÇÃO
========================
- Transporte: TCP/IP (socket SOCK_STREAM), host/porta definidos em
  utils.conexao (HOST=127.0.0.1, PORTA_SRV=5000).
- Handshake: ao conectar, o TV envia a string "TV|CONECTAR" (codificada em
  UTF-8). É assim que o servidor identifica este cliente como um painel de
  visualização e passa a incluí-lo na lista de destinatários do broadcast.
- Mensagens recebidas: texto UTF-8 no formato
      "Guichê X chama: N1 — Nome do Paciente"
  de onde extraímos guichê, senha e nome.
- Enquadramento ('\n'): como TCP é um fluxo de bytes sem fronteira de mensagem,
  toda mensagem termina com '\n'. O TV acumula os bytes em um buffer e processa
  uma linha por vez, evitando que dois broadcasts coalescidos sejam exibidos
  concatenados (ou que uma mensagem fragmentada seja exibida pela metade).

PADRÃO ARQUITETURAL
===================
Produtor/Consumidor com fila intermediária: a thread de rede é a PRODUTORA
(coloca eventos na fila) e o mainloop do tkinter é o CONSUMIDOR (drena a fila
periodicamente via root.after). Isso isola o I/O bloqueante de rede da GUI.

Disciplina: Sistemas Distribuídos — IFCE Campus Crato.
"""

# =============================================================================
# VERSÃO ORIGINAL (CLI) — antes da interface gráfica
# =============================================================================
# (ver histórico git para a versão CLI)
# =============================================================================
# VERSÃO ATUAL — GUI com chassi realista, bisel, controles e efeito glitch
# =============================================================================

import tkinter as tk      # GUI: toda atualização de widget só pode ocorrer na thread do mainloop
import socket             # cliente TCP que fala com o SRV
import threading          # roda a rede em thread separada para não travar a GUI
import queue              # fila thread-safe: ponte entre thread de rede e GUI
import random             # sorteia tipo/duração dos glitches (efeito imprevisível)
import sys
import os
from datetime import datetime

# Garante que o pacote-raiz do projeto esteja no sys.path mesmo quando este
# script é executado diretamente de dentro de clientes/. Sem isto, o import de
# 'utils' falharia, pois ele vive um nível acima deste arquivo.
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from utils import conexao, audio

# ── PALETA ────────────────────────────────────────────────────────────────────
# Cores escolhidas para imitar um painel de LED âmbar real (fósforo laranja dos
# displays de 7 segmentos antigos) sobre fundo quase preto. Cada cor tem uma
# variante "ON" (aceso) e "OFF" (apagado/ocioso) para que a tela "respire" entre
# o estado em-atendimento e o estado de espera, e para o efeito glitch ter de/para.
PAREDE    = "#0f0f0f"     # fundo da janela (a "parede" atrás da TV)
CORPO_TV  = "#2e2e2e"     # plástico do gabinete da TV
BISEL     = "#1c1c1c"     # moldura interna afundada ao redor da tela
TELA_BG   = "#060807"     # fundo da tela ligada (preto esverdeado de tubo)
HEADER_BG = "#0a1208"     # faixa superior da tela (título + relógio)
SEPAR     = "#0f1f0f"     # linhas separadoras finas e texto do header
HIST_BG   = "#050705"     # fundo da faixa de histórico
DIGIT_ON  = "#ffb300"     # senha acesa (âmbar forte) — cor "viva" do display
DIGIT_OFF = "#1a1200"     # senha apagada (estado ocioso, "- - -")
TEXT_ON   = "#ff8f00"     # textos auxiliares acesos
TEXT_OFF  = "#131000"     # textos auxiliares apagados
HIST_OFF  = "#1a1800"     # rótulo do histórico em repouso
HIST_ON   = "#886600"     # histórico com conteúdo
NOME_ON   = "#cc8800"     # âmbar médio para o nome do paciente
NOME_OFF  = "#0d0a00"     # nome apagado (ocioso)
GUICHE_ON  = "#00e5ff"    # ciano para o guichê em atendimento (contraste vs. âmbar)
GUICHE_OFF = "#001a1f"    # guichê apagado
CTRL_BG   = "#2a2a2a"     # barra inferior de controles físicos falsos
MARCA     = "#484848"     # cor da "marca" gravada no gabinete


class AppTerminalVisualizacao:
    """Aplicação completa do Terminal de Visualização (janela + rede + áudio).

    Responsabilidade
    ----------------
    Encapsular toda a TV em um único objeto: constrói a interface tkinter,
    sobe a thread de rede, mantém o estado da última chamada e orquestra os
    efeitos visuais. É instanciada uma única vez (ver bloco __main__).

    Padrão de design
    ----------------
    - Produtor/Consumidor: a thread de rede produz eventos em ``self._fila_ui``
      e o ``_poll_queue`` (rodando no mainloop) os consome. A fila é a única
      fronteira de comunicação entre as duas threads, garantindo que nenhum
      widget tkinter seja tocado fora da thread principal.
    - Máquina de estado leve: ``_cor_atual``, ``_nome_atual`` e
      ``_guiche_atual`` guardam o estado "real" da tela para que os efeitos de
      glitch saibam ao que RESTAURAR depois de distorcer.

    Relação com outros módulos
    --------------------------
    - utils.conexao: fornece HOST e PORTA_SRV (endereço do servidor).
    - utils.audio: reproduz o som de chamada e o jingle de inicialização.
    - SRV (servidor): contraparte remota que envia os broadcasts de chamada.
    """

    def __init__(self):
        """Inicializa a janela, o estado, a fila e dispara os laços periódicos.

        A ordem de chamada importa: a UI precisa existir antes de qualquer
        agendamento (``root.after``) ou consumo de fila, e a thread de rede só
        sobe depois que a fila e os widgets já estão prontos para receber dados.
        Por fim, ``mainloop()`` cede o controle ao tkinter (chamada bloqueante).
        """
        self.root = tk.Tk()
        self.root.title("SASE — Terminal de Visualização")
        self.root.geometry("820x560")
        self.root.configure(bg=PAREDE)
        self.root.resizable(False, False)  # painel de tamanho fixo, como um monitor real

        # ── Estado compartilhado entre rede e GUI ──
        # Fila thread-safe: a thread de rede ENFILEIRA eventos aqui e o mainloop
        # os DESENFILEIRA. É o que torna seguro atualizar a tela a partir de
        # dados que chegaram por socket em outra thread.
        self._fila_ui      = queue.Queue()
        self._historico    = []           # últimas senhas chamadas (mais recente primeiro)
        # Estado "verdadeiro" da tela. Guardado porque os glitches distorcem
        # temporariamente as cores; sem este registro não saberíamos para qual
        # cor voltar em _restaurar() (aceso vs. apagado depende de ter chamada).
        self._cor_atual    = DIGIT_OFF
        self._nome_atual   = ""
        self._guiche_atual = ""

        # Monta os widgets antes de qualquer laço que dependa deles.
        self._build_ui()
        # Laços periódicos dirigidos pelo próprio mainloop (todos via root.after):
        self._poll_queue()       # drena a fila de eventos de rede
        self._tick_hora()        # atualiza o relógio do header a cada segundo
        self._agendar_glitch()   # programa o primeiro glitch cosmético
        audio.tocar_inicio()     # jingle de boot do painel
        self._conectar()         # sobe a thread de rede (não bloqueia)
        self.root.mainloop()     # cede o controle ao tkinter (loop de eventos)

    # ── UI ───────────────────────────────────────────────────────────────────

    def _build_ui(self):
        """Constrói toda a árvore de widgets que simula uma TV física.

        A hierarquia vai de fora para dentro: chassi (gabinete) → bisel
        (moldura afundada) → tela. Dentro da tela ficam o header (título +
        relógio), a área central de exibição (senha/guichê/nome), o rodapé de
        detalhe, a faixa de histórico e, por fim, a barra inferior com
        controles físicos meramente decorativos (LEDs, botões, knob).

        Apenas widgets que serão atualizados em tempo de execução são guardados
        como atributos (self.lbl_*, self.frame_*); os puramente estáticos são
        descartáveis.
        """
        frame_chassi = tk.Frame(self.root, bg=CORPO_TV, bd=12, relief="ridge")
        frame_chassi.pack(expand=True, fill="both", padx=18, pady=18)

        # ── Tira de marca (topo do gabinete, com indicador de conexão) ──
        frame_topo = tk.Frame(frame_chassi, bg="#252525", height=22)
        frame_topo.pack(fill="x")
        frame_topo.pack_propagate(False)  # respeita a altura fixa em vez de encolher ao conteúdo
        tk.Label(frame_topo,
                 text="  IF CRATO  ·  SASE  ·  TERMINAL DE VISUALIZAÇÃO  ·  TV-2026  ",
                 bg="#252525", fg="#383838", font=("Consolas", 7, "bold")).pack(side="left")
        # Indicador textual de estado da conexão; é atualizado pela fila a partir
        # da thread de rede (eventos "status").
        self.lbl_conexao = tk.Label(frame_topo, text="◉ OFFLINE",
                                    bg="#252525", fg="#aa0000",
                                    font=("Consolas", 7, "bold"))
        self.lbl_conexao.pack(side="right", padx=12)

        # ── Bisel afundado (moldura interna ao redor da tela) ──
        frame_bisel = tk.Frame(frame_chassi, bg=BISEL, bd=5, relief="sunken")
        frame_bisel.pack(expand=True, fill="both", padx=22, pady=(8, 8))

        # ── Tela (a área "iluminada" do tubo) ──
        self.frame_tela = tk.Frame(frame_bisel, bg=TELA_BG)
        self.frame_tela.pack(expand=True, fill="both")

        # Header da tela: título do sistema à esquerda, relógio à direita.
        frame_th = tk.Frame(self.frame_tela, bg=HEADER_BG, height=30)
        frame_th.pack(fill="x")
        frame_th.pack_propagate(False)
        tk.Label(frame_th, text="◆  SISTEMA DE ATENDIMENTO POR SENHA ELETRÔNICA  ◆",
                 bg=HEADER_BG, fg=SEPAR, font=("Consolas", 9, "bold")).pack(side="left", padx=16, pady=6)
        self.lbl_hora = tk.Label(frame_th, text="00:00:00",
                                  bg=HEADER_BG, fg=SEPAR, font=("Consolas", 9, "bold"))
        self.lbl_hora.pack(side="right", padx=16, pady=6)

        tk.Frame(self.frame_tela, bg=SEPAR, height=1).pack(fill="x")  # linha separadora

        self.frame_main = tk.Frame(self.frame_tela, bg=TELA_BG)
        self.frame_main.pack(expand=True, fill="both")

        # Frame centralizador — expande e mantém senha + nome no meio da tela
        self.frame_exibe = tk.Frame(self.frame_main, bg=TELA_BG)
        self.frame_exibe.pack(expand=True, fill="both")

        self.lbl_titulo = tk.Label(self.frame_exibe, text="SENHA EM ATENDIMENTO",
                                    bg=TELA_BG, fg=TEXT_OFF, font=("Consolas", 11, "bold"))
        self.lbl_titulo.pack(pady=(26, 0))

        # Elemento principal: a senha em fonte gigante (88pt), visível de longe.
        self.lbl_chamada = tk.Label(self.frame_exibe, text="- - -",
                                     bg=TELA_BG, fg=DIGIT_OFF, font=("Consolas", 88, "bold"))
        self.lbl_chamada.pack(expand=True)

        # Guichê de destino (em ciano para destacar do âmbar da senha).
        self.lbl_guiche = tk.Label(self.frame_exibe, text="",
                                    bg=TELA_BG, fg=GUICHE_OFF,
                                    font=("Consolas", 26, "bold"))
        self.lbl_guiche.pack(pady=(0, 2))

        # Nome do paciente chamado.
        self.lbl_nome = tk.Label(self.frame_exibe, text="",
                                  bg=TELA_BG, fg=NOME_OFF,
                                  font=("Consolas", 20, "bold"))
        self.lbl_nome.pack(pady=(0, 12))

        # Linha de detalhe (eco completo da mensagem recebida do servidor).
        self.lbl_detalhe = tk.Label(self.frame_main, text="AGUARDANDO CHAMADAS...",
                                     bg=TELA_BG, fg=TEXT_OFF, font=("Consolas", 12))
        self.lbl_detalhe.pack(pady=(0, 20))

        tk.Frame(self.frame_tela, bg=SEPAR, height=1).pack(fill="x")

        # ── Faixa de histórico (últimas senhas chamadas) ──
        frame_hist = tk.Frame(self.frame_tela, bg=HIST_BG, height=26)
        frame_hist.pack(fill="x")
        frame_hist.pack_propagate(False)
        tk.Label(frame_hist, text="  ANTERIORES:", bg=HIST_BG, fg=HIST_OFF,
                 font=("Consolas", 8, "bold")).pack(side="left", pady=5)
        self.lbl_hist = tk.Label(frame_hist, text="", bg=HIST_BG, fg=HIST_OFF,
                                  font=("Consolas", 8, "bold"))
        self.lbl_hist.pack(side="left", pady=5)

        # ── Barra de controles (puramente decorativa: imita botões físicos) ──
        frame_ctrl = tk.Frame(frame_chassi, bg=CTRL_BG, height=50)
        frame_ctrl.pack(fill="x", padx=22, pady=(0, 8))
        frame_ctrl.pack_propagate(False)

        # LEDs de status: vermelho (power) e amarelo (standby) são fixos; o
        # terceiro (verde) é o ÚNICO dinâmico — guardamos seu id para alterná-lo
        # entre aceso/apagado conforme a conexão (ver _set_led).
        self._cvs_leds = tk.Canvas(frame_ctrl, bg=CTRL_BG, width=76, height=50, highlightthickness=0)
        self._cvs_leds.create_oval(6,  17, 20, 31, fill="#770000", outline="#aa0000", width=1)
        self._cvs_leds.create_oval(26, 17, 40, 31, fill="#664400", outline="#996600", width=1)
        self._id_led = self._cvs_leds.create_oval(46, 17, 60, 31, fill="#003300", outline="#005500", width=1)
        self._cvs_leds.pack(side="left", padx=4)

        tk.Label(frame_ctrl, text="[ SASE — TV ]", bg=CTRL_BG, fg=MARCA,
                 font=("Consolas", 10, "bold")).pack(expand=True)

        # Dois "botões" redondos decorativos à direita.
        cvs_k = tk.Canvas(frame_ctrl, bg=CTRL_BG, width=84, height=50, highlightthickness=0)
        for cx in (18, 58):
            cvs_k.create_oval(cx-10, 12, cx+10, 32, fill="#1e1e1e", outline="#3d3d3d", width=2)
            cvs_k.create_line(cx, 22, cx, 14, fill="#5a5a5a", width=2)
        cvs_k.pack(side="right", padx=4)

        # "Knob" de volume/potência decorativo (arco + traço indicador).
        cvs_pw = tk.Canvas(frame_ctrl, bg=CTRL_BG, width=34, height=50, highlightthickness=0)
        cvs_pw.create_oval(5, 13, 27, 35, fill="#1a1a1a", outline="#333333", width=2)
        cvs_pw.create_arc(9, 17, 23, 31, start=50, extent=260, style="arc", outline="#4a4a4a", width=2)
        cvs_pw.create_line(16, 16, 16, 24, fill="#4a4a4a", width=2)
        cvs_pw.pack(side="right")

    # ── RELÓGIO ───────────────────────────────────────────────────────────────

    def _tick_hora(self):
        """Atualiza o relógio do header uma vez por segundo, sem bloquear a GUI.

        Em vez de um ``while True: sleep(1)`` (que travaria o mainloop
        single-thread do tkinter), reagenda-se a si mesmo via ``root.after`` —
        o tkinter chama este método novamente após 1000 ms, mantendo a janela
        responsiva. O ``except TclError`` cobre o caso de a janela já ter sido
        destruída quando o callback dispara.

        Raises:
            tk.TclError: capturada internamente quando o widget não existe mais.
        """
        try:
            self.lbl_hora.config(text=datetime.now().strftime("%H:%M:%S"))
            self.root.after(1000, self._tick_hora)  # reagenda; não usa sleep para não travar o mainloop
        except tk.TclError:
            pass

    # ── LED ───────────────────────────────────────────────────────────────────

    def _set_led(self, online: bool):
        """Acende (verde) ou apaga o LED de status conforme o estado da conexão.

        Args:
            online (bool): True pinta o LED de verde vivo (conectado ao SRV);
                False o deixa em verde-escuro apagado (sem conexão).
        """
        self._cvs_leds.itemconfig(self._id_led,
                                   fill="#00bb44" if online else "#003300",
                                   outline="#00ff66" if online else "#005500")

    # ── GLITCH (efeito de tela defeituosa — sempre visível, até em idle) ──────

    def _agendar_glitch(self):
        """Agenda o próximo glitch para um instante aleatório no futuro.

        Sorteia um atraso entre 3 e 9 segundos para que o defeito pareça
        orgânico (intervalos irregulares, não cadenciados). Faz parte do ciclo
        auto-reagendado: _agendar_glitch → _glitch → _agendar_glitch ...,
        rodando inteiramente sobre o mainloop via ``root.after``.
        """
        try:
            self.root.after(random.randint(3000, 9000), self._glitch)
        except tk.TclError:
            pass

    def _glitch(self):
        """Executa UM efeito de glitch sorteado e reagenda o próximo.

        Mecanismo geral
        ----------------
        Sorteia um de cinco tipos de defeito. Cada tipo distorce cores/fundos
        dos widgets da tela por uma janela curta de milissegundos e então
        agenda (de novo via ``root.after``) a reversão ao estado real — seja
        chamando ``_restaurar`` (que lê _cor_atual/_nome_atual/_guiche_atual),
        seja via uma lambda que repinta as cores corretas. Nada aqui bloqueia o
        mainloop: tudo são callbacks encadeados.

        Tipos
        -----
        0 APAGÃO       — tela inteira fica preta por 50–140 ms.
        1 FLASH BRILHO — fundo clareia por 30–90 ms.
        2 COR ERRADA   — dígito/guichê/nome assumem cores trocadas e voltam.
        3 DOUBLE FLICKER — duas piscadas rápidas em sequência (40/80/120 ms).
        4 LINHAS FANTASMA — header e dígito mudam de cor por 60–180 ms.

        Como é apenas cosmético, qualquer ``TclError`` (janela fechada no meio
        do efeito) é silenciada e o ciclo simplesmente para.
        """
        try:
            tipo = random.randint(0, 4)

            # Conjunto de widgets que compõem a "tela" — alvo comum dos efeitos.
            _tela = (self.frame_tela, self.frame_main, self.frame_exibe,
                     self.lbl_chamada, self.lbl_titulo, self.lbl_detalhe,
                     self.lbl_nome, self.lbl_guiche)

            if tipo == 0:
                # APAGÃO completo: tela fica preta por 50–140 ms
                bg = "#010101"
                for w in _tela:
                    self._s(w, bg=bg)
                # Some também o texto (fg = fundo) para simular perda total de sinal.
                for w in (self.lbl_chamada, self.lbl_titulo, self.lbl_detalhe,
                           self.lbl_nome, self.lbl_guiche):
                    self._s(w, fg=bg)
                self.root.after(random.randint(50, 140), self._restaurar)

            elif tipo == 1:
                # FLASH DE BRILHO: tela fica bem mais clara por 30–90 ms
                bg = "#1e1600"
                for w in _tela:
                    self._s(w, bg=bg)
                # As cores do flash dependem do estado real (aceso/apagado) para
                # que o brilho seja coerente com o que está sendo exibido.
                self._s(self.lbl_chamada, fg="#ffdc73" if self._cor_atual == DIGIT_ON else "#2e2000")
                self._s(self.lbl_nome,    fg="#aa6600" if self._nome_atual   else "#1a1000")
                self._s(self.lbl_guiche,  fg="#006666" if self._guiche_atual else "#001f1f")
                self._s(self.lbl_titulo,  fg="#aa6600")
                self._s(self.lbl_detalhe, fg="#aa6600")
                self.root.after(random.randint(30, 90), self._restaurar)

            elif tipo == 2:
                # COR ERRADA: dígito + guichê + nome viram cores trocadas
                self._s(self.lbl_chamada, fg="#7a5800" if self._cor_atual == DIGIT_OFF else "#cc8800")
                self._s(self.lbl_nome,    fg="#3d2800" if not self._nome_atual   else "#886600")
                self._s(self.lbl_guiche,  fg="#003333" if not self._guiche_atual else "#007777")
                self._s(self.lbl_titulo,  fg="#3d2800")
                dur = random.randint(50, 130)
                # Reversão por lambda: repinta cada label na cor correta do estado
                # atual (este efeito só mexe em fg, então não usa _restaurar).
                self.root.after(dur, lambda: [
                    self._s(self.lbl_chamada, fg=self._cor_atual),
                    self._s(self.lbl_nome,    fg=NOME_ON   if self._nome_atual   else NOME_OFF),
                    self._s(self.lbl_guiche,  fg=GUICHE_ON if self._guiche_atual else GUICHE_OFF),
                    self._s(self.lbl_titulo,  fg=TEXT_ON if self._cor_atual == DIGIT_ON else TEXT_OFF),
                ])

            elif tipo == 3:
                # DOUBLE FLICKER: duas piscadas rápidas da tela inteira
                bg1 = "#0f0c00"

                def _flip(on):
                    # on=True: pisca (fundo claro, texto sumido). on=False: volta ao normal.
                    b = bg1 if on else TELA_BG
                    for w in (self.frame_main, self.frame_exibe, self.lbl_chamada,
                               self.lbl_guiche, self.lbl_nome, self.lbl_titulo, self.lbl_detalhe):
                        self._s(w, bg=b)
                    self._s(self.lbl_chamada, fg=TELA_BG if on else self._cor_atual)
                    self._s(self.lbl_nome,    fg=TELA_BG if on else (NOME_ON   if self._nome_atual   else NOME_OFF))
                    self._s(self.lbl_guiche,  fg=TELA_BG if on else (GUICHE_ON if self._guiche_atual else GUICHE_OFF))

                # Sequência on/off/on/off agendada em cadeia (40/80/120 ms) para
                # produzir duas piscadas sem bloquear o mainloop.
                _flip(True)
                self.root.after(40,  lambda: _flip(False))
                self.root.after(80,  lambda: _flip(True))
                self.root.after(120, lambda: _flip(False))

            else:
                # LINHAS FANTASMA: header pisca + dígito + guichê mudam cor por 60–180 ms
                self._s(self.lbl_hora,    fg="#553300")
                self._s(self.lbl_chamada, fg="#3d2800" if self._cor_atual == DIGIT_OFF else "#ffe066")
                self._s(self.lbl_nome,    fg="#1a1000" if not self._nome_atual   else "#664400")
                self._s(self.lbl_guiche,  fg="#001010" if not self._guiche_atual else "#004444")
                dur = random.randint(60, 180)
                self.root.after(dur, lambda: [
                    self._s(self.lbl_hora,    fg=SEPAR),
                    self._s(self.lbl_chamada, fg=self._cor_atual),
                    self._s(self.lbl_nome,    fg=NOME_ON   if self._nome_atual   else NOME_OFF),
                    self._s(self.lbl_guiche,  fg=GUICHE_ON if self._guiche_atual else GUICHE_OFF),
                ])

        except tk.TclError:
            return  # janela destruída no meio do efeito: aborta sem reagendar

        self._agendar_glitch()  # mantém o ciclo: programa o próximo defeito

    def _restaurar(self):
        """Devolve a tela ao estado visual correto após um glitch de fundo.

        Usado pelos efeitos que mexem no FUNDO (tipos 0 e 1). A cor de cada
        elemento é recomputada a partir do estado guardado (_cor_atual,
        _nome_atual, _guiche_atual): se há chamada ativa, repinta nas cores
        "ON"; senão, nas "OFF". É por isso que esse estado é mantido como
        atributo — sem ele não saberíamos para onde restaurar.
        """
        try:
            for w in (self.frame_tela, self.frame_main, self.frame_exibe,
                       self.lbl_chamada, self.lbl_titulo, self.lbl_detalhe,
                       self.lbl_nome, self.lbl_guiche):
                self._s(w, bg=TELA_BG)
            self._s(self.lbl_chamada, fg=self._cor_atual)
            txt = TEXT_ON if self._cor_atual == DIGIT_ON else TEXT_OFF
            self._s(self.lbl_titulo,  fg=txt)
            self._s(self.lbl_detalhe, fg=txt)
            self._s(self.lbl_nome,    fg=NOME_ON   if self._nome_atual   else NOME_OFF)
            self._s(self.lbl_guiche,  fg=GUICHE_ON if self._guiche_atual else GUICHE_OFF)
        except tk.TclError:
            pass

    def _s(self, w, **kw):
        """Aplica ``configure`` em um widget engolindo TclError (atalho seguro).

        Durante os glitches muitos ``configure`` são disparados em rajada via
        callbacks; se a janela for fechada no meio, alguns widgets já não
        existem. Este wrapper evita repetir try/except em cada chamada.

        Args:
            w: widget tkinter a configurar.
            **kw: pares de opções repassados a ``w.configure`` (ex.: bg, fg).
        """
        try:
            w.configure(**kw)
        except tk.TclError:
            pass

    # ── REDE ──────────────────────────────────────────────────────────────────

    def _conectar(self):
        """Sobe a thread de rede em modo daemon.

        A rede roda em thread SEPARADA porque ``socket.recv`` é bloqueante: se
        rodasse na thread principal, congelaria o mainloop do tkinter (que é
        single-thread) enquanto espera dados. Marcar a thread como ``daemon``
        garante que ela morra junto com o processo quando a janela for fechada,
        sem travar o encerramento.
        """
        threading.Thread(target=self._loop_conexao, daemon=True).start()

    def _loop_conexao(self):
        """Laço persistente de conexão ao SRV — roda na thread de rede.

        Fluxo do protocolo
        ------------------
        1. Abre um socket TCP e tenta conectar a (HOST, PORTA_SRV) com timeout
           de 5 s para não ficar pendurado indefinidamente em servidor ausente.
        2. Após conectar, remove o timeout (None = bloqueante) e envia o
           handshake "TV|CONECTAR" para se registrar como painel no servidor.
        3. Sinaliza ONLINE pela fila e entra no laço de recepção: cada
           ``recv(1024)`` traz uma mensagem de chamada que é apenas ENFILEIRADA
           (não tocamos widgets aqui — isso é trabalho do mainloop).
        4. ``recv`` vazio = conexão encerrada pelo servidor → sai do laço
           interno, sinaliza RECONECTANDO, espera 3 s e tenta tudo de novo.

        IMPORTANTE: este método NUNCA chama métodos da GUI diretamente; toda a
        comunicação com a interface passa por ``self._fila_ui`` (thread-safe).
        Erros de rede são tolerados (pass) de propósito — o objetivo é
        reconectar para sempre, comportando-se como um painel real.
        """
        import time
        while True:  # laço externo: reconecta para sempre
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.settimeout(5)  # evita travar indefinidamente se o SRV não responder
                s.connect((conexao.HOST, conexao.PORTA_SRV))
                s.settimeout(None)  # já conectado: recv pode bloquear à vontade
                # Handshake: identifica este cliente como TV para o servidor.
                # sendall garante o envio completo; '\n' delimita a mensagem.
                s.sendall("TV|CONECTAR\n".encode("utf-8"))
                self._fila_ui.put(("status", "◉ ONLINE", "#00bb44", True))
                buffer = ""  # acumula bytes para remontar mensagens por linha
                while True:  # laço interno: recebe broadcasts enquanto a conexão vive
                    dados = s.recv(1024)
                    if not dados:
                        break  # peer fechou a conexão → reconecta
                    # Enquadramento '\n': processa cada mensagem completa
                    # separadamente (evita exibir dois broadcasts concatenados).
                    buffer += dados.decode("utf-8")
                    while "\n" in buffer:
                        linha, buffer = buffer.split("\n", 1)
                        if linha:
                            # Não atualiza a tela aqui: só entrega o texto à fila.
                            self._fila_ui.put(("chamada", linha))
            except (ConnectionRefusedError, TimeoutError, OSError):
                pass  # servidor fora do ar / queda de rede: cai para o retry
            except Exception:
                pass  # qualquer outra falha também não deve matar o laço
            # Chegou aqui = perdemos/falhamos a conexão: avisa a GUI e espera.
            self._fila_ui.put(("status", "◉ RECONECTANDO...", "#f39c12", False))
            time.sleep(3)  # backoff fixo antes de nova tentativa

    def _poll_queue(self):
        """Consome a fila de eventos de rede e atualiza a GUI — roda no mainloop.

        Por que ``root.after(100, ...)`` em vez de um loop com sleep?
        -----------------------------------------------------------
        O mainloop do tkinter é single-thread: um ``sleep`` aqui congelaria a
        janela inteira. Em vez disso, drenamos TUDO o que estiver na fila
        agora, retornamos o controle ao tkinter, e pedimos para sermos chamados
        de novo em 100 ms. Isso cria um polling cooperativo e não-bloqueante —
        e, por rodar na thread principal, é o lugar SEGURO para mexer em widgets
        com dados que vieram da thread de rede.

        Tipos de evento na fila
        -----------------------
        - ("status", texto, cor, online): atualiza o rótulo de conexão e o LED.
        - ("chamada", msg): processa uma nova senha chamada (parsing + exibição
          + histórico + áudio + flash).
        """
        while not self._fila_ui.empty():  # esvazia tudo que chegou desde o último poll
            ev = self._fila_ui.get()
            if ev[0] == "status":
                _, txt, cor, online = ev
                self.lbl_conexao.config(text=txt, fg=cor)
                self._set_led(online)
            elif ev[0] == "chamada":
                msg = ev[1]
                # ── Parsing da mensagem do servidor ──
                # formato: "Guichê X chama: N1 — Nome Aqui"
                # extrai guichê: pega o último token antes de " chama:"
                guiche = ""
                if " chama:" in msg:
                    pre = msg.split(" chama:")[0]
                    tokens = pre.split()
                    guiche = tokens[-1] if tokens else ""

                # Separa a parte após ": " em senha e nome (divididos por " — ").
                parte = msg.split(": ", 1)[-1] if ": " in msg else msg
                if " — " in parte:
                    senha, nome = parte.split(" — ", 1)
                    senha = senha.strip()
                    nome  = nome.strip()
                else:
                    senha = parte.strip()
                    nome  = ""

                # ── Atualiza o estado real (consultado pelos glitches) ──
                self._cor_atual    = DIGIT_ON   # passou a haver chamada ativa
                self._nome_atual   = nome
                self._guiche_atual = guiche

                # ── Pinta a tela com a chamada ──
                self.lbl_chamada.config(text=senha, fg=DIGIT_ON)
                self.lbl_guiche.config(
                    text=f"► DIRIJA-SE AO  GUICHÊ  {guiche}" if guiche else "",
                    fg=GUICHE_ON if guiche else GUICHE_OFF
                )
                self.lbl_nome.config(text=nome.upper(), fg=NOME_ON if nome else NOME_OFF)
                self.lbl_titulo.config(fg=TEXT_ON)
                self.lbl_detalhe.config(text=msg.upper(), fg=TEXT_ON)
                # ── Histórico: insere no topo e mantém só as 6 últimas ──
                self._historico.insert(0, f"{senha}→G{guiche}" if guiche else senha)
                self._historico = self._historico[:6]
                self.lbl_hist.config(text="   ·   ".join(self._historico), fg=HIST_ON)
                # ── Áudio + destaque visual da nova chamada ──
                audio.tocar(nome=nome, guiche=guiche)
                self._flash()
        try:
            self.root.after(100, self._poll_queue)  # reagenda o polling sem bloquear
        except tk.TclError:
            pass

    def _flash(self, n=0):
        """Pisca a tela algumas vezes ao receber uma nova chamada (destaque).

        Diferente do glitch (cosmético/aleatório), este flash é uma reação
        INTENCIONAL a uma chamada nova, chamando a atenção de quem olha. Usa
        ``root.after`` em CADEIA — cada invocação alterna a cor de fundo e
        agenda a próxima 130 ms depois, passando ``n+1`` — em vez de um loop com
        sleep, justamente para não bloquear o mainloop single-thread.

        Args:
            n (int): contador de passos da animação. Pares = fundo escuro,
                ímpares = fundo normal; ao chegar em 6, encerra e garante o
                fundo de tela normal.
        """
        try:
            _ws = (self.frame_main, self.frame_exibe,
                   self.lbl_titulo, self.lbl_chamada,
                   self.lbl_guiche, self.lbl_nome, self.lbl_detalhe)
            if n < 6:
                cor = "#100c00" if n % 2 == 0 else TELA_BG  # alterna escuro/normal
                for w in _ws:
                    w.configure(bg=cor)
                self.root.after(130, lambda: self._flash(n + 1))  # próximo passo da cadeia
            else:
                # Fim da animação: assegura que tudo voltou ao fundo padrão.
                for w in _ws:
                    w.configure(bg=TELA_BG)
        except tk.TclError:
            pass


# ── PONTO DE ENTRADA ───────────────────────────────────────────────────────────
# Instanciar a classe já dispara o mainloop (chamada bloqueante em __init__).
# O guard __main__ evita que isso ocorra caso o módulo seja importado.
if __name__ == "__main__":
    AppTerminalVisualizacao()
