import socket
import logging
import sys

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("repro")

def test_connect(host, port):
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        logger.info(f"Attempting to connect to {host}:{port}")
        s.connect((host, port))
        logger.info("Connect call returned (Succeeded?)")
        s.setblocking(False)
        logger.info("Set non-blocking")
        return True
    except Exception as e:
        logger.error(f"Connect failed: {e}")
        return False

if __name__ == "__main__":
    host = "127.0.0.1"
    port = 24800
    if len(sys.argv) > 1:
        host = sys.argv[1]
    if len(sys.argv) > 2:
        port = int(sys.argv[2])
    test_connect(host, port)
