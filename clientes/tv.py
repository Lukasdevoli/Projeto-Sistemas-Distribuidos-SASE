# =============================================================================
# VERSÃO ORIGINAL (CLI) — antes da interface gráfica
# =============================================================================
# (ver histórico git para a versão CLI)
# =============================================================================
# VERSÃO ATUAL — GUI com chassi realista, bisel, controles e efeito glitch
# =============================================================================

import tkinter as tk
import socket
import threading
import queue
import random
import sys
import os
from datetime import datetime

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from utils import conexao, audio

# === PALETA ===
PAREDE    = "#0f0f0f"
CORPO_TV  = "#2e2e2e"
BISEL     = "#1c1c1c"
TELA_BG   = "#060807"
HEADER_BG = "#0a1208"
SEPAR     = "#0f1f0f"
HIST_BG   = "#050705"
DIGIT_ON  = "#ffb300"
DIGIT_OFF = "#1a1200"
TEXT_ON   = "#ff8f00"
TEXT_OFF  = "#131000"
HIST_OFF  = "#1a1800"
HIST_ON   = "#886600"
NOME_ON   = "#cc8800"    # âmbar médio para o nome do paciente
NOME_OFF  = "#0d0a00"    # nome apagado (ocioso)
GUICHE_ON  = "#00e5ff"   # ciano para o guichê em atendimento
GUICHE_OFF = "#001a1f"   # guichê apagado
CTRL_BG   = "#2a2a2a"
MARCA     = "#484848"


