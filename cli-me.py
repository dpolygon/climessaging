from server import Server
from client import Client

running = True

Server('', 2853, running, app=True)
print('server created')
Client('192.168.1.159', 2853, running)
