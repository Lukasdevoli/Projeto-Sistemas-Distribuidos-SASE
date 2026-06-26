"""
================================================================================
ARQUIVO: servidor/srv.py
PROPÓSITO: Servidor central (SRV) do SASE — Sistema de Atendimento por Senha
           Eletrônica.
================================================================================

O QUE FAZ
---------
Este é o nó central da arquitetura. Ele mantém o ESTADO GLOBAL do atendimento:
  - As duas filas de senhas (Normal e Prioritária);
  - Os contadores sequenciais de senha (N1, N2, ..., P1, P2, ...);
  - O registro dos guichês (TA) atualmente conectados;
  - A lista dos painéis de visualização (TV) conectados;
  - O histórico completo de atendimentos (para o relatório).

Todos os demais módulos do sistema são CLIENTES deste servidor:
  - TS (Terminal de Senhas)      → gera novas senhas para entrar na fila;
  - TA (Terminal de Atendimento) → solicita a próxima senha da fila (guichê);
  - TV (Terminal de Visualização)→ recebe broadcasts de "chamada de senha".

COMO USA
--------
Executar diretamente: `python3 srv.py`. A classe `AppServidor` sobe a interface
gráfica (tkinter) e, em paralelo, uma thread dedicada (`_loop_servidor`) abre o
socket TCP e fica aceitando conexões. Cada conexão aceita ganha sua própria
thread (modelo "thread por conexão"), tratada por `ServidorSASE.handle_client`.

PROTOCOLO DE COMUNICAÇÃO (TCP, mensagens em texto UTF-8, campos separados por '|')
--------------------------------------------------------------------------------
Toda mensagem que chega ao servidor começa por um "tipo" que identifica o cliente:

  TS  → SRV : "TS|GERAR_N"  ou  "TS|GERAR_P"
              Conexão CURTA: o TS conecta, pede uma senha, recebe a confirmação
              e a conexão é encerrada logo em seguida.

  TA  → SRV : "TA_CONECTAR|<id>"      (handshake inicial, registra o guichê)
              "TA_SOLICITAR|<id>"     (pedido de próxima senha, repetível)
              Conexão PERSISTENTE: o socket permanece aberto enquanto o guichê
              estiver ativo; o servidor escuta solicitações em laço.

  TV  → SRV : "TV|CONECTAR"
              Conexão PERSISTENTE: o painel apenas escuta; não envia comandos.
              Serve para o servidor empurrar (push) as chamadas de senha.

  SRV → TV  : broadcast "Guichê X chama: N1 — Nome"
              Enviado a TODAS as TVs conectadas sempre que um guichê chama uma
              senha, replicando no painel público o que aparece no guichê.

ENQUADRAMENTO DE MENSAGENS (delimitador '\n')
--------------------------------------------------------------------------------
TCP é um FLUXO de bytes, sem fronteira de mensagem: um único recv() pode trazer
duas mensagens coladas ou apenas um pedaço de uma. Para resolver isso, TODA
mensagem do protocolo termina com '\n'. O lado receptor acumula os bytes em um
buffer e processa uma linha por vez (buffer.split('\n', 1)), garantindo que cada
mensagem seja remontada/separada corretamente.

Disciplina: Sistemas Distribuídos — IFCE Campus Crato
================================================================================
"""

# ── Imports ──────────────────────────────────────────────────────────────────
import tkinter as tk                          # Toolkit gráfico padrão da std lib
from tkinter import filedialog, messagebox    # Diálogos de salvar arquivo / alertas
import socket                                  # Sockets TCP (núcleo da comunicação)
import threading                               # Concorrência: 1 thread por conexão
import queue                                   # Fila thread-safe GUI ↔ rede
import subprocess                              # Lançar TS/TA/TV como processos filhos
import sys
import os
from datetime import datetime                  # Timestamps de cada evento/SEA

import random                                  # Sorteio de nome fictício por senha

# Permite importar o pacote `utils` da raiz do projeto, mesmo executando este
# arquivo de dentro da pasta servidor/ (sobe um nível e adiciona ao sys.path).
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from utils import conexao, relatorio          # conexao: HOST/PORTA; relatorio: TXT/PDF

