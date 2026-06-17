# =============================================================================
# VERSÃO ORIGINAL (CLI) — antes da interface gráfica
# =============================================================================
#
# import socket
# import sys
# import os
#
# sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
# from utils import conexao
#
# def iniciar_ts():
#     print("--- TERMINAL DE SENHAS (TS) INICIADO ---")
#     print("Digite 'N' para Normal, 'P' para Prioritária ou 'S' para Sair.")
#
#     while True:
#         escolha = input("\nGerar qual senha? ").strip().upper()
#
#         if escolha == 'S':
#             print("Encerrando Terminal de Senhas...")
#             break
#         elif escolha not in ['N', 'P']:
#             print("Opção inválida! Use N ou P.")
#             continue
#
#         # Criando o socket TCP (SOCK_STREAM) para o protocolo IPv4 (AF_INET)
#         cliente_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
#
#         try:
#             # Conecta ao servidor utilizando as configurações do utils
#             cliente_socket.connect((conexao.HOST, conexao.PORTA_SRV))
#
#             # Montamos a mensagem no formato: "IDENTIFICADOR_DO_CLIENTE|COMANDO"
#             # Ex: "TS|GERAR_N"
#             mensagem = f"TS|GERAR_{escolha}"
#
#             # Envia a mensagem codificada em bytes para o servidor
#             cliente_socket.send(mensagem.encode('utf-8'))
#
#             # Aguarda a confirmação do servidor (buffer de 1024 bytes)
#             resposta = cliente_socket.recv(1024).decode('utf-8')
#             print(f"Resposta do Servidor: {resposta}")
#
#         # Tratamento de erro caso o servidor não esteja em serviço
#         except ConnectionRefusedError:
#             print("Erro: Não foi possível conectar. O Servidor (SRV) está rodando?")
#         finally:
#             # Sempre fecha a conexão após a requisição para liberar recursos
#             cliente_socket.close()
#
# if __name__ == "__main__":
#     iniciar_ts()
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

COR_FUNDO    = "#1e3a5f"
COR_DISPLAY  = "#0d1b2a"
COR_NORMAL   = "#27ae60"
COR_PRIO     = "#e67e22"
COR_TEXTO    = "#ecf0f1"
COR_SUBTEXTO = "#7f8c8d"


class AppTerminalSenhas:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("TS — Terminal de Senhas")
        self.root.geometry("380x460")
        self.root.configure(bg=COR_FUNDO)
        self.root.resizable(False, False)

        self._fila_ui = queue.Queue()
        self._build_ui()
        self._poll_queue()
        self.root.mainloop()

    def _build_ui(self):
        tk.Label(
            self.root, text="TERMINAL DE SENHAS",
            bg=COR_FUNDO, fg=COR_TEXTO,
            font=("Segoe UI", 14, "bold")
        ).pack(pady=(22, 2))

        tk.Label(
            self.root, text="Sistema de Atendimento por Senha Eletrônica",
            bg=COR_FUNDO, fg=COR_SUBTEXTO,
            font=("Segoe UI", 9)
        ).pack()

        # --- Display da senha gerada ---
        frame_display = tk.Frame(self.root, bg=COR_DISPLAY)
        frame_display.pack(padx=30, pady=22, fill="x")

        tk.Label(
            frame_display, text="SENHA GERADA",
            bg=COR_DISPLAY, fg=COR_SUBTEXTO,
            font=("Segoe UI", 9)
        ).pack(pady=(12, 0))

        self.lbl_senha = tk.Label(
            frame_display, text="---",
            bg=COR_DISPLAY, fg=COR_TEXTO,
            font=("Consolas", 60, "bold")
        )
        self.lbl_senha.pack(pady=(0, 12))

        # --- Botões ---
        frame_botoes = tk.Frame(self.root, bg=COR_FUNDO)
        frame_botoes.pack(padx=30, fill="x")

        self.btn_n = tk.Button(
            frame_botoes, text="NORMAL\n(N)",
            bg=COR_NORMAL, fg="white",
            font=("Segoe UI", 13, "bold"),
            relief="flat", cursor="hand2", height=3,
            command=lambda: self._gerar("N"),
            activebackground="#1e8449", activeforeground="white"
        )
        self.btn_n.pack(side="left", expand=True, fill="x", padx=(0, 8))

        self.btn_p = tk.Button(
            frame_botoes, text="PRIORITÁRIA\n(P)",
            bg=COR_PRIO, fg="white",
            font=("Segoe UI", 13, "bold"),
            relief="flat", cursor="hand2", height=3,
            command=lambda: self._gerar("P"),
            activebackground="#ca6f1e", activeforeground="white"
        )
        self.btn_p.pack(side="left", expand=True, fill="x")

        # --- Status ---
        self.lbl_status = tk.Label(
            self.root, text="Pronto. Selecione o tipo de senha.",
            bg=COR_FUNDO, fg=COR_SUBTEXTO,
            font=("Segoe UI", 9), wraplength=340
        )
        self.lbl_status.pack(pady=18)

    def _gerar(self, tipo):
        self.btn_n.config(state="disabled")
        self.btn_p.config(state="disabled")
        self.lbl_status.config(text="Conectando ao servidor...", fg="#f39c12")
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
                senha = resposta.split(": ")[-1]
                cor = COR_NORMAL if tipo == "N" else COR_PRIO
                self.lbl_senha.config(text=senha, fg=cor)
                self.lbl_status.config(text=resposta, fg=COR_TEXTO)
                audio.tocar()
            else:
                self.lbl_status.config(text=evento[1], fg="#e74c3c")

        self.root.after(100, self._poll_queue)


if __name__ == "__main__":
    AppTerminalSenhas()
