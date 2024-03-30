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
        self.state = ClientState.UNDEFINED
    
class Client:
    def __init__(self, server_name, server_port, running):
        #  Logging level set to INFO, change to DEBUG for print statements
        logging.basicConfig(format='%(message)s', level=logging.INFO)
        
        # Setting up client state
        self.session_id = random.randint(0, (2 ** 32) - 1)
        self.sequence_number = 0
        self.server_addr = (server_name, server_port)
        self.buffer_size = 2048
        self.client_time = time.process_time()
        self.timer_on = True
        self.sem = Semaphore()
        
        # Creating the socket we will communicate out of
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

        # Create a queue to hold lines from standard input that still need to be sent
        self.message_queue = Queue()

        # Create a thread to handle keyboard input and handle client timeout
        self.handle_keyboard_thread = Thread(target = self.__handle_keyboard, args=(running,), daemon = True)
        self.handle_timeout_thread = Thread(target = self.__handle_timeouts, args=(running,), daemon = True)
        
        # On initialization, send a hello to the server
        hello_header = create_header(MessageType.HELLO, 0, self.session_id)
        self.socket.sendto(hello_header, self.server_addr)
        self.state = ClientState.HELLO_WAIT

        # Begin keyboard and socket threads
        self.handle_keyboard_thread.start()
        self.handle_timeout_thread.start()
        self.__handle_socket(running)

    def __handle_timeouts(self, running):
        while running:
            if self.timer_on:
                passed_time = time.process_time() - self.client_time;
                if passed_time > 300.0 and self.timer_on:
                    self.__close()
                time.sleep(2)

    def __handle_socket(self, running):
        while running:
            logging.debug("client socket waiting for server message")
            # listen to socket for any messages
            packet, _ = self.socket.recvfrom(self.buffer_size)
            magic, version, command, sequence_number, session_id = unpack_header(packet)
            logging.debug(f'server message recieved -> Command: {command_to_ascii(command)}, {sequence_number}, {session_id}')

            # Check magic and decide what to do based on what state we're currently in
            if magic != 0xC356 or version != 1:
                continue
                
            if command == MessageType.GOODBYE:
                self.state = ClientState.CLOSING
                self.__close()
                continue
            
            match self.state:
                case ClientState.HELLO_WAIT:
                    if command == MessageType.HELLO:
                        self.timer_on = False
                        self.state = ClientState.READY
                        self.sequence_number += 1
                    else:
                        self.state = ClientState.CLOSING
                        self.__close() 
                case ClientState.READY:
                    if command == MessageType.ALIVE:
                        continue
                    else:
                        self.state = ClientState.CLOSING
                        self.__close() 
                case ClientState.READY_TIMER:
                    if command == MessageType.ALIVE:
                        self.timer_on = False
                        self.state = ClientState.READY
                    else:
                        self.state = ClientState.CLOSING
                        self.__close()
                case ClientState.CLOSING:
                    if command == MessageType.ALIVE:
                        continue
                    else:
                        self.state = ClientState.CLOSING
                        self.__close() 
                case ClientState.CLOSED:
                    pass
                case _:
                    logging.error("invalid state! closing")
                    self.state = ClientState.CLOSING
                    self.__close()
            
    def __handle_keyboard(self, running):
        while running:
            text = sys.stdin.readline()
            logging.debug("client key input detected...")

            # Terminates client if input is invalid (CTRL-d/c or 'q')
            if (not text or (text == "q" and sys.stdin.isatty())):
                if self.state == ClientState.HELLO_WAIT or self.state == ClientState.READY or self.state == ClientState.READY_TIMER:
                    self.__close()
                else:
                    self.state = ClientState.CLOSING
                    self.__close()
            else:
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
    server_name = sys.argv[1]           # destination address
    server_port = int(sys.argv[2])      # port number
   
    # Create client
    client = Client(server_name, server_port)