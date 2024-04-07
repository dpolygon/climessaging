#!/usr/bin/env python3
import sys
import socket
import random
import logging
import time

from queue import Queue
from data import *
from threading import Thread, Semaphore
    
class Client:
    def __init__(self):
        #  Logging level set to INFO, change to DEBUG for print statements
        logging.basicConfig(format='%(message)s', level=logging.INFO)
        
        # Setting up client state
        self.session_id = random.randint(0, (2 ** 32) - 1)
        self.buffer_size = 2048
        self.sequence_number = 0
        server_name = input('Provide a domain name (e.g., UTCS-MACHINE-NAME.cs.utexas.edu) or an IPv4 address: ').strip()
        server_port = int(input('Provide a port number: ').strip())
        self.username = input('What name would you like your friends to know you by? ')
        print(f'Welcome {self.username}')
        self.server_addr = (server_name, server_port)
        self.client_time = time.process_time()
        self.echo = False
        self.timer_on = True
        self.sem = Semaphore()
        
        # Creating the socket we will communicate out of
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

        # Create a queue to hold lines from standard input that still need to be sent
        self.message_queue = Queue()

        # Create a thread to handle keyboard input and handle client timeout
        self.handle_keyboard_thread = Thread(target = self.__handle_keyboard, daemon = True)
        self.handle_timeout_thread = Thread(target = self.__handle_timeouts, daemon = True)
        
        # On initialization, send a hello to the server
        hello_header = create_header(MessageType.HELLO, 0, self.session_id)
        hello_msg = hello_header + self.username.encode('utf-8')
        self.socket.sendto(hello_msg, self.server_addr)
        self.state = ClientState.HELLO_WAIT
        self.running = True
        # Begin keyboard and socket threads
        self.handle_keyboard_thread.start()
        self.handle_timeout_thread.start()
        self.__handle_socket()

    def __handle_timeouts(self):
        while self.running:
            if self.timer_on:
                passed_time = time.process_time() - self.client_time;
                if passed_time > 300.0 and self.timer_on:
                    self.__close()
                time.sleep(2)

    def __handle_socket(self):
        while self.running:
            logging.debug("client socket waiting for server message")
            # listen to socket for any messages
            packet, _ = self.socket.recvfrom(self.buffer_size)
            magic, version, command, sequence_number, session_id = unpack_header(packet)
            logging.debug(f'server message recieved -> Command: {command_to_ascii(command)}, {sequence_number}, {session_id}')

            # Check magic and decide what to do based on what state we're currently in
            if magic != 0xC356 or version != 1:
                continue

            if command == MessageType.HELLO and self.state == ClientState.HELLO_WAIT:
                print("chatroom found - connected!")
                self.timer_on = False
                self.state = ClientState.READY
                self.sequence_number += 1
                continue

            if command == MessageType.DATA:
                if self.session_id != session_id or self.echo:
                    print(packet[12:].decode('utf-8'))

            if command == MessageType.ALIVE and self.state == ClientState.READY_TIMER:
                self.timer_on = False
                self.state = ClientState.READY

            if command == MessageType.GOODBYE:
                print("server disconnecting...")
                self.state = ClientState.CLOSING
                self.__close()
                continue

    def __handle_keyboard(self):
        while self.running:
            text = input()
            logging.debug("client key input detected...")

            # Terminates client if input is invalid (CTRL-d/c or 'q')
            if (not text or (text == "q" and sys.stdin.isatty())):
                print("leaving chat")
                self.__close()
                continue

            if self.state == ClientState.READY:
                data_header = create_header(MessageType.DATA, self.sequence_number, self.session_id)
                data_msg = data_header + text.encode('utf-8')
                self.socket.sendto(data_msg, self.server_addr)
                self.sequence_number += 1
                # Set timer
                self.client_time = time.process_time()
                self.timer_on = True
                self.state = ClientState.READY_TIMER

            elif self.state == ClientState.READY_TIMER:
                data_header = create_header(MessageType.DATA, self.sequence_number, self.session_id)
                data_msg = data_header + text.encode('utf-8')
                self.socket.sendto(data_msg, self.server_addr)
                self.sequence_number += 1

            # If the input is valid, add to the back of the message queue

    def __close(self):
        self.sem.acquire()
        if self.state == ClientState.CLOSING:
            self.state = ClientState.CLOSED
            self.running = False
        else:
            # create goodbye message and send into socket, then close socket
            goodbye = create_header(MessageType.GOODBYE, self.sequence_number, self.session_id)
            self.socket.sendto(goodbye, self.server_addr)
            self.state = ClientState.CLOSING

            # Set time
            self.client_time = time.process_time()
            self.timer_on = True

        self.sem.release()

# command line argument: name + port
if __name__ == "__main__":

    # Create client
    client = Client()