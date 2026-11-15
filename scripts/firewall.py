"""Совместимый запуск Docker CLI firewall; локальный Python не обязателен."""
import subprocess
import sys
from pathlib import Path

if __name__ == '__main__':
    raise SystemExit(subprocess.call([str(Path(__file__).with_suffix('')), *sys.argv[1:]]))
