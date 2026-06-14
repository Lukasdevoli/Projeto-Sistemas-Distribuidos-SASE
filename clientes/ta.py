# clientes/ta.py
import socket
import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from utils import conexao

def iniciar_ta():
    # Simulando que este terminal seja o Guichê 1 (poderia ser dinâmico no futuro)
    id_guiche = input("Digite o número deste guichê (ex: 1, 2, 3): ").strip()
    print(f"--- TERMINAL DE ATENDIMENTO (GUICHÊ {id_guiche}) INICIADO ---")
    print("Pressione ENTER para chamar o próximo da fila ou digite 'S' para sair.")

    while True:
        acao = input("\nAguardando comando... ")

        if acao.strip().upper() == 'S':
            print("Encerrando Terminal de Atendimento...")
            break

        cliente_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        
        try:
            cliente_socket.connect((conexao.HOST, conexao.PORTA_SRV))
            
            # Formato da mensagem: "TA|ID_DO_GUICHE" -> Avisa o servidor quem está pedindo
            mensagem = f"TA|{id_guiche}"
            cliente_socket.send(mensagem.encode('utf-8'))
            
            # Aguarda o servidor responder qual senha foi atribuída a este guichê
            resposta = cliente_socket.recv(1024).decode('utf-8')
            print(f">>> {resposta}")
            
        except ConnectionRefusedError:
            print("Erro: Servidor offline.")
        finally:
            cliente_socket.close()

if __name__ == "__main__":
    iniciar_ta()