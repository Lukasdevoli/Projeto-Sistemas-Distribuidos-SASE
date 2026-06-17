# =============================================================================
# VERSÃO ORIGINAL (CLI) — antes da interface gráfica
# =============================================================================
#
# # clientes/tv.py
# import socket
# import sys
# import os
#
# sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
# from utils import conexao
#
# def iniciar_tv():
#     print("--- TERMINAL DE VISUALIZAÇÃO (TV) INICIADO ---")
#     print("Aguardando chamadas...")
#
#     cliente_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
#
#     try:
#         cliente_socket.connect((conexao.HOST, conexao.PORTA_SRV))
#
#         # A TV se identifica para o servidor e avisa que vai ficar conectada
#         mensagem = "TV|CONECTAR"
#         cliente_socket.send(mensagem.encode('utf-8'))
#
#         # Loop infinito recebendo os avisos do servidor
#         while True:
#             # A execução do script pausa aqui (bloqueio) até receber dados do servidor
#             dados = cliente_socket.recv(1024)
#
#             if not dados:
#                 # Se dados vier vazio, o servidor fechou a conexão
#                 print("Conexão com o servidor encerrada.")
#                 break
#
#             mensagem_recebida = dados.decode('utf-8')
#
#             # Exibe a chamada de forma destacada
#             print("="*40)
#             print(f"NOVA CHAMADA: {mensagem_recebida}")
#             print("="*40)
#
#     except ConnectionRefusedError:
#         print("Erro: Servidor offline. Inicie o servidor primeiro.")
#     finally:
#         cliente_socket.close()
#
# if __name__ == "__main__":
#     iniciar_tv()
#
# =============================================================================
# VERSÃO ATUAL (GUI com tkinter)
# =============================================================================

import tkinter as tk
import socket
import threading
import queue
import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from utils import conexao, audio

COR_FUNDO   = "#0d0d0d"
COR_PAINEL  = "#1a1a2e"
COR_CHAMADA = "#f1c40f"
COR_TEXTO   = "#ecf0f1"
COR_INATIVO = "#3d3d3d"


class AppTerminalVisualizacao:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("TV — Terminal de Visualização")
        self.root.geometry("640x420")
        self.root.configure(bg=COR_FUNDO)
        self.root.resizable(True, True)
        self.root.minsize(480, 320)

        self._fila_ui = queue.Queue()
        self._historico = []
        self._build_ui()
        self._poll_queue()
        self._conectar()
        self.root.mainloop()

    def _build_ui(self):
        # --- Barra superior ---
        frame_top = tk.Frame(self.root, bg=COR_PAINEL, height=48)
        frame_top.pack(fill="x")
        frame_top.pack_propagate(False)

        tk.Label(
            frame_top, text="TERMINAL DE VISUALIZAÇÃO — SASE",
            bg=COR_PAINEL, fg="#5d6d7e",
            font=("Segoe UI", 10)
        ).pack(side="left", padx=20, pady=12)

        self.lbl_conexao = tk.Label(
            frame_top, text="● Conectando...",
            bg=COR_PAINEL, fg="#f39c12",
            font=("Segoe UI", 9)
        )
        self.lbl_conexao.pack(side="right", padx=20)

        # --- Área principal (display) ---
        self.frame_main = tk.Frame(self.root, bg=COR_FUNDO)
        self.frame_main.pack(expand=True, fill="both")

        self.lbl_titulo = tk.Label(
            self.frame_main, text="SENHA EM ATENDIMENTO",
            bg=COR_FUNDO, fg=COR_INATIVO,
            font=("Segoe UI", 11, "bold")
        )
        self.lbl_titulo.pack(pady=(20, 0))

        self.lbl_chamada = tk.Label(
            self.frame_main, text="---",
            bg=COR_FUNDO, fg=COR_INATIVO,
            font=("Consolas", 96, "bold")
        )
        self.lbl_chamada.pack(expand=True)

        self.lbl_detalhe = tk.Label(
            self.frame_main, text="Aguardando chamadas...",
            bg=COR_FUNDO, fg=COR_INATIVO,
            font=("Segoe UI", 12)
        )
        self.lbl_detalhe.pack(pady=(0, 10))

        # --- Barra inferior (histórico) ---
        frame_bottom = tk.Frame(self.root, bg=COR_PAINEL, height=36)
        frame_bottom.pack(fill="x")
        frame_bottom.pack_propagate(False)

        tk.Label(
            frame_bottom, text="ANTERIORES:",
            bg=COR_PAINEL, fg="#5d6d7e",
            font=("Segoe UI", 8)
        ).pack(side="left", padx=10, pady=8)

        self.lbl_hist = tk.Label(
            frame_bottom, text="",
            bg=COR_PAINEL, fg="#5d6d7e",
            font=("Consolas", 9)
        )
        self.lbl_hist.pack(side="left", pady=8)

    def _conectar(self):
        threading.Thread(target=self._loop_conexao, daemon=True).start()

    def _loop_conexao(self):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.connect((conexao.HOST, conexao.PORTA_SRV))
            s.send("TV|CONECTAR".encode("utf-8"))
            self._fila_ui.put(("status", "● Conectado", "#2ecc71"))

            while True:
                dados = s.recv(1024)
                if not dados:
                    self._fila_ui.put(("status", "● Conexão encerrada pelo servidor", "#e74c3c"))
                    break
                self._fila_ui.put(("chamada", dados.decode("utf-8")))

        except ConnectionRefusedError:
            self._fila_ui.put(("status", "● Servidor offline. Inicie o SRV.", "#e74c3c"))
        except Exception as e:
            self._fila_ui.put(("status", f"● Erro: {e}", "#e74c3c"))

    def _poll_queue(self):
        while not self._fila_ui.empty():
            evento = self._fila_ui.get()

            if evento[0] == "status":
                _, texto, cor = evento
                self.lbl_conexao.config(text=texto, fg=cor)

            elif evento[0] == "chamada":
                msg = evento[1]
                # msg = "Guichê X chama: N1"
                senha = msg.split(": ")[-1] if ": " in msg else msg

                self.lbl_chamada.config(text=senha, fg=COR_CHAMADA)
                self.lbl_detalhe.config(text=msg, fg=COR_TEXTO)

                self._historico.insert(0, senha)
                self._historico = self._historico[:6]
                self.lbl_hist.config(text="  |  ".join(self._historico))

                audio.tocar()
                self._flash()

        try:
            self.root.after(100, self._poll_queue)
        except tk.TclError:
            pass

    def _flash(self, n=0):
        try:
            if n < 6:
                cor = "#1a1a00" if n % 2 == 0 else COR_FUNDO
                self.frame_main.configure(bg=cor)
                self.lbl_titulo.configure(bg=cor)
                self.lbl_chamada.configure(bg=cor)
                self.lbl_detalhe.configure(bg=cor)
                self.root.after(120, lambda: self._flash(n + 1))
            else:
                self.frame_main.configure(bg=COR_FUNDO)
                self.lbl_titulo.configure(bg=COR_FUNDO)
                self.lbl_chamada.configure(bg=COR_FUNDO)
                self.lbl_detalhe.configure(bg=COR_FUNDO)
        except tk.TclError:
            pass  # janela fechada durante a animação


if __name__ == "__main__":
    AppTerminalVisualizacao()
