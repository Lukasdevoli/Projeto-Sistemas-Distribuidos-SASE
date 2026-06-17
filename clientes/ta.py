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

COR_FUNDO    = "#1a3a1a"
COR_HEADER   = "#145214"
COR_DISPLAY  = "#0d1a0d"
COR_BOTAO    = "#27ae60"
COR_TEXTO    = "#ecf0f1"
COR_SUBTEXTO = "#7f8c8d"

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
    "Guiche Sem Nome",
    "Ninguem me nomeou",
    "Alguem teve preguica de mim",
    "Guiche do Esquecido",
    "Eu Precisava de um Nome",
    "Sem Identidade S/A",
    "Por favor me da um nome",
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

        id_guiche = simpledialog.askstring(
            "Terminal de Atendimento",
            "Digite o numero deste guiche (ex: 1, 2, 3):",
            parent=self.root
        )
        if not id_guiche or not id_guiche.strip():
            _piada_terminal()
            id_guiche = random.choice(_NOMES_TRISTES)

        self.id_guiche = id_guiche.strip()
        self._socket   = None
        self._fila_ui  = queue.Queue()
        self._ativo    = True

        # Histórico local de atendimentos deste guichê
        self._historico    = []
        self._contador_seq = 0

        self.root.deiconify()
        self.root.title(f"TA — Guichê {self.id_guiche}")
        self.root.geometry("420x560")
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
        ).pack(side="left", padx=16, pady=(10, 2))

        # Botão relatório no cabeçalho
        tk.Button(
            frame_header, text="Relatorio",
            bg="#8e44ad", fg="white",
            font=("Segoe UI", 8, "bold"),
            relief="flat", cursor="hand2",
            padx=10, pady=3,
            command=self._abrir_relatorio,
            activebackground="#6c3483", activeforeground="white",
        ).pack(side="right", padx=12, pady=8)

        frame_sub = tk.Frame(frame_header, bg=COR_HEADER)
        frame_sub.pack(fill="x", padx=16, pady=(0, 10))

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
            self.root, text="CHAMAR PROXIMA SENHA",
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
            self.root, text="Aguardando conexao com o servidor...",
            bg=COR_FUNDO, fg=COR_SUBTEXTO,
            font=("Segoe UI", 9)
        )
        self.lbl_status.pack(pady=8)

        # --- Histórico ---
        tk.Label(
            self.root, text="HISTORICO DE CHAMADAS",
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
            self.lbl_status.config(text="Sem conexao com o servidor.", fg="#e74c3c")
            return
        self.btn_chamar.config(state="disabled")
        self.lbl_status.config(text="Solicitando proxima senha...", fg="#f39c12")
        try:
            self._socket.send(f"TA_SOLICITAR|{self.id_guiche}".encode("utf-8"))
        except Exception as e:
            self._fila_ui.put(("erro", f"Falha ao enviar: {e}"))

    def _abrir_relatorio(self):
        titulo = "RELATORIO DE ATENDIMENTOS - GUICHE {}".format(self.id_guiche)
        extras = {"Guiche": self.id_guiche}
        extras.update(relatorio._stats_sessao(self._historico))
        texto  = relatorio.gerar_txt(titulo, self._historico, com_guiche=False, extras=extras)

        janela = tk.Toplevel(self.root)
        janela.title("Relatorio — Guiche {}".format(self.id_guiche))
        janela.geometry("640x480")
        janela.configure(bg=COR_FUNDO)
        janela.resizable(True, True)

        frame_txt = tk.Frame(janela, bg=COR_FUNDO)
        frame_txt.pack(fill="both", expand=True, padx=12, pady=(12, 0))

        sb = tk.Scrollbar(frame_txt, orient="vertical")
        sb.pack(side="right", fill="y")

        txt = tk.Text(
            frame_txt,
            bg=COR_DISPLAY, fg=COR_TEXTO,
            font=("Consolas", 10),
            relief="flat", bd=0,
            wrap="none",
            highlightthickness=0,
            padx=10, pady=10,
            yscrollcommand=sb.set,
        )
        txt.pack(side="left", fill="both", expand=True)
        sb.config(command=txt.yview)
        txt.insert("1.0", texto)
        txt.config(state="disabled")

        frame_btns = tk.Frame(janela, bg=COR_FUNDO)
        frame_btns.pack(fill="x", padx=12, pady=10)

        def salvar_pdf():
            path = filedialog.asksaveasfilename(
                defaultextension=".pdf",
                filetypes=[("PDF", "*.pdf")],
                initialfile="relatorio_guiche{}_{}.pdf".format(
                    self.id_guiche, datetime.now().strftime("%Y%m%d_%H%M%S")
                ),
                parent=janela,
            )
            if not path:
                return
            ok, msg = relatorio.gerar_pdf(
                path, titulo, self._historico, com_guiche=False, extras=extras
            )
            if ok:
                messagebox.showinfo("PDF salvo", "Arquivo salvo em:\n{}".format(path), parent=janela)
            else:
                messagebox.showerror("Erro ao gerar PDF", msg, parent=janela)

        def salvar_txt():
            path = filedialog.asksaveasfilename(
                defaultextension=".txt",
                filetypes=[("Arquivo de texto", "*.txt")],
                initialfile="relatorio_guiche{}_{}.txt".format(
                    self.id_guiche, datetime.now().strftime("%Y%m%d_%H%M%S")
                ),
                parent=janela,
            )
            if path:
                with open(path, "w", encoding="utf-8") as f:
                    f.write(texto)

        tk.Button(
            frame_btns, text="Salvar PDF",
            bg="#c0392b", fg="white",
            font=("Segoe UI", 10, "bold"), relief="flat", cursor="hand2",
            command=salvar_pdf, padx=16, pady=6,
            activebackground="#922b21", activeforeground="white",
        ).pack(side="left", padx=(0, 6))

        tk.Button(
            frame_btns, text="Salvar .txt",
            bg="#2980b9", fg="white",
            font=("Segoe UI", 10), relief="flat", cursor="hand2",
            command=salvar_txt, padx=16, pady=6,
            activebackground="#1a5276", activeforeground="white",
        ).pack(side="left", padx=(0, 6))

        tk.Button(
            frame_btns, text="Fechar",
            bg="#7f8c8d", fg="white",
            font=("Segoe UI", 10), relief="flat", cursor="hand2",
            command=janela.destroy, padx=16, pady=6,
            activebackground="#626567", activeforeground="white",
        ).pack(side="left")

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
                self.lbl_status.config(text="Servidor indisponivel. Tentando reconectar...", fg="#f39c12")
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

                    # Registra no histórico local
                    self._contador_seq += 1
                    self._historico.append({
                        "ordem": self._contador_seq,
                        "senha": senha,
                        "tipo":  "Prioritario" if senha.startswith("P") else "Normal",
                        "hora":  datetime.now(),
                    })

                    audio.tocar()

            elif tipo == "erro":
                self.lbl_conexao.config(text="● Erro", fg="#e74c3c")
                self.lbl_status.config(text=evento[1], fg="#e74c3c")
                self.btn_chamar.config(state="disabled")

        self.root.after(100, self._poll_queue)


if __name__ == "__main__":
    AppTerminalAtendimento()
