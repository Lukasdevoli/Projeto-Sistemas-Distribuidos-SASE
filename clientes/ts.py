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

import tkinter as tk
import socket
import threading
import queue
import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from utils import conexao, audio

# === PALETA ===
PAREDE     = "#0a0a0a"    # fundo externo (parede/balcão)
CORPO      = "#525252"    # chassi cinza médio — contrasta com displays escuros
CORPO_DARK = "#2e2e2e"    # sombra do chassi
CORPO_HI   = "#787878"    # highlight do chassi (bevel superior-esquerdo)
DISPLAY_BG = "#040b14"    # fundo do display LCD (quase preto)
DISPLAY_BD = "#0a1828"    # borda do display
BTN_N_BG   = "#0d3a1a"    # verde muito escuro — botão Normal
BTN_N_TXT  = "#00ff7f"    # verde brilhante
BTN_N_HI   = "#1a7038"
BTN_P_BG   = "#4a1800"    # laranja-escuro — botão Prioritária
BTN_P_TXT  = "#ff9f33"    # laranja brilhante
BTN_P_HI   = "#7a2a00"
DIGIT_N    = "#00e5ff"    # ciano — senha Normal no display
DIGIT_P    = "#ff9f33"    # laranja — senha Prioritária no display
DIGIT_OFF  = "#050e18"    # dígito apagado
BADGE_BG   = "#080c1a"    # fundo da placa institucional
STATUS_FG  = "#5a5a5a"


