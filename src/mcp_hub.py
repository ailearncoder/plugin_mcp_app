import requests
import os

def load_env():
    env_file = '/root/.env'
    if os.path.exists(env_file):
        with open(env_file, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#'):
                    key, value = line.split('=', 1)
                    os.environ[key] = value

def get_servers():
    load_env()
    host = os.getenv("THING_HOST", "127.0.0.1")
    port = os.getenv("MCP_HUB_PORT", "3000")
    token = os.getenv("MCP_HUB_TOKEN", "5B0xk3XPN0zNxChUGV1fDVuifc0Ko7cIiY7TkA0PyIk")
    res = requests.get(f"http://{host}:{port}/api/servers?token={token}")
    return res.json()

if __name__ == "__main__":
    print(get_servers())
