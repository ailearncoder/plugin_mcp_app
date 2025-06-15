import os
import sys
import fcntl
import signal
import time

def single_instance():
    lock_file = 'mcp_proxy_run.lock'
    try:
        lock_fd = os.open(lock_file, os.O_WRONLY | os.O_CREAT)
        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except (IOError, OSError):
        # 读取锁文件中的旧PID
        try:
            with open(lock_file, 'r') as f:
                old_pid = int(f.read())
        except:
            old_pid = None
        # 尝试终止旧进程
        if old_pid:
            try:
                os.kill(old_pid, signal.SIGTERM)
                print(f"Terminated old instance (PID: {old_pid})")
                time.sleep(0.1)
            except ProcessLookupError:
                pass
        # 再次尝试获取锁
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except (IOError, OSError):
            print("Failed to terminate old instance", file=sys.stderr)
            sys.exit(1)
    # 将当前PID写入锁文件
    with open(lock_file, 'w') as f:
        f.write(str(os.getpid()))
    return lock_fd

if __name__ == "__main__":
    lock_fd = single_instance()
    while True:
        os.system("uv run --active ./mcp_proxy.py")
        time.sleep(1)
