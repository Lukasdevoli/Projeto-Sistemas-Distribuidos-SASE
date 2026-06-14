# clientes/tv.py
import socket
import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from utils import conexao

def iniciar_tv():
    print("--- TERMINAL DE VISUALIZAÇÃO (TV) INICIADO ---")
    print("Aguardando chamadas...")

    cliente_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    
    try:
        cliente_socket.connect((conexao.HOST, conexao.PORTA_SRV))
        
        # A TV se identifica para o servidor e avisa que vai ficar conectada
        mensagem = "TV|CONECTAR"
        cliente_socket.send(mensagem.encode('utf-8'))
        
        # Loop infinito recebendo os avisos do servidor
        while True:
            # A execução do script pausa aqui (bloqueio) até receber dados do servidor
            dados = cliente_socket.recv(1024)
            
            if not dados:
                # Se dados vier vazio, o servidor fechou a conexão
                print("Conexão com o servidor encerrada.")
                break
                
            mensagem_recebida = dados.decode('utf-8')
            
            # Exibe a chamada de forma destacada
            print("="*40)
            print(f"NOVA CHAMADA: {mensagem_recebida}")
            print("="*40)
            
    except ConnectionRefusedError:
        print("Erro: Servidor offline. Inicie o servidor primeiro.")
    finally:
        cliente_socket.close()

if __name__ == "__main__":
    iniciar_tv()