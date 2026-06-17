# =============================================================================
# VERSÃO ORIGINAL (CLI) — antes da interface gráfica
# =============================================================================
#
# # clientes/ta.py
# import socket
# import sys
# import os
#
# sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
# from utils import conexao
#
# def iniciar_ta():
#     # Simulando que este terminal seja o Guichê 1 (poderia ser dinâmico no futuro)
#     id_guiche = input("Digite o número deste guichê (ex: 1, 2, 3): ").strip()
#     print(f"--- TERMINAL DE ATENDIMENTO (GUICHÊ {id_guiche}) INICIADO ---")
#     print("Pressione ENTER para chamar o próximo da fila ou digite 'S' para sair.")
#
#     while True:
#         acao = input("\nAguardando comando... ")
#
#         if acao.strip().upper() == 'S':
#             print("Encerrando Terminal de Atendimento...")
#             break
#
#         cliente_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
#
#         try:
#             cliente_socket.connect((conexao.HOST, conexao.PORTA_SRV))
#
#             # Formato da mensagem: "TA|ID_DO_GUICHE" -> Avisa o servidor quem está pedindo
#             mensagem = f"TA|{id_guiche}"
#             cliente_socket.send(mensagem.encode('utf-8'))
#
#             # Aguarda o servidor responder qual senha foi atribuída a este guichê
#             resposta = cliente_socket.recv(1024).decode('utf-8')
#             print(f">>> {resposta}")
#
#         except ConnectionRefusedError:
#             print("Erro: Servidor offline.")
#         finally:
#             cliente_socket.close()
#
# if __name__ == "__main__":
#     iniciar_ta()
#
# =============================================================================
# VERSÃO ATUAL (GUI com tkinter + conexão permanente ao servidor)
# =============================================================================

import tkinter as tk
from tkinter import simpledialog
import socket
import threading
import queue
import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from utils import conexao, audio

COR_FUNDO    = "#1a3a1a"
COR_HEADER   = "#145214"
COR_DISPLAY  = "#0d1a0d"
COR_BOTAO    = "#27ae60"
COR_TEXTO    = "#ecf0f1"
COR_SUBTEXTO = "#7f8c8d"


