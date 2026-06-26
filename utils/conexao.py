"""
conexao.py — Configuração centralizada de rede do SASE.

O QUE FAZ:
    Define em um único lugar os parâmetros de rede usados por TODOS os
    componentes do sistema (servidor de senhas, painel de chamadas, totem de
    retirada, guichês de atendimento). Em vez de espalhar o endereço e a porta
    por vários arquivos, eles ficam aqui e são importados onde forem precisos.

COMO USAR:
    from utils.conexao import HOST, PORTA_SRV
    sock.connect((HOST, PORTA_SRV))   # nos clientes
    sock.bind((HOST, PORTA_SRV))      # no servidor

POR QUE CENTRALIZAR AQUI:
    Quando o projeto deixar de rodar só na máquina local e for colocado em uma
    rede real (laboratório, várias máquinas), basta alterar HOST e PORTA_SRV
    NESTE arquivo. Todos os módulos passam a apontar para o novo destino sem
    necessidade de caçar valores "hardcoded" pelo código — evita inconsistência
    (um cliente tentando uma porta e o servidor escutando em outra).

PROTOCOLO DE COMUNICAÇÃO:
    O SASE usa sockets TCP/IP (camada de transporte). TCP garante entrega
    ordenada e confiável das mensagens de controle de senhas entre cliente e
    servidor — essencial porque a ordem das chamadas de atendimento importa.

Disciplina: Sistemas Distribuídos — IFCE Campus Crato
"""

# ── Configuração de Rede ───────────────────────────────────────────────────

# Endereço IP do servidor.
# '127.0.0.1' é o "localhost" — o endereço de loopback que aponta para a
# própria máquina. Usá-lo significa que cliente e servidor estão no MESMO
# computador, ideal para desenvolvimento e testes sem depender de rede física.
# QUANDO TROCAR: ao distribuir em máquinas diferentes, substituir pelo IP real
# da máquina que hospeda o servidor (ex.: '192.168.0.10') — descoberto via
# `ip addr` (Linux) ou `ipconfig` (Windows). Para o servidor aceitar conexões
# de outras máquinas, ele pode também usar '0.0.0.0' (escuta em todas as
# interfaces de rede).
HOST = '127.0.0.1'

# Porta TCP em que o servidor de senhas escuta.
# POR QUE ACIMA DE 1024: portas de 0 a 1023 são "well-known ports" reservadas
# e exigem privilégios de administrador/root para serem abertas. Escolhendo uma
# porta alta (>= 1024) o programa roda como usuário comum, sem sudo/admin.
# QUANDO TROCAR: 5000 é uma porta comum e também é a padrão do Flask. Se o
# projeto rodar um servidor Flask na mesma máquina, haverá conflito ("address
# already in use") — nesse caso troque por outra porta livre (ex.: 5050, 6000).
PORTA_SRV = 5000
