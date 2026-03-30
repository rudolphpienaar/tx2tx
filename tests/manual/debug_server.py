import socket
import sys

def run_debug_server(host, port):
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind((host, port))
        s.listen(1)
        print(f"DEBUG SERVER: Listening on {host}:{port}")
        print("Waiting for connection...")
        
        while True:
            client_sock, address = s.accept()
            print(f"DEBUG SERVER: Accepted connection from {address}")
            
            try:
                while True:
                    data = client_sock.recv(4096)
                    if not data:
                        print(f"DEBUG SERVER: Connection closed by {address}")
                        break
                    print(f"DEBUG SERVER: Received from {address}: {data.decode('utf-8', errors='replace').strip()}")
            except Exception as e:
                print(f"DEBUG SERVER: Error during receive: {e}")
            finally:
                client_sock.close()
                print("DEBUG SERVER: Waiting for next connection...")
                
    except Exception as e:
        print(f"DEBUG SERVER: Failed to start: {e}")
        sys.exit(1)

if __name__ == "__main__":
    host = "0.0.0.0"
    port = 24800
    if len(sys.argv) > 1:
        host = sys.argv[1]
    if len(sys.argv) > 2:
        port = int(sys.argv[2])
    run_debug_server(host, port)