# ── Dados de domínio ─────────────────────────────────────────────────────────
# NOMES: lista de "pacientes" fictícios usada para dar realismo à simulação.
# Cada senha gerada pelo TS recebe um nome sorteado desta lista (random.choice),
# de modo que a chamada exibida no guichê e na TV mostre algo como
# "Guichê 1 chama: N1 — Pelé", em vez de apenas o código da senha.
# O conteúdo é a lista dos "100 maiores brasileiros de todos os tempos"
# (enquete SBT/BBC, 2012) — escolha puramente ilustrativa, sem efeito na lógica.
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

# ── Paleta da interface ──────────────────────────────────────────────────────
# Tema escuro unificado entre todos os módulos do SASE. Centralizar as cores em
# constantes evita "números mágicos" hexadecimais espalhados pelo build da UI e
# garante consistência visual entre SRV, TS, TA e TV.
COR_FUNDO  = "#1a1a2e"   # Fundo geral das janelas
COR_PAINEL = "#16213e"   # Faixas/cabeçalhos destacados
COR_LOG    = "#0d0d1a"   # Fundo da área de log (quase preto, p/ contraste)
COR_TEXTO  = "#ecf0f1"   # Texto claro padrão


# ── Janela de relatório ──────────────────────────────────────────────────────

def _abrir_janela_relatorio(parent, titulo, texto, fn_salvar_pdf=None):
    """Abre uma janela secundária (Toplevel) exibindo o relatório de atendimentos.

    Mostra o texto já formatado em uma área rolável e oferece três ações:
    salvar como PDF (delegada ao chamador), salvar como .txt e fechar. É um
    helper puramente de apresentação — não toca no estado do servidor.

    Args:
        parent (tk.Misc): Janela-mãe à qual o Toplevel fica vinculado.
        titulo (str): Título exibido na barra da janela.
        texto (str): Conteúdo já renderizado do relatório.
        fn_salvar_pdf (callable, optional): Callback chamado ao clicar em
            "Salvar PDF", recebendo a própria janela como argumento. Se None,
            o botão fica inerte.

    Returns:
        None
    """
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

    # Closure: serializa o texto do relatório para um arquivo .txt escolhido
    # pelo usuário. Fica aninhada porque depende de `texto` e `janela` locais.
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


# ── Lógica central do servidor ───────────────────────────────────────────────

