# SASE — Sistema de Atendimento por Senha Eletrônica

> IF Ceará, Campus Crato — Disciplina: Sistemas Distribuídos

## Início Rápido

```bash
pip install -r requirements.txt
python3 iniciar.py
```

O comando `iniciar.py` abre as quatro janelas do sistema (SRV, TV, TS, TA).

## Pré-requisitos

<details>
<summary>Detalhes de instalação (Python, espeak-ng, tk)</summary>

| Dependência | Versão | Para que serve | Instalação |
|-------------|--------|----------------|------------|
| Python | 3.8+ | Interpretador | [python.org/downloads](https://www.python.org/downloads/) |
| Tkinter (tk) | — | Interface gráfica dos módulos | `sudo apt install python3-tk` |
| espeak-ng | — | Voz da chamada de senha (via `pyttsx3`) | `sudo apt install espeak-ng` |

As bibliotecas Python (`pygame`, `fpdf2`, `pyttsx3`) são instaladas por `pip install -r requirements.txt`.

</details>

## Arquitetura do Sistema

| Módulo | Arquivo | Função |
|--------|---------|--------|
| SRV | `servidor/srv.py` | Servidor TCP central que gerencia as filas |
| TV | `clientes/tv.py` | Visualização pública das senhas chamadas |
| TS | `clientes/ts.py` | Totem de geração de senhas |
| TA | `clientes/ta.py` | Terminal do atendente no guichê |

**Fluxo:** o TS gera a senha → o SRV gerencia a fila → o TA chama a próxima → a TV exibe.

## Regra de Prioridade

A cada 2 senhas Normais chamadas, a próxima chamada é obrigatoriamente uma Prioritária, desde que exista alguma na fila. Quando não há prioritária pendente, o atendimento segue na ordem Normal.

```text
N1, N2, P1, N3, N4, P2, ...
```

## Estrutura de Arquivos

```text
.
├── iniciar.py            # Inicializador das 4 janelas
├── requirements.txt
├── musica.mp3            # Áudio da chamada (pode ficar na raiz ou em sons/)
├── image.png             # Logo usada nos relatórios (relatorio.py)
├── servidor/
│   └── srv.py            # Servidor TCP central
├── clientes/
│   ├── tv.py             # Visualização pública
│   ├── ts.py             # Totem de senhas
│   └── ta.py             # Terminal do atendente
├── utils/
│   ├── conexao.py        # HOST e PORTA_SRV centralizados
│   ├── audio.py          # Síntese de voz e som
│   └── relatorio.py      # Geração de relatórios em PDF
└── sons/                 # Áudio opcional (.mp3, .wav, .ogg, .flac); audio.py
                          # também procura na raiz do projeto
```

## Configuração de Rede

<details>
<summary>Como rodar em rede real (trocar HOST e PORTA)</summary>

A rede é configurada em um único arquivo: `utils/conexao.py`. Todos os módulos importam `HOST` e `PORTA_SRV` dele.

| Cenário | HOST no servidor | HOST nos clientes |
|---------|------------------|-------------------|
| Mesma máquina (padrão) | `127.0.0.1` | `127.0.0.1` |
| Várias máquinas | `0.0.0.0` (escuta tudo) | IP real do servidor, ex. `192.168.0.10` |

Para descobrir o IP da máquina servidora, use `ip addr` (Linux) ou `ipconfig` (Windows). A `PORTA_SRV` padrão é `5000`; troque-a caso já esteja ocupada (ex. `5050`).

</details>

## Solução de Problemas

<details>
<summary>Tabela de erros comuns</summary>

| Erro | Causa | Solução |
|------|-------|---------|
| `libtk8.6.so: cannot open shared object file` | Tkinter ausente | Veja Pré-requisitos |
| `espeak not found` / sem voz na chamada | espeak-ng ausente | Veja Pré-requisitos |
| `Servidor offline` / `Reconectando...` | SRV não foi iniciado antes dos clientes | Inicie `servidor/srv.py` primeiro (ou use `python3 iniciar.py`, que respeita a ordem via DELAYS) |
| `pygame ... timeout` ao tocar o som | Áudio inacessível ou ausente | Coloque um arquivo suportado em `sons/` e confira o servidor de áudio do sistema |
| `address already in use` (porta 5000) | Porta 5000 ocupada por outro processo | Altere `PORTA_SRV` em `utils/conexao.py` para uma porta livre |

</details>
