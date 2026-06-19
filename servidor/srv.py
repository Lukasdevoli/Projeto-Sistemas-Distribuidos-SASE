# =============================================================================
# VERSÃO ORIGINAL — o servidor estava vazio no commit inicial.
# A lógica foi construída do zero neste projeto:
#   - Gerenciamento de filas Normal e Prioritária
#   - Regra de prioridade: a cada 2 senhas Normais, 1 Prioritária obrigatória
#   - Registro e rastreamento de guichês ativos (TA_CONECTAR)
#   - Broadcast para todos os Terminais de Visualização (TV)
#   - Timestamps em cada evento (recebimento e envio de SEAs)
# =============================================================================
# VERSÃO ATUAL (GUI com tkinter + lógica de servidor em classe separada)
# =============================================================================

import tkinter as tk
from tkinter import filedialog, messagebox
import socket
import threading
import queue
import subprocess
import sys
import os
from datetime import datetime

import random

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from utils import conexao, relatorio

# 100 maiores brasileiros de todos os tempos (SBT/BBC, 2012)
NOMES = [
    "Ayrton Senna", "Chico Xavier", "Fernando Henrique Cardoso",
    "Getúlio Vargas", "Irmã Dulce", "Juscelino Kubitschek",
    "Lula", "Oscar Niemeyer", "Pelé", "Princesa Isabel",
    "Alberto Santos Dumont", "Tiradentes",
    "Edir Macedo", "Chico Anysio", "Ronaldo Fenômeno",
    "Dercy Gonçalves", "Zilda Arns", "Roberto Carlos",
    "José Alencar", "Neymar", "Eike Batista",
    "Ruy Barbosa", "Frei Galvão", "Manuel Jacinto Coelho",
    "Oswaldo Cruz", "Silas Malafaia", "Dom Pedro II",
    "Chico Mendes", "Luiz Gonzaga", "Renato Russo",
    "Betinho", "Pe. Cícero Batista", "Dilma Rousseff",
    "Tancredo Neves", "Luciano Huck", "Valdemiro Santiago",
    "Hélder Câmara", "Renato Aragão", "Rodrigo Faro",
    "Xuxa Meneghel", "Machado de Assis", "Luan Santana",
    "Ivete Sangalo", "Elis Regina", "Visconde de Mauá",
    "Raul Seixas", "Leonel Brizola", "Tiririca",
    "Gugu Liberato", "Rogério Ceni", "Paiva Netto",
    "Carlos Drummond", "Zumbi dos Palmares", "RR Soares",
    "Paulo Freire", "Hebe Camargo", "Monteiro Lobato",
    "Roberto Marinho", "Marcos Palmeiras", "Pe. Marcelo Rossi",
    "Zico", "Amácio Mazzaropi", "Dedé",
    "Ulysses Guimarães", "Reynaldo Gianecchini", "Carlos Chagas",
    "Jonas Abib", "Duque de Caxias", "Ermírio de Moraes",
    "Cândido Rondon", "Lua Blanco", "Michel Teló",
    "Garrincha", "Lampião", "Claudia Leitte",
    "Luís Carlos Prestes", "Marcos Pontes", "Fernando Collor",
    "José Serra", "Sócrates", "José Luiz Datena",
    "Ronaldinho Gaúcho", "Joelma", "Chico Buarque",
    "Chacrinha", "Amado Batista", "William Bonner",
    "Cazuza", "Tom Jobim", "Anderson Silva",
    "Pe. Landell de Moura", "Romário", "Jorge Amado",
    "Ronald Golias", "Itamar Franco", "Roberto Justus",
    "Ana Paula Valadão", "Vital Brazil", "Jô Soares",
    "Maria da Penha",
]

COR_FUNDO  = "#1a1a2e"
COR_PAINEL = "#16213e"
COR_LOG    = "#0d0d1a"
COR_TEXTO  = "#ecf0f1"


# ---------------------------------------------------------------------------
# Janela de relatório
# ---------------------------------------------------------------------------