class ServidorSASE:
    """Núcleo de regra de negócio e estado compartilhado do SRV.

    Responsabilidade
    ----------------
    Concentra TODO o estado mutável do atendimento (filas, contadores,
    clientes conectados, histórico) e as operações que o alteram. A classe é
    deliberadamente separada da interface gráfica (`AppServidor`): a GUI apenas
    lança esta classe e lê seu estado para exibir contadores, seguindo uma
    separação de responsabilidades no estilo "model" (lógica) vs. "view" (UI).

    Concorrência
    ------------
    Suas instâncias são acessadas SIMULTANEAMENTE por várias threads (uma por
    conexão TCP, criadas em `AppServidor._loop_servidor`). Por isso, toda
    leitura/escrita do estado compartilhado é protegida por `self.lock`. O envio
    de mensagens pela rede, porém, é feito FORA do lock (ver `_broadcast_tvs`).

    Relação com outros módulos
    --------------------------
    Recebe conexões dos clientes TS, TA e TV e responde conforme o protocolo
    descrito no cabeçalho do módulo. Não importa nem instancia esses clientes —
    apenas reage às mensagens que eles enviam.
    """

    def __init__(self, log_fn):
        """Inicializa o estado do servidor.

        Args:
            log_fn (callable): Função de log (msg, tag) usada para registrar
                eventos. Injetada pela GUI (`AppServidor._enfileirar_log`), o
                que desacopla a lógica do mecanismo de exibição.
        """
        # Função de log injetada (inversão de dependência: a lógica não conhece
        # a GUI, apenas chama este callback).
        self._log = log_fn

        # ── Estado das filas e dos contadores de senha ──────────────────────
        self.fila_normal = []           # FIFO de senhas Normais aguardando ("N…")
        self.fila_prioritaria = []      # FIFO de senhas Prioritárias aguardando ("P…")
        self.proximo_N = 1              # Próximo número Normal a emitir (N1, N2, …)
        self.proximo_P = 1              # Próximo número Prioritário a emitir (P1, P2, …)
        # Contador de Normais servidas em sequência; é o que viabiliza a regra
        # de prioridade "N, N, P" em _proximo_da_fila(). Zera ao servir uma P.
        self.normals_consecutivos = 0

        # Histórico de atendimentos: lista de dicts
        # [{ordem, senha, nome, tipo, guiche, hora}], base para o relatório.
        self.historico_atendimentos = []
        self._contador_ordem = 0        # Ordem global de chamada (1,2,3,…)

        # Mapa senha → nome fictício, atribuído no momento da geração e
        # consumido (pop) quando a senha é chamada.
        self._nomes = {}

        # Guichês de atendimento registrados: {id_guiche(str): socket}.
        self.tas_conectados = {}
        # Painéis de visualização conectados (alvos do broadcast): [socket, …].
        self.tvs_conectadas = []

        # Lock único que serializa o acesso a TODO o estado acima. Necessário
        # porque múltiplas threads de conexão podem, ao mesmo tempo, alterar as
        # filas, os contadores e as listas de clientes — sem ele haveria
        # condições de corrida (ex.: dois guichês recebendo a mesma senha, ou
        # contadores corrompidos).
        self.lock = threading.Lock()

    def _proximo_da_fila(self):
        """Seleciona a próxima senha a ser chamada aplicando a regra de prioridade.

        Regra (Projeto_SD.pdf, seção 2.1 item 4c):
            'Para cada duas SEAs do tipo N informadas, a próxima SEA deverá ser
            obrigatoriamente do tipo P, se houver.'

        Em outras palavras, o padrão ideal de chamada é: N, N, P, N, N, P, …
        A escolha segue esta ordem de decisão:
          1. Se já foram servidas 2 Normais seguidas E existe Prioritária na
             fila → serve a Prioritária (cumpre a cota obrigatória) e zera o
             contador de consecutivas.
          2. Senão, se há Normal disponível → serve a Normal e incrementa o
             contador de consecutivas.
          3. Senão, se há Prioritária → serve a Prioritária (caso em que não
             havia Normais para servir) e zera o contador.
          4. Senão, ambas as filas estão vazias → retorna None.

        Casos de borda cobertos pela ordem acima:
          - 2 Normais servidas mas SEM Prioritária disponível: cai no ramo 2 e
            continua servindo Normais (a cota só se aplica "se houver" P).
          - Sem Normais e só Prioritárias: cai no ramo 3, servindo P direto.

        Pré-condição: deve ser chamado com `self.lock` já adquirido, pois lê e
        modifica filas e contadores compartilhados.

        Returns:
            str | None: O código da senha escolhida (ex.: "N3", "P1"), ou None
            se não há ninguém aguardando.
        """
        # Cota de prioridade cumprida: 2 Normais seguidas → vez de uma P.
        if self.normals_consecutivos >= 2 and self.fila_prioritaria:
            sea = self.fila_prioritaria.pop(0)
            self.normals_consecutivos = 0
        # Fluxo comum: ainda dentro da cota de 2 Normais → serve Normal.
        elif self.fila_normal:
            sea = self.fila_normal.pop(0)
            self.normals_consecutivos += 1
        # Só restam Prioritárias → serve P (não há Normal para contar).
        elif self.fila_prioritaria:
            sea = self.fila_prioritaria.pop(0)
            self.normals_consecutivos = 0
        # Ambas as filas vazias.
        else:
            sea = None
        return sea

    def _broadcast_tvs(self, mensagem, tvs_snapshot):
        """Empurra (push) uma mensagem de chamada para todos os painéis TV.

        Implementa o passo "SRV → TV" do protocolo: replica nos painéis públicos
        a senha que acabou de ser chamada em um guichê.

        IMPORTANTE — por que executa FORA do lock:
            Operações de rede (`socket.send`) podem BLOQUEAR (buffer cheio, TV
            lenta, conexão pendente). Se este envio fosse feito segurando
            `self.lock`, todas as outras threads ficariam paradas esperando o
            lock enquanto uma única TV lenta trava o servidor inteiro — e, no
            limite, abre porta para deadlock. Por isso o chamador tira um
            SNAPSHOT da lista de TVs sob o lock e o passa aqui (`tvs_snapshot`);
            o envio em si ocorre sem lock. O lock só é readquirido por um
            instante curtíssimo no final, apenas para remover as TVs que caíram.

        Args:
            mensagem (str): Texto a transmitir (ex.: "Guichê 1 chama: N1 — Pelé").
            tvs_snapshot (list[socket]): Cópia da lista de sockets de TV feita
                pelo chamador enquanto segurava o lock.

        Returns:
            None
        """
        # Coleta as TVs cujo envio falhou (provavelmente desconectadas) para
        # removê-las depois, sem mutar a lista enquanto iteramos sobre ela.
        desconectadas = []
        for tv_sock in tvs_snapshot:
            try:
                # sendall garante o envio completo; '\n' delimita a mensagem.
                tv_sock.sendall((mensagem + "\n").encode("utf-8"))
            except Exception:
                # Falha de envio = TV caiu; marca para remoção (não interrompe
                # o broadcast para as demais).
                desconectadas.append(tv_sock)
        # Limpeza: agora sim, brevemente sob o lock, retira as TVs mortas da
        # lista oficial. Reverifica a presença pois outra thread pode tê-las
        # removido nesse meio-tempo.
        if desconectadas:
            with self.lock:
                for tv in desconectadas:
                    if tv in self.tvs_conectadas:
                        self.tvs_conectadas.remove(tv)

    def _atender_guiche(self, conn, id_guiche):
        """Atende um pedido "TA_SOLICITAR" de um guichê: chama a próxima senha.

        Fluxo: escolhe a próxima senha pela regra de prioridade, registra o
        atendimento no histórico, responde ao guichê e faz broadcast da chamada
        para todas as TVs.

        Estratégia de bloqueio (padrão "lock curto, I/O longo"):
            A seção crítica (escolha da senha + atualização de histórico + cópia
            do snapshot de TVs) roda DENTRO do lock. Os envios pela rede ao
            guichê e às TVs acontecem DEPOIS, já FORA do lock — pelos mesmos
            motivos de não bloquear o servidor descritos em `_broadcast_tvs`.

        Args:
            conn (socket.socket): Socket persistente do guichê solicitante.
            id_guiche (str): Identificador do guichê (ex.: "1").

        Returns:
            None
        """
        # ── Seção crítica: muta estado compartilhado sob o lock ─────────────
        with self.lock:
            sea = self._proximo_da_fila()
            if sea:
                # Consome o nome associado à senha (pop: a senha sai de cena).
                nome = self._nomes.pop(sea, "")
                self._contador_ordem += 1
                # Grava o atendimento para o relatório posterior.
                self.historico_atendimentos.append({
                    "ordem":  self._contador_ordem,
                    "senha":  sea,
                    "nome":   nome,
                    # Tipo derivado do prefixo do código da senha ("P…"/"N…").
                    "tipo":   "Prioritario" if sea.startswith("P") else "Normal",
                    "guiche": id_guiche,
                    "hora":   datetime.now(),
                })
                resposta = f"Guichê {id_guiche} chama: {sea} — {nome}" if nome else f"Guichê {id_guiche} chama: {sea}"
                # Snapshot das TVs tirado AINDA sob o lock, para broadcast seguro
                # fora dele.
                tvs_snapshot = list(self.tvs_conectadas)
            else:
                resposta = "Fila vazia. Nenhuma senha aguardando atendimento."
                tvs_snapshot = []

        # ── I/O de rede: já fora do lock ────────────────────────────────────
        # Responde ao guichê solicitante (passo SRV → TA).
        try:
            # sendall garante o envio completo; '\n' delimita a mensagem.
            conn.sendall((resposta + "\n").encode("utf-8"))
        except Exception:
            # Guichê caiu durante o envio; aborta. A remoção do registro é feita
            # pelo laço de handle_client ao detectar a desconexão.
            return

        if sea:
            self._log(f"SEA enviada ao Guichê {id_guiche} e TVs: {sea}", "ta")
            # Replica a chamada nos painéis públicos (passo SRV → TV).
            self._broadcast_tvs(resposta, tvs_snapshot)
        else:
            self._log(f"Guichê {id_guiche} solicitou senha — fila vazia.", "aviso")

    def handle_client(self, conn, addr):
        """Despachador de protocolo: trata UMA conexão de cliente do início ao fim.

        É o ponto de entrada executado em uma thread dedicada por conexão
        (criada em `AppServidor._loop_servidor`). Lê a primeira mensagem, usa o
        "tipo" (primeiro campo) para decidir como tratar o cliente e segue um de
        três fluxos, conforme o protocolo do módulo:

          - "TS"          → conexão CURTA: gera uma senha (Normal ou Prioritária),
                            responde e encerra (cai no `finally` que fecha o socket).
          - "TA_CONECTAR" → conexão PERSISTENTE: registra o guichê e entra em laço
                            atendendo cada "TA_SOLICITAR" até a desconexão.
          - "TV"          → conexão PERSISTENTE: registra o painel e entra em laço
                            apenas para detectar a queda da conexão (o painel só
                            recebe broadcasts, não envia comandos úteis).
          - qualquer outro→ responde "Mensagem não reconhecida.".

        Args:
            conn (socket.socket): Socket conectado ao cliente.
            addr (tuple): Endereço (ip, porta) do cliente, usado em logs.

        Returns:
            None

        Raises:
            Exception: Qualquer erro de I/O/decodificação é capturado, logado
                como "erro" e NÃO propagado — a thread encerra limpa e o socket
                é fechado no `finally`.
        """
        tipo = None
        partes = []
        try:
            # Lê a mensagem inicial (até 1024 bytes). Como o protocolo enquadra
            # mensagens com '\n', isola a PRIMEIRA linha completa e guarda o que
            # sobrar em `resto` (pode conter o início da próxima mensagem se duas
            # vierem coaladas no mesmo segmento TCP). Depois divide nos campos do
            # protocolo (separador "|"). O primeiro campo identifica o cliente.
            dados = conn.recv(1024).decode("utf-8")
            linha, _sep, resto = dados.partition("\n")
            partes = linha.strip().split("|")
            tipo = partes[0]

            # ── Caso "TS": Terminal de Senhas (conexão curta) ───────────────
            # Formato esperado: "TS|GERAR_N" ou "TS|GERAR_P".
            if tipo == "TS" and len(partes) == 2:
                comando = partes[1]
                # Geração de senha muta contadores/filas → seção crítica.
                with self.lock:
                    if comando == "GERAR_N":
                        # Emite a próxima senha Normal (N1, N2, …), associa um
                        # nome fictício e a coloca no fim da fila Normal.
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
                        conn.sendall(f"Senha gerada: {sea} — {nome}\n".encode("utf-8"))
                    elif comando == "GERAR_P":
                        # Emite a próxima senha Prioritária (P1, P2, …), associa
                        # um nome fictício e a coloca no fim da fila Prioritária.
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
                        conn.sendall(f"Senha gerada: {sea} — {nome}\n".encode("utf-8"))
                    else:
                        # Comando após "TS|" não reconhecido.
                        conn.sendall("Comando inválido.\n".encode("utf-8"))

            # ── Caso "TA_CONECTAR": Terminal de Atendimento (persistente) ───
            # Formato do handshake: "TA_CONECTAR|<id>". Depois, o guichê passa a
            # enviar "TA_SOLICITAR|<id>" repetidamente na MESMA conexão.
            elif tipo == "TA_CONECTAR" and len(partes) == 2:
                id_guiche = partes[1]
                # Registra o socket do guichê no mapa de ativos (seção crítica).
                with self.lock:
                    self.tas_conectados[id_guiche] = conn
                self._log(
                    f"Guichê {id_guiche} registrado  "
                    f"[Ativos: {sorted(self.tas_conectados.keys())}]", "ta"
                )

                try:
                    # Laço de serviço da conexão persistente: bloqueia em recv()
                    # até chegar um pedido ou a conexão cair. Acumula os bytes em
                    # `buffer` e processa UMA linha por vez (enquadramento '\n'),
                    # de modo que pedidos coalescidos pelo TCP sejam separados
                    # corretamente e pedidos fragmentados sejam remontados.
                    buffer = resto  # sobra da leitura inicial (handshake coalado)
                    while True:
                        # Primeiro consome o que já está no buffer.
                        while "\n" in buffer:
                            req, buffer = buffer.split("\n", 1)
                            req = req.strip()
                            # Cada "TA_SOLICITAR" dispara a próxima senha.
                            if req.startswith("TA_SOLICITAR"):
                                self._atender_guiche(conn, id_guiche)
                        dados = conn.recv(1024)
                        # recv vazio (b"") = o cliente fechou a conexão → sai.
                        if not dados:
                            break
                        buffer += dados.decode("utf-8")
                finally:
                    # Desregistra o guichê ao sair do laço (queda ou erro),
                    # mantendo o mapa de ativos coerente. Sempre executa.
                    with self.lock:
                        if id_guiche in self.tas_conectados:
                            del self.tas_conectados[id_guiche]
                    self._log(
                        f"Guichê {id_guiche} desconectado  "
                        f"[Ativos: {sorted(self.tas_conectados.keys())}]", "ta"
                    )
                # Retorna aqui para não cair no envio genérico abaixo (o socket é
                # fechado pelo `finally` externo).
                return

            # ── Caso "TV": Terminal de Visualização (persistente) ───────────
            # Formato: "TV|CONECTAR". O painel apenas escuta broadcasts.
            elif tipo == "TV":
                # Adiciona o socket à lista de destinatários de broadcast.
                with self.lock:
                    self.tvs_conectadas.append(conn)
                self._log(
                    f"TV conectada: {addr}  [TVs ativas: {len(self.tvs_conectadas)}]", "tv"
                )
                try:
                    # A TV não envia comandos úteis; este laço existe só para
                    # bloquear até detectar a desconexão (recv vazio).
                    while True:
                        dados = conn.recv(1024)
                        if not dados:
                            break
                finally:
                    # Remove a TV da lista de broadcast ao desconectar.
                    with self.lock:
                        if conn in self.tvs_conectadas:
                            self.tvs_conectadas.remove(conn)
                    self._log(
                        f"TV desconectada: {addr}  [TVs ativas: {len(self.tvs_conectadas)}]", "tv"
                    )
                return

            else:
                # Tipo não previsto pelo protocolo.
                conn.sendall("Mensagem não reconhecida.\n".encode("utf-8"))

        except Exception as e:
            # Blindagem da thread: nenhum erro de um cliente derruba o servidor.
            self._log(f"Erro com cliente {addr}: {e}", "erro")
        finally:
            # Garante o fechamento do socket em TODOS os caminhos (inclusive a
            # conexão curta do TS, que não tem return próprio).
            conn.close()


