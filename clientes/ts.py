import socket
import sys
import os

# Aqui adicionei o diretório pai ao path para conseguir importar a pasta utils
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from utils import conexao

def iniciar_ts():
    print("--- TERMINAL DE SENHAS (TS) INICIADO ---")
    print("Digite 'N' para Normal, 'P' para Prioritária ou 'S' para Sair.")

    while True:
        escolha = input("\nGerar qual senha? ").strip().upper()

        if escolha == 'S':
            print("Encerrando Terminal de Senhas...")
            break
        elif escolha not in ['N', 'P']:
            print("Opção inválida! Use N ou P.")
            continue

        # Criando o socket TCP (SOCK_STREAM) para o protocolo IPv4 (AF_INET)
        cliente_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        
        try:
            # Conecta ao servidor utilizando as configurações do utils
            cliente_socket.connect((conexao.HOST, conexao.PORTA_SRV))
            
            # Montamos a mensagem no formato: "IDENTIFICADOR_DO_CLIENTE|COMANDO"
            # Ex: "TS|GERAR_N"
            mensagem = f"TS|GERAR_{escolha}"
            
            # Envia a mensagem codificada em bytes para o servidor
            cliente_socket.send(mensagem.encode('utf-8'))
            
            # Aguarda a confirmação do servidor (buffer de 1024 bytes)
            resposta = cliente_socket.recv(1024).decode('utf-8')
            print(f"Resposta do Servidor: {resposta}")

        # Tratamento de erro caso o servidor não esteja em serviço    
        except ConnectionRefusedError:
            print("Erro: Não foi possível conectar. O Servidor (SRV) está rodando?")
        finally:
            # Sempre fecha a conexão após a requisição para liberar recursos
            cliente_socket.close()

if __name__ == "__main__":
    iniciar_ts()