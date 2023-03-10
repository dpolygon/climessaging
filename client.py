#!/usr/bin/env python3
import sys
import socket
import random
import logging
import time

from queue import Queue
from helper import *
from threading import Thread, Semaphore

class ClientData:
    def __init__(self, client_addr, session_id, time):
        self.client_addr = client_addr
        self.session_id = session_id
        self.expected_sequence_number = 1
        self.previous_sequence_number = 0
        self.time = time
        self.timer_on = True
        state = ClientState.UNDEFINED
    
class Client:
    buffer_size = 2048
    client_time = 0
    timer_on = False

    def __init__(self, server_name, server_port):
        # Client state
        self.session_id = random.randint(0, (2 ** 32) - 1)
        self.sequence_number = 0
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.server_name = server_name
        self.server_port = server_port
        self.server_addr = (self.server_name, self.server_port)
        self.state = ClientState.UNDEFINED
        self.sem = Semaphore()

        logging.basicConfig(format='%(message)s', level=logging.INFO)     #  Logging level set to INFO, change to DEBUG for print statements
        self.running = True

        # Create a queue to hold lines from standard input that still need to be sent
        self.message_queue = Queue()

        # Create a thread to handle keyboard input and handle client timeout
        self.handle_keyboard_thread = Thread(target = self.__handle_keyboard, daemon = True)
        self.handle_timeout_thread = Thread(target = self.__handle_timeouts, daemon = True)
        
        # On initialization, send a hello to the server
        hello_header = create_header(int(MessageType.HELLO), 0, self.session_id)
        self.socket.sendto(hello_header, self.server_addr)

        # Set timer
        self.client_time = time.process_time()
        self.timer_on = True
        self.state = ClientState.HELLO_WAIT

        # Begin keyboard and socket threads
        self.handle_keyboard_thread.start()
        self.handle_timeout_thread.start()
        self.__handle_socket()

    def __handle_timeouts(self):
        while self.running or self.timer_on:
            passed_time = time.process_time() - self.client_time;
            if passed_time > 5.0 and self.timer_on:
                self.__close()
            time.sleep(1)

    def __handle_socket(self):
        logging.debug("socket is listening")
        while self.running:
            # listen to socket for any messages
            packet, _ = self.socket.recvfrom(self.buffer_size)
            magic, version, command, sequence_number, session_id = unpack_header(packet)
            logging.debug(f'response recieved -> Magic: {magic}, Version: {version}, Command: {command_to_ascii(command)}, {sequence_number}, {session_id}')

            # Check magic and decide what to do based on what state we're currently in
            if magic == 0xC356 and version == 1:
                if command == int(MessageType.GOODBYE):
                    self.state = ClientState.CLOSING
                    self.__close()
                else: 
                    if self.state == ClientState.HELLO_WAIT:
                        if command == int(MessageType.HELLO):
                            self.timer_on = False
                            self.state = ClientState.READY
                            self.sequence_number += 1
                        else:
                            self.state = ClientState.CLOSING
                            self.__close() 
                    elif self.state == ClientState.READY:
                        if command == int(MessageType.ALIVE):
                            continue
                        else:
                            self.state = ClientState.CLOSING
                            self.__close() 
                    elif self.state == ClientState.READY_TIMER:
                        if command == int(MessageType.ALIVE):
                            self.timer_on = False
                            self.state = ClientState.READY
                        else:
                            self.state = ClientState.CLOSING
                            self.__close()
                    elif self.state == ClientState.CLOSING:
                        if command == int(MessageType.ALIVE):
                            continue
                        else:
                            self.state = ClientState.CLOSING
                            self.__close() 
                    elif self.state == ClientState.CLOSED:
                        pass
                    else:
                        logging.error("invalid state! closing")
                        self.state = ClientState.CLOSING
                        self.__close()
            
    def __handle_keyboard(self):
        while self.running:
            text = sys.stdin.readline()

            # Terminates client if input is invalid (CTRL-d/c or 'q')
            if (not text or (text == "q" and sys.stdin.isatty())):
                if self.state == ClientState.HELLO_WAIT or self.state == ClientState.READY or self.state == ClientState.READY_TIMER:
                    self.__close()
                else:
                    self.state = ClientState.CLOSING
                    self.__close()
            else:
                if self.state == ClientState.READY:
                    data_header = create_header(int(MessageType.DATA), self.sequence_number, self.session_id)
                    data_msg = data_header + text.encode('utf-8')
                    self.socket.sendto(data_msg, self.server_addr)
                    self.sequence_number += 1

                    # Set timer
                    self.client_time = time.process_time()
                    self.timer_on = True

                    self.state = ClientState.READY_TIMER
                elif self.state == ClientState.READY_TIMER:
                    data_header = create_header(int(MessageType.DATA), self.sequence_number, self.session_id)
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
            goodbye = create_header(int(MessageType.GOODBYE), self.sequence_number, self.session_id)
            self.socket.sendto(goodbye, self.server_addr)
            self.state = ClientState.CLOSING

            # Set time
            self.client_time = time.process_time()
            self.timer_on = True

        self.sem.release()

# command line argument: name + port
if __name__ == "__main__":
    server_name = sys.argv[1]           # destination address
    server_port = int(sys.argv[2])      # port number
   
    # Create client
    client = Client(server_name, server_port)