# ── Interface gráfica ────────────────────────────────────────────────────────

class AppServidor:
    """Camada de apresentação (GUI tkinter) e bootstrap do servidor.

    Responsabilidade
    ----------------
    Monta a janela de monitoramento (status, contadores de filas/guichês/TVs,
    log e botão de relatório), lança os módulos clientes como processos filhos
    e hospeda a thread de rede que efetivamente roda o servidor TCP.

    Modelo de threads (importante)
    ------------------------------
    tkinter NÃO é thread-safe: apenas a thread principal pode tocar widgets.
    Por isso adota-se o padrão produtor/consumidor:
      - As threads de rede (servidor/conexões) PRODUZEM eventos em `_fila_ui`
        (uma `queue.Queue`, thread-safe) via `_enfileirar_log`;
      - A thread principal CONSOME esses eventos em `_poll_queue`, agendado
        periodicamente com `root.after`, e só ela atualiza os widgets.

    Relação com a lógica
    --------------------
    Cria a instância única de `ServidorSASE`, injeta nela seu logger e lê o
    estado dela (sob `servidor.lock`) apenas para exibir contadores.
    """

    def __init__(self):
        """Constrói a janela, instancia o servidor e inicia os laços (rede + UI)."""
        # ── Janela principal ────────────────────────────────────────────────
        self.root = tk.Tk()
        self.root.title("SRV — Servidor SASE")
        self.root.geometry("640x580")
        self.root.configure(bg=COR_FUNDO)
        self.root.resizable(True, True)
        self.root.minsize(500, 440)

        # Canal thread-safe rede → GUI (ver docstring da classe).
        self._fila_ui = queue.Queue()
        # Contadores apenas para rotular os processos clientes lançados (o TA
        # usa o seu valor como número de guichê, ex.: --guiche=1).
        self._ts_lancados = 0
        self._ta_lancados = 0
        self._build_ui()

        # Instancia a lógica, injetando o logger (callback que enfileira na UI).
        self.servidor = ServidorSASE(log_fn=self._enfileirar_log)
        # Sobe o servidor TCP em thread separada (daemon: morre junto com a GUI),
        # para não bloquear o mainloop.
        threading.Thread(target=self._loop_servidor, daemon=True).start()

        # Inicia o consumo periódico da fila de eventos e entra no laço da GUI.
        self._poll_queue()
        self.root.mainloop()

    def _build_ui(self):
        """Monta todos os widgets da janela (layout estático, sem lógica de rede).

        Seções, de cima para baixo: cabeçalho (título + status + botão de
        relatório), lançador de módulos, painel de contadores, lista de guichês
        ativos e a área de log com suas tags de cor.
        """
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

        # Tags de cor do log: cada categoria de evento (TS, TA, TV, aviso, erro,
        # sistema) recebe uma cor própria, facilitando a leitura visual do fluxo.
        self.txt_log.tag_config("hora",    foreground="#44475a")
        self.txt_log.tag_config("ts",      foreground="#2ecc71")
        self.txt_log.tag_config("ta",      foreground="#3498db")
        self.txt_log.tag_config("tv",      foreground="#9b59b6")
        self.txt_log.tag_config("aviso",   foreground="#f39c12")
        self.txt_log.tag_config("erro",    foreground="#e74c3c")
        self.txt_log.tag_config("sistema", foreground="#7f8c8d")

    def _criar_contador(self, parent, titulo, cor):
        """Cria um cartão de contador (título + número grande) no painel.

        Args:
            parent (tk.Widget): Container onde o cartão será empacotado.
            titulo (str): Rótulo do contador (ex.: "FILA NORMAL").
            cor (str): Cor hex do número exibido.

        Returns:
            tk.Label: O Label do número, guardado pelo chamador para atualizá-lo
            depois em `_poll_queue`.
        """
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
        """Inicia um novo painel de visualização (clientes/tv.py) como processo filho.

        Usa `sys.executable` para reutilizar o mesmo interpretador Python em uso,
        garantindo portabilidade independentemente do venv/sistema.
        """
        tv_path = os.path.normpath(
            os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'clientes', 'tv.py')
        )
        subprocess.Popen([sys.executable, tv_path])
        self._enfileirar_log("Nova TV iniciada.", "tv")

    def _lancar_ts(self):
        """Inicia um novo Terminal de Senhas (clientes/ts.py) como processo filho."""
        ts_path = os.path.normpath(
            os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'clientes', 'ts.py')
        )
        self._ts_lancados += 1
        subprocess.Popen([sys.executable, ts_path])
        self._enfileirar_log(f"Novo TS iniciado (total lançados: {self._ts_lancados}).", "ts")

    def _lancar_ta(self):
        """Inicia um novo Terminal de Atendimento (clientes/ta.py) como processo filho.

        Cada TA lançado recebe um número de guichê sequencial via argumento de
        linha de comando (`--guiche=N`), de modo que o primeiro vira "Guichê 1",
        o segundo "Guichê 2", etc. Esse id é o mesmo usado no handshake
        "TA_CONECTAR|<id>" do protocolo.
        """
        ta_path = os.path.normpath(
            os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'clientes', 'ta.py')
        )
        self._ta_lancados += 1
        subprocess.Popen([sys.executable, ta_path, f'--guiche={self._ta_lancados}'])
        self._enfileirar_log(f"Novo TA iniciado — Guichê {self._ta_lancados}.", "ta")

    def _abrir_relatorio(self):
        """Gera o relatório consolidado de atendimentos e abre a janela de visualização.

        Tira uma cópia consistente do estado do servidor (sob `servidor.lock`),
        monta estatísticas extras de sessão via `utils.relatorio` e abre a
        janela com opções de exportação em .txt e PDF.
        """
        # Snapshot coerente do estado sob o lock: copia o histórico e lê os
        # tamanhos das filas e os guichês ativos de uma só vez, evitando que a
        # rede altere esses dados durante a montagem do relatório.
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

        # Closure de exportação para PDF: capturada pela janela de relatório e
        # acionada pelo botão "Salvar PDF". Depende de historico/titulo/extras
        # locais, por isso é aninhada.
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
                messagebox.showinfo("PDF salvo", "Arquivo salvo em:\n{}".format(path), parent=janela_pai)
            else:
                messagebox.showerror("Erro ao gerar PDF", msg, parent=janela_pai)

        _abrir_janela_relatorio(
            self.root,
            "Relatorio de Atendimentos - SRV",
            texto,
            fn_salvar_pdf=salvar_pdf,
        )

    def _enfileirar_log(self, mensagem, tag="sistema"):
        """Enfileira um evento de log para a thread da GUI exibir (thread-safe).

        É este o callback injetado em `ServidorSASE` como `log_fn`. Pode ser
        chamado por QUALQUER thread de rede; por isso ele apenas deposita o
        evento na `queue.Queue` (que é thread-safe) em vez de tocar widgets
        diretamente — quem desenha é `_poll_queue`, na thread principal.

        Args:
            mensagem (str): Texto a registrar.
            tag (str): Categoria/cor do log (ts, ta, tv, aviso, erro, sistema).
        """
        hora = datetime.now().strftime("%H:%M:%S")
        self._fila_ui.put(("log", hora, mensagem, tag))

    def _poll_queue(self):
        """Consome a fila de eventos e atualiza os widgets (roda na thread da GUI).

        É o lado CONSUMIDOR do padrão produtor/consumidor: drena todos os
        eventos pendentes em `_fila_ui` (logs e mudanças de status), depois lê o
        estado atual do servidor para atualizar os contadores e a lista de
        guichês, e por fim se reagenda via `root.after` (~300 ms), formando um
        laço de atualização contínuo sem bloquear o mainloop.
        """
        # Drena tudo que as threads de rede produziram desde a última passagem.
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

        # Atualização dos contadores: lê o estado do servidor sob o lock (cópia
        # rápida dos números) e só então mexe nos widgets, já fora do lock.
        # O guard hasattr evita corrida na inicialização, caso o primeiro poll
        # dispare antes de `self.servidor` existir.
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

        # Reagenda a si mesmo: laço de atualização da UI a cada ~300 ms.
        self.root.after(300, self._poll_queue)

    def _loop_servidor(self):
        """Laço principal do servidor TCP — modelo "thread por conexão".

        Roda em uma thread daemon dedicada (criada no __init__). Abre o socket
        de escuta e fica em accept() permanente; para CADA conexão aceita, cria
        uma nova thread que executa `ServidorSASE.handle_client`. Assim, vários
        clientes (TS, TA, TV) são atendidos concorrentemente sem que um bloqueie
        o outro.

        Tratamento de erros: falhas ao abrir o socket (ex.: porta já em uso)
        viram status de erro na UI; o método nunca propaga exceção (a thread
        encerra de forma controlada).
        """
        try:
            # Cria o socket TCP/IPv4 de escuta.
            srv_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            # SO_REUSEADDR: permite reabrir a porta imediatamente após um
            # reinício, sem esperar o estado TIME_WAIT do TCP liberá-la.
            srv_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            # Vincula ao HOST/PORTA centralizados em utils.conexao (um único
            # ponto de configuração para todo o sistema).
            srv_socket.bind((conexao.HOST, conexao.PORTA_SRV))
            # backlog=10: até 10 conexões podem ficar na fila do SO aguardando
            # accept().
            srv_socket.listen(10)

            self._fila_ui.put(("status", f"● Online  —  {conexao.HOST}:{conexao.PORTA_SRV}", "#2ecc71"))
            self._enfileirar_log(f"Servidor iniciado em {conexao.HOST}:{conexao.PORTA_SRV}", "sistema")
            self._enfileirar_log("Aguardando conexoes de TS, TA e TV...", "sistema")

            # Laço de aceitação infinito.
            while True:
                # Bloqueia até um cliente conectar.
                conn, addr = srv_socket.accept()
                # Despacha a conexão para sua própria thread daemon, deixando o
                # accept() livre para atender o próximo cliente imediatamente.
                threading.Thread(
                    target=self.servidor.handle_client,
                    args=(conn, addr),
                    daemon=True
                ).start()

        except OSError as e:
            # Tipicamente "address already in use" — porta ocupada por outra
            # instância do servidor.
            self._fila_ui.put(("status", f"● Erro: {e}", "#e74c3c"))
            self._enfileirar_log(f"Erro ao iniciar: {e}", "erro")
        except Exception as e:
            self._enfileirar_log(f"Erro inesperado: {e}", "erro")


# ── Ponto de entrada ─────────────────────────────────────────────────────────
# Só executa quando rodado diretamente (não em import). Instancia a GUI, que
# por sua vez sobe o servidor e bloqueia no mainloop do tkinter.
if __name__ == "__main__":
    AppServidor()