class AppTerminalAtendimento:
    def __init__(self):
        self.root = tk.Tk()
        self.root.withdraw()

        id_guiche = simpledialog.askstring(
            "Terminal de Atendimento",
            "Digite o número deste guichê (ex: 1, 2, 3):",
            parent=self.root
        )
        if not id_guiche or not id_guiche.strip():
            self.root.destroy()
            return

        self.id_guiche = id_guiche.strip()
        self._socket  = None
        self._fila_ui = queue.Queue()
        self._ativo   = True   # False quando a janela é fechada

        self.root.deiconify()
        self.root.title(f"TA — Guichê {self.id_guiche}")
        self.root.geometry("420x520")
        self.root.configure(bg=COR_FUNDO)
        self.root.resizable(False, False)

        self.root.protocol("WM_DELETE_WINDOW", self._fechar)
        self._build_ui()
        self._poll_queue()
        self._conectar()
        self.root.mainloop()

    def _build_ui(self):
        # --- Cabeçalho ---
        frame_header = tk.Frame(self.root, bg=COR_HEADER)
        frame_header.pack(fill="x")

        tk.Label(
            frame_header, text="TERMINAL DE ATENDIMENTO",
            bg=COR_HEADER, fg=COR_TEXTO,
            font=("Segoe UI", 13, "bold")
        ).pack(pady=(10, 2))

        frame_sub = tk.Frame(frame_header, bg=COR_HEADER)
        frame_sub.pack(pady=(0, 10))

        tk.Label(
            frame_sub, text=f"GUICHÊ  {self.id_guiche}",
            bg=COR_HEADER, fg="#2ecc71",
            font=("Segoe UI", 12, "bold")
        ).pack(side="left", padx=(0, 16))

        self.lbl_conexao = tk.Label(
            frame_sub, text="● Conectando...",
            bg=COR_HEADER, fg="#f39c12",
            font=("Segoe UI", 9)
        )
        self.lbl_conexao.pack(side="left")

        # --- Display da senha em atendimento ---
        frame_display = tk.Frame(self.root, bg=COR_DISPLAY)
        frame_display.pack(padx=30, pady=20, fill="x")

        tk.Label(
            frame_display, text="ATENDENDO",
            bg=COR_DISPLAY, fg=COR_SUBTEXTO,
            font=("Segoe UI", 9)
        ).pack(pady=(12, 0))

        self.lbl_senha = tk.Label(
            frame_display, text="---",
            bg=COR_DISPLAY, fg=COR_TEXTO,
            font=("Consolas", 56, "bold")
        )
        self.lbl_senha.pack(pady=(0, 12))

        # --- Botão chamar ---
        self.btn_chamar = tk.Button(
            self.root, text="CHAMAR PRÓXIMA SENHA",
            bg=COR_BOTAO, fg="white",
            font=("Segoe UI", 13, "bold"),
            relief="flat", cursor="hand2", height=2,
            state="disabled",
            command=self._chamar,
            activebackground="#1e8449", activeforeground="white"
        )
        self.btn_chamar.pack(padx=30, fill="x")

        # --- Status ---
        self.lbl_status = tk.Label(
            self.root, text="Aguardando conexão com o servidor...",
            bg=COR_FUNDO, fg=COR_SUBTEXTO,
            font=("Segoe UI", 9)
        )
        self.lbl_status.pack(pady=8)

        # --- Histórico ---
        tk.Label(
            self.root, text="HISTÓRICO DE CHAMADAS",
            bg=COR_FUNDO, fg=COR_SUBTEXTO,
            font=("Segoe UI", 8, "bold")
        ).pack(anchor="w", padx=30)

        self.listbox = tk.Listbox(
            self.root,
            bg="#0d1a0d", fg=COR_SUBTEXTO,
            font=("Consolas", 10),
            selectbackground=COR_HEADER,
            relief="flat", bd=0, height=7,
            highlightthickness=0
        )
        self.listbox.pack(padx=30, fill="x", pady=(2, 20))

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
                pass  # servidor offline ou inacessível
            except Exception:
                pass
            finally:
                self._socket = None

            if not self._ativo:
                break

            # Aguarda 3 segundos e tenta reconectar
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

    def _poll_queue(self):
        while not self._fila_ui.empty():
            evento = self._fila_ui.get()
            tipo = evento[0]

            if tipo == "conexao":
                if evento[1] == "ok":
                    self.lbl_conexao.config(text="● Conectado", fg="#2ecc71")
                    self.lbl_status.config(text="Pronto. Clique para chamar.", fg=COR_TEXTO)
                    self.btn_chamar.config(state="normal")

            elif tipo == "reconectando":
                self.lbl_conexao.config(text="● Reconectando...", fg="#f39c12")
                self.lbl_status.config(text="Servidor indisponível. Tentando reconectar...", fg="#f39c12")
                self.btn_chamar.config(state="disabled")

            elif tipo == "resposta":
                msg = evento[1]
                self.btn_chamar.config(state="normal")
                if "Fila vazia" in msg:
                    self.lbl_senha.config(text="---", fg=COR_SUBTEXTO)
                    self.lbl_status.config(text=msg, fg="#e67e22")
                else:
                    senha = msg.split(": ")[-1]
                    self.lbl_senha.config(text=senha, fg="#2ecc71")
                    self.lbl_status.config(text="Senha chamada com sucesso.", fg=COR_TEXTO)
                    self.listbox.insert(0, msg)
                    audio.tocar()

            elif tipo == "erro":
                self.lbl_conexao.config(text="● Erro", fg="#e74c3c")
                self.lbl_status.config(text=evento[1], fg="#e74c3c")
                self.btn_chamar.config(state="disabled")

        self.root.after(100, self._poll_queue)


if __name__ == "__main__":
    AppTerminalAtendimento()