class AppTerminalSenhas:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("SASE — Terminal de Senhas (TS)")
        self.root.geometry("420x680")
        self.root.configure(bg=PAREDE)
        self.root.resizable(False, False)

        self._fila_ui = queue.Queue()
        self._build_ui()
        self._poll_queue()
        self.root.mainloop()

    # ── CORPO DA MÁQUINA (desenhado no Canvas) ────────────────────────────────

    def _build_ui(self):
        W, H = 420, 680

        # Canvas cobre a janela inteira e serve de "parede" + corpo da máquina
        self._cvs = tk.Canvas(
            self.root, bg=PAREDE, width=W, height=H,
            highlightthickness=0
        )
        self._cvs.place(x=0, y=0, width=W, height=H)

        self._desenhar_corpo(W, H)

        # Frame de conteúdo posicionado sobre o Canvas
        fc = tk.Frame(self.root, bg=CORPO)
        fc.place(x=22, y=64, width=W - 44, height=546)
        self._build_content(fc)

    def _desenhar_corpo(self, W, H):
        c = self._cvs

        # Sombra
        c.create_rectangle(20, 20, W - 12, H - 12, fill="#050505", outline="")

        # Corpo principal (chassi cinza)
        c.create_rectangle(14, 14, W - 14, H - 14,
                            fill=CORPO, outline="#1e1e1e", width=3)

        # Bevel: topo + esquerda (mais claro = luz vindo de cima-esquerda)
        for i in range(4):
            clr = "#787878" if i < 2 else "#686868"
            c.create_line(17 + i, 17 + i, W - 17 - i, 17 + i, fill=clr, width=1)  # top
            c.create_line(17 + i, 17 + i, 17 + i, H - 17 - i, fill=clr, width=1)  # left

        # Bevel: baixo + direita (mais escuro = sombra)
        for i in range(4):
            clr = "#1a1a1a" if i < 2 else "#2a2a2a"
            c.create_line(17 + i, H - 17 - i, W - 17 - i, H - 17 - i, fill=clr, width=1)  # bottom
            c.create_line(W - 17 - i, 17 + i, W - 17 - i, H - 17 - i, fill=clr, width=1)  # right

        # Parafusos Phillips em cada canto
        for sx, sy in [(32, 32), (W - 32, 32), (32, H - 32), (W - 32, H - 32)]:
            r = 9
            c.create_oval(sx - r, sy - r, sx + r, sy + r,
                           fill="#404040", outline="#707070", width=1)
            c.create_oval(sx - 4, sy - 4, sx + 4, sy + 4,
                           fill="#1a1a1a", outline="")
            c.create_line(sx - 6, sy, sx + 6, sy, fill="#707070", width=1)
            c.create_line(sx, sy - 6, sx, sy + 6, fill="#707070", width=1)

        # Faixa de marca (topo do chassi)
        c.create_rectangle(18, 18, W - 18, 60, fill="#3a3a3a", outline="")
        c.create_text(W // 2 - 16, 39,
                      text="INSTITUTO FEDERAL  ·  CAMPUS CRATO  ·  SASE  ·  TS-2026",
                      fill="#5a5a5a", font=("Consolas", 7, "bold"), anchor="center")

        # LED de status na faixa de marca
        self._id_led = c.create_oval(W - 52, 29, W - 38, 43,
                                      fill="#003300", outline="#005500", width=1)
        c.create_oval(W - 68, 29, W - 54, 43, fill="#440000", outline="#660000", width=1)

        # Linha separadora abaixo da faixa de marca
        c.create_line(18, 62, W - 18, 62, fill="#3a3a3a", width=2)

        # Slots de ventilação (parte inferior do chassi)
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

        # Knobs decorativos (barra inferior)
        for kx in (34, 58):
            c.create_oval(kx - 9, H - 46, kx + 9, H - 28,
                           fill="#3a3a3a", outline="#606060", width=2)
            c.create_line(kx, H - 42, kx, H - 30, fill="#606060", width=2)

        # Botão power (canto inferior direito)
        c.create_oval(W - 50, H - 48, W - 30, H - 28,
                       fill="#2a2a2a", outline="#4a4a4a", width=2)
        c.create_arc(W - 47, H - 45, W - 33, H - 31,
                      start=50, extent=260, style="arc", outline="#5a5a5a", width=2)
        c.create_line(W - 40, H - 45, W - 40, H - 37, fill="#5a5a5a", width=2)

    # ── CONTEÚDO (Frame sobre o Canvas) ───────────────────────────────────────

    def _build_content(self, parent):
        # ── PLACA INSTITUCIONAL ────────────────────────────────────────────
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
        frame_bd = tk.Frame(parent, bg="#1e1e1e", bd=5, relief="sunken")
        frame_bd.pack(fill="x", padx=8, pady=(10, 0))

        frame_display = tk.Frame(frame_bd, bg=DISPLAY_BG)
        frame_display.pack(fill="x", padx=3, pady=3)

        tk.Label(
            frame_display, text="ÚLTIMA SENHA GERADA",
            bg=DISPLAY_BG, fg=DIGIT_OFF,
            font=("Consolas", 8, "bold")
        ).pack(pady=(8, 0))

        self.lbl_senha = tk.Label(
            frame_display, text="- - -",
            bg=DISPLAY_BG, fg=DIGIT_OFF,
            font=("Consolas", 64, "bold")
        )
        self.lbl_senha.pack(pady=(0, 8))

        # ── BOTÕES FÍSICOS (N e P) ─────────────────────────────────────────
        frame_btns = tk.Frame(parent, bg=CORPO)
        frame_btns.pack(fill="x", padx=8, pady=(12, 0))

        # Botão N — Normal
        frame_n_sombra = tk.Frame(frame_btns, bg="#040d08")
        frame_n_sombra.pack(side="left", expand=True, fill="both", padx=(0, 8))

        frame_n_ext = tk.Frame(frame_n_sombra, bg=BTN_N_BG, bd=10, relief="raised")
        frame_n_ext.pack(fill="both", padx=2, pady=2)

        frame_n_int = tk.Frame(frame_n_ext, bg=BTN_N_BG, bd=4, relief="raised")
        frame_n_int.pack(fill="both", padx=3, pady=3)

        self.btn_n = tk.Button(
            frame_n_int, text="N",
            bg=BTN_N_BG, fg=BTN_N_TXT,
            font=("Consolas", 62, "bold"),
            relief="flat", cursor="hand2", bd=0,
            activebackground=BTN_N_HI, activeforeground="white",
            command=lambda: self._gerar("N")
        )
        self.btn_n.pack(fill="both", expand=True, ipady=8)

        # Botão P — Prioritária
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
        self.lbl_status = tk.Label(
            parent,
            text="Pressione  N  para Normal  ·  P  para Prioritária",
            bg=CORPO, fg=STATUS_FG,
            font=("Segoe UI", 8), wraplength=360
        )
        self.lbl_status.pack(pady=(8, 0))

        # ── SLOT DE TICKET ─────────────────────────────────────────────────
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
            cvs_slot.delete("slot_lines")
            w = cvs_slot.winfo_width() or 340
            for y in (7, 11, 15):
                cvs_slot.create_line(12, y, w - 12, y,
                                      fill="#1e1e1e", width=1, tags="slot_lines")
            cvs_slot.create_line(12, 11, w - 12, 11,
                                  fill="#2a2a2a", width=2, tags="slot_lines")

        cvs_slot.bind("<Configure>", _draw_slot)
        self.root.after(50, _draw_slot)

    # ── LED ───────────────────────────────────────────────────────────────────

    def _set_led(self, ok: bool):
        self._cvs.itemconfig(
            self._id_led,
            fill="#00bb44" if ok else "#003300",
            outline="#00ff66" if ok else "#005500"
        )

    # ── LÓGICA ────────────────────────────────────────────────────────────────

    def _gerar(self, tipo):
        self.btn_n.config(state="disabled")
        self.btn_p.config(state="disabled")
        self.lbl_status.config(text="Conectando ao servidor...", fg="#f39c12")
        self._set_led(False)
        threading.Thread(target=self._requisitar, args=(tipo,), daemon=True).start()

    def _requisitar(self, tipo):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.connect((conexao.HOST, conexao.PORTA_SRV))
            s.send(f"TS|GERAR_{tipo}".encode("utf-8"))
            resposta = s.recv(1024).decode("utf-8")
            s.close()
            self._fila_ui.put(("ok", resposta, tipo))
        except ConnectionRefusedError:
            self._fila_ui.put(("erro", "Servidor offline. Inicie o SRV primeiro."))
        except Exception as e:
            self._fila_ui.put(("erro", f"Erro: {e}"))

    def _poll_queue(self):
        while not self._fila_ui.empty():
            evento = self._fila_ui.get()
            self.btn_n.config(state="normal")
            self.btn_p.config(state="normal")

            if evento[0] == "ok":
                _, resposta, tipo = evento
                # formato: "Senha gerada: N1 — Nome Aqui"
                parte = resposta.split(": ", 1)[-1] if ": " in resposta else resposta
                senha = parte.split(" — ")[0].strip() if " — " in parte else parte.strip()
                cor = DIGIT_N if tipo == "N" else DIGIT_P
                self.lbl_senha.config(text=senha, fg=cor)
                self.lbl_status.config(text=resposta, fg="#ecf0f1")
                self._set_led(True)
                audio.tocar()
            else:
                self.lbl_status.config(text=evento[1], fg="#e74c3c")
                self._set_led(False)

        self.root.after(100, self._poll_queue)


if __name__ == "__main__":
    AppTerminalSenhas()
