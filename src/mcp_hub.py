import requests
import os

def get_servers():
    host = os.getenv("THING_HOST", "127.0.0.1")
    port = os.getenv("MCP_HUB_PORT", "3000")
    res = requests.get(f"http://{host}:{port}/api/servers?token=5B0xk3XPN0zNxChUGV1fDVuifc0Ko7cIiY7TkA0PyIk")
    return res.json()

if __name__ == "__main__":
    print(get_servers())
