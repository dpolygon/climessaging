from server import Server
from client import Client

import sys

running = True

Server('', 2853, running, app=True)
print('provide an IP address...')
IP = sys.stdin.readline().strip()
Client(IP, 2853, running)
