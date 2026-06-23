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

import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog
import socket
import threading
import queue
import sys
import os
import random
from datetime import datetime

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from utils import conexao, audio, relatorio

# === PALETA — Terminal de Balcão (antracito escuro + verde) ===
PAREDE     = "#0a0a0a"    # fundo externo
CORPO      = "#2a2a2a"    # chassi antracito escuro
CORPO_HI   = "#484848"    # bevel highlight
DISPLAY_BG = "#050e05"    # fundo do display (verde quase preto)
COR_VERDE  = "#00e676"    # verde brilhante
COR_BOTAO  = "#0d3a1a"    # fundo do botão CHAMAR
COR_BTN_HI = "#1a7038"    # hover do botão
COR_TEXTO  = "#e8f5e9"    # texto claro
COR_SUBTEX = "#3a5a3a"    # subtexto
BADGE_BG   = "#060e06"    # fundo do cabeçalho de guichê

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

_NOMES_TRISTES = [
    "Guiche Sem Nome", "Ninguem me nomeou", "Alguem teve preguica de mim",
    "Guiche do Esquecido", "Eu Precisava de um Nome",
    "Sem Identidade S/A", "Por favor me da um nome",
]

def _piada_terminal():
    sep = "=" * 52
    piada = random.choice(_PIADAS)
    print("\n" + sep)
    print("  Piada do dia (voce nao digitou nada, merece):")
    print()
    for linha in piada.splitlines():
        print("  " + linha)
    print(sep + "\n")


class AppTerminalAtendimento:
    def __init__(self):
        self.root = tk.Tk()
        self.root.withdraw()

        # Aceita --guiche=X passado pelo SRV ao lançar instâncias automaticamente
        id_guiche = None
        for arg in sys.argv[1:]:
            if arg.startswith("--guiche="):
                id_guiche = arg.split("=", 1)[1].strip()
                break

        if not id_guiche:
            id_guiche = simpledialog.askstring(
                "Terminal de Atendimento",
                "Digite o numero deste guiche (ex: 1, 2, 3):",
                parent=self.root
            )
            if not id_guiche or not id_guiche.strip():
                _piada_terminal()
                id_guiche = random.choice(_NOMES_TRISTES)

        self.id_guiche     = id_guiche.strip()
        self._socket       = None
        self._fila_ui      = queue.Queue()
        self._ativo        = True
        self._historico    = []
        self._contador_seq = 0

        self.root.deiconify()
        self.root.title(f"TA — Guichê {self.id_guiche}")
        self.root.geometry("460x640")
        self.root.configure(bg=PAREDE)
        self.root.resizable(False, False)
        self.root.protocol("WM_DELETE_WINDOW", self._fechar)

        self._build_ui()
        self._poll_queue()
        self._conectar()
        self.root.mainloop()

    # ── CORPO DA MÁQUINA (desenhado no Canvas) ────────────────────────────────

    def _build_ui(self):
        W, H = 460, 640

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

        # Botão Relatório na faixa
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
        self._ativo = False
        self.root.destroy()

    def _conectar(self):
        threading.Thread(target=self._loop_conexao, daemon=True).start()

    def _loop_conexao(self):
        import time
        while self._ativo:
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.settimeout(5)
                s.connect((conexao.HOST, conexao.PORTA_SRV))
                s.settimeout(None)
                s.send(f"TA_CONECTAR|{self.id_guiche}".encode("utf-8"))
                self._socket = s
                self._fila_ui.put(("conexao", "ok"))

                while self._ativo:
                    dados = s.recv(1024)
                    if not dados:
                        break
                    self._fila_ui.put(("resposta", dados.decode("utf-8")))

            except (ConnectionRefusedError, TimeoutError, OSError):
                pass
            except Exception:
                pass
            finally:
                self._socket = None

            if not self._ativo:
                break
            self._fila_ui.put(("reconectando",))
            time.sleep(3)

    def _chamar(self):
        if not self._socket:
            self.lbl_status.config(text="Sem conexão com o servidor.", fg="#e74c3c")
            return
        self.btn_chamar.config(state="disabled")
        self.lbl_status.config(text="Solicitando próxima senha...", fg="#f39c12")
        try:
            self._socket.send(f"TA_SOLICITAR|{self.id_guiche}".encode("utf-8"))
        except Exception as e:
            self._fila_ui.put(("erro", f"Falha ao enviar: {e}"))

    # ── RELATÓRIO ─────────────────────────────────────────────────────────────

    def _abrir_relatorio(self):
        titulo = "RELATORIO DE ATENDIMENTOS - GUICHE {}".format(self.id_guiche)
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
                self.btn_chamar.config(state="normal")
                if "Fila vazia" in msg:
                    self.lbl_senha.config(text="---", fg=COR_SUBTEX)
                    self.lbl_status.config(text=msg, fg="#e67e22")
                else:
                    # formato: "Guichê X chama: N1 — Nome Aqui"
                    parte_senha = msg.split(": ", 1)[-1] if ": " in msg else msg
                    if " — " in parte_senha:
                        senha, nome = parte_senha.split(" — ", 1)
                        senha = senha.strip()
                        nome  = nome.strip()
                    else:
                        senha = parte_senha.strip()
                        nome  = ""
                    self.lbl_senha.config(text=senha, fg="#2ecc71")
                    self.lbl_status.config(
                        text=f"{senha} — {nome}" if nome else senha,
                        fg=COR_TEXTO
                    )
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

        self.root.after(100, self._poll_queue)


if __name__ == "__main__":
    AppTerminalAtendimento()