class AppTerminalVisualizacao:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("SASE — Terminal de Visualização")
        self.root.geometry("820x560")
        self.root.configure(bg=PAREDE)
        self.root.resizable(False, False)

        self._fila_ui      = queue.Queue()
        self._historico    = []
        self._cor_atual    = DIGIT_OFF
        self._nome_atual   = ""
        self._guiche_atual = ""

        self._build_ui()
        self._poll_queue()
        self._tick_hora()
        self._agendar_glitch()
        audio.tocar_inicio()
        self._conectar()
        self.root.mainloop()

    # ── UI ───────────────────────────────────────────────────────────────────

    def _build_ui(self):
        frame_chassi = tk.Frame(self.root, bg=CORPO_TV, bd=12, relief="ridge")
        frame_chassi.pack(expand=True, fill="both", padx=18, pady=18)

        # Tira de marca
        frame_topo = tk.Frame(frame_chassi, bg="#252525", height=22)
        frame_topo.pack(fill="x")
        frame_topo.pack_propagate(False)
        tk.Label(frame_topo,
                 text="  IF CRATO  ·  SASE  ·  TERMINAL DE VISUALIZAÇÃO  ·  TV-2026  ",
                 bg="#252525", fg="#383838", font=("Consolas", 7, "bold")).pack(side="left")
        self.lbl_conexao = tk.Label(frame_topo, text="◉ OFFLINE",
                                    bg="#252525", fg="#aa0000",
                                    font=("Consolas", 7, "bold"))
        self.lbl_conexao.pack(side="right", padx=12)

        # Bisel sunken
        frame_bisel = tk.Frame(frame_chassi, bg=BISEL, bd=5, relief="sunken")
        frame_bisel.pack(expand=True, fill="both", padx=22, pady=(8, 8))

        # Tela
        self.frame_tela = tk.Frame(frame_bisel, bg=TELA_BG)
        self.frame_tela.pack(expand=True, fill="both")

        frame_th = tk.Frame(self.frame_tela, bg=HEADER_BG, height=30)
        frame_th.pack(fill="x")
        frame_th.pack_propagate(False)
        tk.Label(frame_th, text="◆  SISTEMA DE ATENDIMENTO POR SENHA ELETRÔNICA  ◆",
                 bg=HEADER_BG, fg=SEPAR, font=("Consolas", 9, "bold")).pack(side="left", padx=16, pady=6)
        self.lbl_hora = tk.Label(frame_th, text="00:00:00",
                                  bg=HEADER_BG, fg=SEPAR, font=("Consolas", 9, "bold"))
        self.lbl_hora.pack(side="right", padx=16, pady=6)

        tk.Frame(self.frame_tela, bg=SEPAR, height=1).pack(fill="x")

        self.frame_main = tk.Frame(self.frame_tela, bg=TELA_BG)
        self.frame_main.pack(expand=True, fill="both")

        # Frame centralizador — expande e mantém senha + nome no meio da tela
        self.frame_exibe = tk.Frame(self.frame_main, bg=TELA_BG)
        self.frame_exibe.pack(expand=True, fill="both")

        self.lbl_titulo = tk.Label(self.frame_exibe, text="SENHA EM ATENDIMENTO",
                                    bg=TELA_BG, fg=TEXT_OFF, font=("Consolas", 11, "bold"))
        self.lbl_titulo.pack(pady=(26, 0))

        self.lbl_chamada = tk.Label(self.frame_exibe, text="- - -",
                                     bg=TELA_BG, fg=DIGIT_OFF, font=("Consolas", 88, "bold"))
        self.lbl_chamada.pack(expand=True)

        self.lbl_guiche = tk.Label(self.frame_exibe, text="",
                                    bg=TELA_BG, fg=GUICHE_OFF,
                                    font=("Consolas", 26, "bold"))
        self.lbl_guiche.pack(pady=(0, 2))

        self.lbl_nome = tk.Label(self.frame_exibe, text="",
                                  bg=TELA_BG, fg=NOME_OFF,
                                  font=("Consolas", 20, "bold"))
        self.lbl_nome.pack(pady=(0, 12))

        self.lbl_detalhe = tk.Label(self.frame_main, text="AGUARDANDO CHAMADAS...",
                                     bg=TELA_BG, fg=TEXT_OFF, font=("Consolas", 12))
        self.lbl_detalhe.pack(pady=(0, 20))

        tk.Frame(self.frame_tela, bg=SEPAR, height=1).pack(fill="x")

        frame_hist = tk.Frame(self.frame_tela, bg=HIST_BG, height=26)
        frame_hist.pack(fill="x")
        frame_hist.pack_propagate(False)
        tk.Label(frame_hist, text="  ANTERIORES:", bg=HIST_BG, fg=HIST_OFF,
                 font=("Consolas", 8, "bold")).pack(side="left", pady=5)
        self.lbl_hist = tk.Label(frame_hist, text="", bg=HIST_BG, fg=HIST_OFF,
                                  font=("Consolas", 8, "bold"))
        self.lbl_hist.pack(side="left", pady=5)

        # Barra de controles
        frame_ctrl = tk.Frame(frame_chassi, bg=CTRL_BG, height=50)
        frame_ctrl.pack(fill="x", padx=22, pady=(0, 8))
        frame_ctrl.pack_propagate(False)

        self._cvs_leds = tk.Canvas(frame_ctrl, bg=CTRL_BG, width=76, height=50, highlightthickness=0)
        self._cvs_leds.create_oval(6,  17, 20, 31, fill="#770000", outline="#aa0000", width=1)
        self._cvs_leds.create_oval(26, 17, 40, 31, fill="#664400", outline="#996600", width=1)
        self._id_led = self._cvs_leds.create_oval(46, 17, 60, 31, fill="#003300", outline="#005500", width=1)
        self._cvs_leds.pack(side="left", padx=4)

        tk.Label(frame_ctrl, text="[ SASE — TV ]", bg=CTRL_BG, fg=MARCA,
                 font=("Consolas", 10, "bold")).pack(expand=True)

        cvs_k = tk.Canvas(frame_ctrl, bg=CTRL_BG, width=84, height=50, highlightthickness=0)
        for cx in (18, 58):
            cvs_k.create_oval(cx-10, 12, cx+10, 32, fill="#1e1e1e", outline="#3d3d3d", width=2)
            cvs_k.create_line(cx, 22, cx, 14, fill="#5a5a5a", width=2)
        cvs_k.pack(side="right", padx=4)

        cvs_pw = tk.Canvas(frame_ctrl, bg=CTRL_BG, width=34, height=50, highlightthickness=0)
        cvs_pw.create_oval(5, 13, 27, 35, fill="#1a1a1a", outline="#333333", width=2)
        cvs_pw.create_arc(9, 17, 23, 31, start=50, extent=260, style="arc", outline="#4a4a4a", width=2)
        cvs_pw.create_line(16, 16, 16, 24, fill="#4a4a4a", width=2)
        cvs_pw.pack(side="right")

    # ── RELÓGIO ───────────────────────────────────────────────────────────────

    def _tick_hora(self):
        try:
            self.lbl_hora.config(text=datetime.now().strftime("%H:%M:%S"))
            self.root.after(1000, self._tick_hora)
        except tk.TclError:
            pass

    # ── LED ───────────────────────────────────────────────────────────────────

    def _set_led(self, online: bool):
        self._cvs_leds.itemconfig(self._id_led,
                                   fill="#00bb44" if online else "#003300",
                                   outline="#00ff66" if online else "#005500")

    # ── GLITCH (efeito de tela defeituosa — sempre visível, até em idle) ──────

    def _agendar_glitch(self):
        try:
            self.root.after(random.randint(3000, 9000), self._glitch)
        except tk.TclError:
            pass

    def _glitch(self):
        try:
            tipo = random.randint(0, 4)

            _tela = (self.frame_tela, self.frame_main, self.frame_exibe,
                     self.lbl_chamada, self.lbl_titulo, self.lbl_detalhe,
                     self.lbl_nome, self.lbl_guiche)

            if tipo == 0:
                # APAGÃO completo: tela fica preta por 50–140 ms
                bg = "#010101"
                for w in _tela:
                    self._s(w, bg=bg)
                for w in (self.lbl_chamada, self.lbl_titulo, self.lbl_detalhe,
                           self.lbl_nome, self.lbl_guiche):
                    self._s(w, fg=bg)
                self.root.after(random.randint(50, 140), self._restaurar)

            elif tipo == 1:
                # FLASH DE BRILHO: tela fica bem mais clara por 30–90 ms
                bg = "#1e1600"
                for w in _tela:
                    self._s(w, bg=bg)
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
                    b = bg1 if on else TELA_BG
                    for w in (self.frame_main, self.frame_exibe, self.lbl_chamada,
                               self.lbl_guiche, self.lbl_nome, self.lbl_titulo, self.lbl_detalhe):
                        self._s(w, bg=b)
                    self._s(self.lbl_chamada, fg=TELA_BG if on else self._cor_atual)
                    self._s(self.lbl_nome,    fg=TELA_BG if on else (NOME_ON   if self._nome_atual   else NOME_OFF))
                    self._s(self.lbl_guiche,  fg=TELA_BG if on else (GUICHE_ON if self._guiche_atual else GUICHE_OFF))

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
            return

        self._agendar_glitch()

    def _restaurar(self):
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
        try:
            w.configure(**kw)
        except tk.TclError:
            pass

    # ── REDE ──────────────────────────────────────────────────────────────────

    def _conectar(self):
        threading.Thread(target=self._loop_conexao, daemon=True).start()

    def _loop_conexao(self):
        import time
        while True:
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.settimeout(5)
                s.connect((conexao.HOST, conexao.PORTA_SRV))
                s.settimeout(None)
                s.send("TV|CONECTAR".encode("utf-8"))
                self._fila_ui.put(("status", "◉ ONLINE", "#00bb44", True))
                while True:
                    dados = s.recv(1024)
                    if not dados:
                        break
                    self._fila_ui.put(("chamada", dados.decode("utf-8")))
            except (ConnectionRefusedError, TimeoutError, OSError):
                pass
            except Exception:
                pass
            self._fila_ui.put(("status", "◉ RECONECTANDO...", "#f39c12", False))
            time.sleep(3)

    def _poll_queue(self):
        while not self._fila_ui.empty():
            ev = self._fila_ui.get()
            if ev[0] == "status":
                _, txt, cor, online = ev
                self.lbl_conexao.config(text=txt, fg=cor)
                self._set_led(online)
            elif ev[0] == "chamada":
                msg = ev[1]
                # formato: "Guichê X chama: N1 — Nome Aqui"
                # extrai guichê
                guiche = ""
                if " chama:" in msg:
                    pre = msg.split(" chama:")[0]
                    tokens = pre.split()
                    guiche = tokens[-1] if tokens else ""

                parte = msg.split(": ", 1)[-1] if ": " in msg else msg
                if " — " in parte:
                    senha, nome = parte.split(" — ", 1)
                    senha = senha.strip()
                    nome  = nome.strip()
                else:
                    senha = parte.strip()
                    nome  = ""

                self._cor_atual    = DIGIT_ON
                self._nome_atual   = nome
                self._guiche_atual = guiche

                self.lbl_chamada.config(text=senha, fg=DIGIT_ON)
                self.lbl_guiche.config(
                    text=f"► DIRIJA-SE AO  GUICHÊ  {guiche}" if guiche else "",
                    fg=GUICHE_ON if guiche else GUICHE_OFF
                )
                self.lbl_nome.config(text=nome.upper(), fg=NOME_ON if nome else NOME_OFF)
                self.lbl_titulo.config(fg=TEXT_ON)
                self.lbl_detalhe.config(text=msg.upper(), fg=TEXT_ON)
                self._historico.insert(0, f"{senha}→G{guiche}" if guiche else senha)
                self._historico = self._historico[:6]
                self.lbl_hist.config(text="   ·   ".join(self._historico), fg=HIST_ON)
                audio.tocar(nome=nome, guiche=guiche)
                self._flash()
        try:
            self.root.after(100, self._poll_queue)
        except tk.TclError:
            pass

    def _flash(self, n=0):
        try:
            _ws = (self.frame_main, self.frame_exibe,
                   self.lbl_titulo, self.lbl_chamada,
                   self.lbl_guiche, self.lbl_nome, self.lbl_detalhe)
            if n < 6:
                cor = "#100c00" if n % 2 == 0 else TELA_BG
                for w in _ws:
                    w.configure(bg=cor)
                self.root.after(130, lambda: self._flash(n + 1))
            else:
                for w in _ws:
                    w.configure(bg=TELA_BG)
        except tk.TclError:
            pass


if __name__ == "__main__":
    AppTerminalVisualizacao()