def _abrir_janela_relatorio(parent, titulo, texto, fn_salvar_pdf=None):
    janela = tk.Toplevel(parent)
    janela.title(titulo)
    janela.geometry("720x540")
    janela.configure(bg=COR_FUNDO)
    janela.resizable(True, True)

    frame_txt = tk.Frame(janela, bg=COR_FUNDO)
    frame_txt.pack(fill="both", expand=True, padx=12, pady=(12, 0))

    sb = tk.Scrollbar(frame_txt, orient="vertical")
    sb.pack(side="right", fill="y")

    txt = tk.Text(
        frame_txt,
        bg=COR_LOG, fg=COR_TEXTO,
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

    def salvar_txt():
        path = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[("Arquivo de texto", "*.txt")],
            initialfile="relatorio_sase_{}.txt".format(
                datetime.now().strftime("%Y%m%d_%H%M%S")
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
        command=lambda: fn_salvar_pdf(janela) if fn_salvar_pdf else None,
        padx=16, pady=6,
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


# ---------------------------------------------------------------------------
# Lógica central do servidor
# ---------------------------------------------------------------------------

class ServidorSASE:
    def __init__(self, log_fn):
        self._log = log_fn

        self.fila_normal = []
        self.fila_prioritaria = []
        self.proximo_N = 1
        self.proximo_P = 1
        self.normals_consecutivos = 0

        # Histórico de atendimentos: [{ordem, senha, nome, tipo, guiche, hora}]
        self.historico_atendimentos = []
        self._contador_ordem = 0

        # Mapa senha → nome associado (atribuído na geração)
        self._nomes = {}

        # Guichês registrados: {id_guiche: socket}
        self.tas_conectados = {}
        # TVs conectadas para broadcast
        self.tvs_conectadas = []

        self.lock = threading.Lock()

    def _proximo_da_fila(self):
        """
        Spec (Projeto_SD.pdf, seção 2.1 item 4c):
        'Para cada duas SEAs do tipo N informadas, a próxima SEA deverá ser
        obrigatoriamente do tipo P, se houver.'

        Padrão: N, N, P, N, N, P, ...
        - Após 2 Normais consecutivos → força Prioritária (se houver)
        - Sem P disponível → continua com N normalmente
        - Sem N disponível → serve P diretamente
        """
        if self.normals_consecutivos >= 2 and self.fila_prioritaria:
            sea = self.fila_prioritaria.pop(0)
            self.normals_consecutivos = 0
        elif self.fila_normal:
            sea = self.fila_normal.pop(0)
            self.normals_consecutivos += 1
        elif self.fila_prioritaria:
            sea = self.fila_prioritaria.pop(0)
            self.normals_consecutivos = 0
        else:
            sea = None
        return sea

    def _broadcast_tvs(self, mensagem, tvs_snapshot):
        """Envia para todos os TVs da lista. Fora do lock."""
        desconectadas = []
        for tv_sock in tvs_snapshot:
            try:
                tv_sock.send(mensagem.encode("utf-8"))
            except Exception:
                desconectadas.append(tv_sock)
        if desconectadas:
            with self.lock:
                for tv in desconectadas:
                    if tv in self.tvs_conectadas:
                        self.tvs_conectadas.remove(tv)

    def _atender_guiche(self, conn, id_guiche):
        """Processa uma solicitação de senha de um guichê registrado."""
        with self.lock:
            sea = self._proximo_da_fila()
            if sea:
                nome = self._nomes.pop(sea, "")
                self._contador_ordem += 1
                self.historico_atendimentos.append({
                    "ordem":  self._contador_ordem,
                    "senha":  sea,
                    "nome":   nome,
                    "tipo":   "Prioritario" if sea.startswith("P") else "Normal",
                    "guiche": id_guiche,
                    "hora":   datetime.now(),
                })
                resposta = f"Guichê {id_guiche} chama: {sea} — {nome}" if nome else f"Guichê {id_guiche} chama: {sea}"
                tvs_snapshot = list(self.tvs_conectadas)
            else:
                resposta = "Fila vazia. Nenhuma senha aguardando atendimento."
                tvs_snapshot = []

        try:
            conn.send(resposta.encode("utf-8"))
        except Exception:
            return

        if sea:
            self._log(f"SEA enviada ao Guichê {id_guiche} e TVs: {sea}", "ta")
            self._broadcast_tvs(resposta, tvs_snapshot)
        else:
            self._log(f"Guichê {id_guiche} solicitou senha — fila vazia.", "aviso")

    def handle_client(self, conn, addr):
        tipo = None
        partes = []
        try:
            dados = conn.recv(1024).decode("utf-8").strip()
            partes = dados.split("|")
            tipo = partes[0]

            # --- Terminal de Senhas ---
            if tipo == "TS" and len(partes) == 2:
                comando = partes[1]
                with self.lock:
                    if comando == "GERAR_N":
                        sea = f"N{self.proximo_N}"
                        self.proximo_N += 1
                        nome = random.choice(NOMES)
                        self._nomes[sea] = nome
                        self.fila_normal.append(sea)
                        self._log(
                            f"SEA recebida do TS: {sea} — {nome}  "
                            f"[Normal: {len(self.fila_normal)} | Prio: {len(self.fila_prioritaria)}]",
                            "ts"
                        )
                        conn.send(f"Senha gerada: {sea} — {nome}".encode("utf-8"))
                    elif comando == "GERAR_P":
                        sea = f"P{self.proximo_P}"
                        self.proximo_P += 1
                        nome = random.choice(NOMES)
                        self._nomes[sea] = nome
                        self.fila_prioritaria.append(sea)
                        self._log(
                            f"SEA recebida do TS: {sea} — {nome}  "
                            f"[Normal: {len(self.fila_normal)} | Prio: {len(self.fila_prioritaria)}]",
                            "ts"
                        )
                        conn.send(f"Senha gerada: {sea} — {nome}".encode("utf-8"))
                    else:
                        conn.send("Comando inválido.".encode("utf-8"))

            # --- Terminal de Atendimento (conexão permanente) ---
            elif tipo == "TA_CONECTAR" and len(partes) == 2:
                id_guiche = partes[1]
                with self.lock:
                    self.tas_conectados[id_guiche] = conn
                self._log(
                    f"Guichê {id_guiche} registrado  "
                    f"[Ativos: {sorted(self.tas_conectados.keys())}]", "ta"
                )

                try:
                    while True:
                        dados = conn.recv(1024)
                        if not dados:
                            break
                        req = dados.decode("utf-8").strip()
                        if req.startswith("TA_SOLICITAR"):
                            self._atender_guiche(conn, id_guiche)
                finally:
                    with self.lock:
                        if id_guiche in self.tas_conectados:
                            del self.tas_conectados[id_guiche]
                    self._log(
                        f"Guichê {id_guiche} desconectado  "
                        f"[Ativos: {sorted(self.tas_conectados.keys())}]", "ta"
                    )
                return

            # --- Terminal de Visualização (conexão permanente) ---
            elif tipo == "TV":
                with self.lock:
                    self.tvs_conectadas.append(conn)
                self._log(
                    f"TV conectada: {addr}  [TVs ativas: {len(self.tvs_conectadas)}]", "tv"
                )
                try:
                    while True:
                        dados = conn.recv(1024)
                        if not dados:
                            break
                finally:
                    with self.lock:
                        if conn in self.tvs_conectadas:
                            self.tvs_conectadas.remove(conn)
                    self._log(
                        f"TV desconectada: {addr}  [TVs ativas: {len(self.tvs_conectadas)}]", "tv"
                    )
                return

            else:
                conn.send("Mensagem não reconhecida.".encode("utf-8"))

        except Exception as e:
            self._log(f"Erro com cliente {addr}: {e}", "erro")
        finally:
            conn.close()


# ---------------------------------------------------------------------------
# Interface gráfica
# ---------------------------------------------------------------------------

class AppServidor:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("SRV — Servidor SASE")
        self.root.geometry("640x580")
        self.root.configure(bg=COR_FUNDO)
        self.root.resizable(True, True)
        self.root.minsize(500, 440)

        self._fila_ui = queue.Queue()
        self._ts_lancados = 0
        self._ta_lancados = 0
        self._build_ui()

        self.servidor = ServidorSASE(log_fn=self._enfileirar_log)
        threading.Thread(target=self._loop_servidor, daemon=True).start()

        self._poll_queue()
        self.root.mainloop()

    def _build_ui(self):
        # --- Cabeçalho ---
        frame_header = tk.Frame(self.root, bg=COR_PAINEL)
        frame_header.pack(fill="x")

        tk.Label(
            frame_header, text="SERVIDOR SASE",
            bg=COR_PAINEL, fg=COR_TEXTO,
            font=("Segoe UI", 14, "bold")
        ).pack(side="left", padx=20, pady=12)

        # Botão relatório no cabeçalho
        tk.Button(
            frame_header, text="Gerar Relatorio",
            bg="#8e44ad", fg="white",
            font=("Segoe UI", 9, "bold"),
            relief="flat", cursor="hand2",
            padx=12, pady=4,
            command=self._abrir_relatorio,
            activebackground="#6c3483", activeforeground="white",
        ).pack(side="right", padx=(8, 20), pady=8)

        self.lbl_status = tk.Label(
            frame_header, text="● Iniciando...",
            bg=COR_PAINEL, fg="#f39c12",
            font=("Segoe UI", 9)
        )
        self.lbl_status.pack(side="right", padx=8)

        # --- Lançador de módulos ---
        frame_modulos = tk.Frame(self.root, bg="#0d1b2e")
        frame_modulos.pack(fill="x", padx=18, pady=(8, 0))

        tk.Label(
            frame_modulos, text="MÓDULOS:",
            bg="#0d1b2e", fg="#5d6d7e",
            font=("Segoe UI", 8, "bold")
        ).pack(side="left", padx=(10, 12), pady=8)

        for txt, cor, cor_hover, cmd in [
            ("▶  Nova TV", "#4a1568", "#6c3483", self._lancar_tv),
            ("▶  Novo TS", "#0d3a1a", "#1e8449", self._lancar_ts),
            ("▶  Novo TA", "#0d2a40", "#1a5276", self._lancar_ta),
        ]:
            tk.Button(
                frame_modulos, text=txt,
                bg=cor, fg="white",
                font=("Segoe UI", 9, "bold"),
                relief="flat", cursor="hand2",
                padx=14, pady=5,
                command=cmd,
                activebackground=cor_hover, activeforeground="white",
            ).pack(side="left", padx=4, pady=8)

        # --- Contadores ---
        frame_cont = tk.Frame(self.root, bg="#0f3460")
        frame_cont.pack(fill="x", padx=18, pady=(6, 0))

        self.lbl_fila_n  = self._criar_contador(frame_cont, "FILA NORMAL",      "#27ae60")
        self.lbl_fila_p  = self._criar_contador(frame_cont, "FILA PRIORITARIA", "#e67e22")
        self.lbl_guiches = self._criar_contador(frame_cont, "GUICHES ATIVOS",   "#3498db")
        self.lbl_tvs     = self._criar_contador(frame_cont, "TVs ATIVAS",       "#9b59b6")

        # --- Guichês registrados ---
        frame_guiches = tk.Frame(self.root, bg="#0f3460")
        frame_guiches.pack(fill="x", padx=18, pady=(2, 10))

        tk.Label(
            frame_guiches, text="Guiches:",
            bg="#0f3460", fg="#7f8c8d",
            font=("Segoe UI", 8)
        ).pack(side="left", padx=10, pady=4)

        self.lbl_guiches_lista = tk.Label(
            frame_guiches, text="nenhum registrado",
            bg="#0f3460", fg="#3498db",
            font=("Consolas", 9, "bold")
        )
        self.lbl_guiches_lista.pack(side="left", pady=4)

        # --- Log ---
        tk.Label(
            self.root, text="LOG DO SERVIDOR",
            bg=COR_FUNDO, fg="#5d6d7e",
            font=("Segoe UI", 8, "bold")
        ).pack(anchor="w", padx=20)

        self.txt_log = tk.Text(
            self.root,
            bg=COR_LOG, fg=COR_TEXTO,
            font=("Consolas", 9),
            state="disabled",
            relief="flat", bd=0,
            wrap="word",
            highlightthickness=0
        )
        self.txt_log.pack(padx=18, pady=(2, 18), fill="both", expand=True)

        self.txt_log.tag_config("hora",    foreground="#44475a")
        self.txt_log.tag_config("ts",      foreground="#2ecc71")
        self.txt_log.tag_config("ta",      foreground="#3498db")
        self.txt_log.tag_config("tv",      foreground="#9b59b6")
        self.txt_log.tag_config("aviso",   foreground="#f39c12")
        self.txt_log.tag_config("erro",    foreground="#e74c3c")
        self.txt_log.tag_config("sistema", foreground="#7f8c8d")

    def _criar_contador(self, parent, titulo, cor):
        frame = tk.Frame(parent, bg="#0f3460")
        frame.pack(side="left", expand=True, fill="both", padx=6, pady=6)
        tk.Label(
            frame, text=titulo,
            bg="#0f3460", fg="#7f8c8d",
            font=("Segoe UI", 7, "bold")
        ).pack(pady=(6, 0))
        lbl = tk.Label(
            frame, text="0",
            bg="#0f3460", fg=cor,
            font=("Consolas", 26, "bold")
        )
        lbl.pack(pady=(0, 6))
        return lbl

    def _lancar_tv(self):
        tv_path = os.path.normpath(
            os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'clientes', 'tv.py')
        )
        subprocess.Popen([sys.executable, tv_path])
        self._enfileirar_log("Nova TV iniciada.", "tv")

    def _lancar_ts(self):
        ts_path = os.path.normpath(
            os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'clientes', 'ts.py')
        )
        self._ts_lancados += 1
        subprocess.Popen([sys.executable, ts_path])
        self._enfileirar_log(f"Novo TS iniciado (total lançados: {self._ts_lancados}).", "ts")

    def _lancar_ta(self):
        ta_path = os.path.normpath(
            os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'clientes', 'ta.py')
        )
        self._ta_lancados += 1
        subprocess.Popen([sys.executable, ta_path, f'--guiche={self._ta_lancados}'])
        self._enfileirar_log(f"Novo TA iniciado — Guichê {self._ta_lancados}.", "ta")

    def _abrir_relatorio(self):
        with self.servidor.lock:
            historico = list(self.servidor.historico_atendimentos)
            fn        = len(self.servidor.fila_normal)
            fp        = len(self.servidor.fila_prioritaria)
            guiches   = sorted(self.servidor.tas_conectados.keys())

        log_txt = self.txt_log.get("1.0", "end")
        titulo  = "RELATORIO DE ATENDIMENTOS - SASE (todos os guiches)"

        # Extras: fila restante + stats de sessão
        extras = {}
        extras["Fila Normal restante"]       = fn
        extras["Fila Prioritaria restante"]  = fp
        extras["Total aguardando atendimento"] = fn + fp
        extras["Guiches ativos"]             = ", ".join(guiches) if guiches else "nenhum"
        extras.update(relatorio._stats_sessao(historico))

        texto = relatorio.gerar_txt(titulo, historico, com_guiche=True, extras=extras)

        def salvar_pdf(janela_pai):
            path = filedialog.asksaveasfilename(
                defaultextension=".pdf",
                filetypes=[("PDF", "*.pdf")],
                initialfile="relatorio_sase_{}.pdf".format(
                    datetime.now().strftime("%Y%m%d_%H%M%S")
                ),
                parent=janela_pai,
            )
            if not path:
                return
            ok, msg = relatorio.gerar_pdf(
                path, titulo, historico,
                log_texto=log_txt, com_guiche=True, extras=extras,
            )
            if ok:
                tk.messagebox.showinfo("PDF salvo", "Arquivo salvo em:\n{}".format(path), parent=janela_pai)
            else:
                tk.messagebox.showerror("Erro ao gerar PDF", msg, parent=janela_pai)

        _abrir_janela_relatorio(
            self.root,
            "Relatorio de Atendimentos - SRV",
            texto,
            fn_salvar_pdf=salvar_pdf,
        )

    def _enfileirar_log(self, mensagem, tag="sistema"):
        hora = datetime.now().strftime("%H:%M:%S")
        self._fila_ui.put(("log", hora, mensagem, tag))

    def _poll_queue(self):
        while not self._fila_ui.empty():
            evento = self._fila_ui.get()

            if evento[0] == "log":
                _, hora, msg, tag = evento
                self.txt_log.config(state="normal")
                self.txt_log.insert("end", f"[{hora}] ", "hora")
                self.txt_log.insert("end", f"{msg}\n", tag)
                self.txt_log.see("end")
                self.txt_log.config(state="disabled")

            elif evento[0] == "status":
                _, texto, cor = evento
                self.lbl_status.config(text=texto, fg=cor)

        if hasattr(self, "servidor"):
            with self.servidor.lock:
                fn      = len(self.servidor.fila_normal)
                fp      = len(self.servidor.fila_prioritaria)
                tvs     = len(self.servidor.tvs_conectadas)
                guiches = sorted(self.servidor.tas_conectados.keys())

            self.lbl_fila_n.config(text=str(fn))
            self.lbl_fila_p.config(text=str(fp))
            self.lbl_tvs.config(text=str(tvs))
            self.lbl_guiches.config(text=str(len(guiches)))

            if guiches:
                texto = "  ".join(f"Guiche {g}" for g in guiches)
            else:
                texto = "nenhum registrado"
            self.lbl_guiches_lista.config(text=texto)

        self.root.after(300, self._poll_queue)

    def _loop_servidor(self):
        try:
            srv_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            srv_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            srv_socket.bind((conexao.HOST, conexao.PORTA_SRV))
            srv_socket.listen(10)

            self._fila_ui.put(("status", f"● Online  —  {conexao.HOST}:{conexao.PORTA_SRV}", "#2ecc71"))
            self._enfileirar_log(f"Servidor iniciado em {conexao.HOST}:{conexao.PORTA_SRV}", "sistema")
            self._enfileirar_log("Aguardando conexoes de TS, TA e TV...", "sistema")

            while True:
                conn, addr = srv_socket.accept()
                threading.Thread(
                    target=self.servidor.handle_client,
                    args=(conn, addr),
                    daemon=True
                ).start()

        except OSError as e:
            self._fila_ui.put(("status", f"● Erro: {e}", "#e74c3c"))
            self._enfileirar_log(f"Erro ao iniciar: {e}", "erro")
        except Exception as e:
            self._enfileirar_log(f"Erro inesperado: {e}", "erro")


if __name__ == "__main__":
    AppServidor()
