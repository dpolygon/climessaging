#!/usr/bin/env python3
import sys
import socket
import logging
import time

from queue import Queue

from data import *
from threading import Thread, Semaphore
from client import ClientData

class Server:
    buffer_size = 2048
    expected_num_of_packets = 58936
    testing = False

    def __init__(self, server_name, server_port, app=False):
        # Logging level set to INFO, change to DEBUG for print statements
        logging.basicConfig(format='%(message)s', level=logging.INFO)
        
        # initialize server state
        self.server_addr = (server_name, server_port)
        self.outgoing_seq_num = 0
        self.sem = Semaphore()
        logging.debug("lock created")

        # initializing socket
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.socket.bind(self.server_addr)
        self.socket.setblocking(False)
        logging.debug("socket initialized")

        # initialize shared objects
        self.clients = {}
        self.packet_queue = Queue()
        self.message_queue = Queue()
        self.validation_queue = Queue()
        self.broadcast_queue = Queue()
        logging.debug("queues creates")
        
        self.running = True

        # initialize threads
        self.handle_packets_thread = Thread(target = self.__handle_packets, daemon = True)
        self.handle_validation_thread = Thread(target = self.__handle_validation, daemon = True)
        self.handle_printing_thread = Thread(target = self.__handle_printing, daemon = True)
        self.handle_timeout_thread = Thread(target = self.__handle_timeouts, daemon = True)
        self.handle_keyboard_thread = Thread(target = self.__handle_keyboard, daemon = True)
        self.handle_broadcast_thread = Thread(target = self.__handle_broadcast, daemon = True)
        
        # begin running threads
        self.handle_validation_thread.start()
        logging.debug("validation thread online")
        self.handle_printing_thread.start()
        logging.debug("print thread online")
        self.handle_timeout_thread.start()
        logging.debug("timout thread online")
        self.handle_packets_thread.start()
        logging.debug("packet thread online")
        self.handle_keyboard_thread.start()
        logging.debug("keyboard thread online")
        self.handle_broadcast_thread.start()
        logging.debug("broadcast thread online")
        self.__handle_socket()


    def __handle_socket(self):
        while self.running:
            # Check to see if a packet has been recieved
            try:
                packet, client_addr = self.socket.recvfrom(self.buffer_size)
            except:
                continue
            else:
                self.packet_queue.put((packet, client_addr))
                logging.debug("packet picked up...")
                
        self.socket.close()
        
    def __handle_broadcast(self):
        while self.running:
            if self.broadcast_queue.empty():
                continue
            
            logging.debug("broadcasting...")
            id, message = self.broadcast_queue.get()
            for session_id in self.clients:
                client = self.clients[session_id]
                hello_message = create_header(MessageType.DATA, 0, id)
                msg = hello_message + message.encode('utf-8') 
                self.socket.sendto(msg, client.client_addr)
        
    def __handle_packets(self):
        while self.running:
            if self.packet_queue.empty():
                continue
            
            logging.debug("packet found in queue...")
            packet, client_addr = self.packet_queue.get()
            try:
                magic, version, command, sequence_number, session_id = unpack_header(packet)
            except:
                # If we run into an exception when trying to unpack, just continue
                continue
            else:
                # Check if existing session ID, but different IP:port
                # Ignore the packet
                if session_id in self.clients and client_addr != self.clients[session_id].client_addr:
                    continue;

                if command == MessageType.HELLO:
                    if session_id not in self.clients and sequence_number == 0:
                        # Create a new ClientData
                        username = '@' + packet[12:].decode("utf-8")
                        self.clients[session_id] = ClientData(username, client_addr, session_id, time.process_time())
                        hello_message = create_header(MessageType.HELLO, 0, session_id)
                        self.socket.sendto(hello_message, client_addr)
                        self.validation_queue.put((packet, client_addr))

                elif command == MessageType.DATA:
                    logging.debug(f'Magic: {magic}, Version: {version}, Command: {command_to_ascii(command)}, {sequence_number}, {session_id}')
                    if session_id in self.clients:
                        self.validation_queue.put((packet, client_addr))

                elif command == MessageType.GOODBYE:
                    if session_id in self.clients: 
                        self.validation_queue.put((packet, client_addr))

                else:
                    self.__client_close(client_addr, session_id)

    def validate_and_push(self, session_id, sequence_number, packet, client_addr):
        # We need to keep track of multiple things: last received packet number and expected
        if session_id in self.clients.keys():
            user = self.clients[session_id].username
            self.clients[session_id].previous_sequence_number = sequence_number
            self.clients[session_id].expected_sequence_number += 1
            self.outgoing_seq_num += 1

            # Decode the message and add to message queue
            logging.debug(f'[{sequence_number}]')
            message = f'{user} ' + packet[12:].decode("utf-8")
            self.message_queue.put(message)
            self.broadcast_queue.put((session_id, message))

            # Set the timer
            self.clients[session_id].time = time.process_time()

            # Send back alive message
            alive = create_header(MessageType.ALIVE, self.outgoing_seq_num, session_id)
            self.socket.sendto(alive, client_addr)

    def __handle_validation(self):
        while self.running:
            if self.validation_queue.empty():
                continue
            
            logging.debug("validating ...")
            packet, client_addr = self.validation_queue.get();
            magic, version, command, sequence_number, session_id = unpack_header(packet)    

            if magic != 0xC356 or version != 1:
                continue
            
            if command == MessageType.HELLO:
                user = self.clients[session_id].username
                msg = f'{user} joined the conversation'
                self.message_queue.put(msg)
                self.broadcast_queue.put((session_id, msg))
                continue

            if command == MessageType.GOODBYE:
                self.__client_close(client_addr, session_id)
                continue

            elif command == MessageType.DATA:
                if session_id in self.clients.keys():
                    client = self.clients[session_id]
                    if sequence_number > client.expected_sequence_number:
                        # Should have normal behavior, since we still received a valid packet
                        # When receiving a valid DATA, turn off the timer for that client
                        self.clients[session_id].timer_on = False
                        lost_packets = sequence_number - client.expected_sequence_number
                        for lost_packet in range(lost_packets):
                            self.message_queue.put(f'{hex(session_id)} [{lost_packet + client.expected_sequence_number}] Lost packet!')
                        client.expected_sequence_number += lost_packets

                    elif sequence_number < client.expected_sequence_number:
                        self.message_queue.put(f'{hex(session_id)} [{sequence_number}] Out of order packet!')
                        self.__client_close(client_addr, session_id)
                        continue

                    elif (client.previous_sequence_number == sequence_number):
                        self.message_queue.put(f'{hex(session_id)}[{sequence_number}] Duplicate packet!')
                        continue

            self.validate_and_push(session_id, sequence_number, packet, client_addr)    
                    
    def __handle_timeouts(self):
        while self.running:
            for session_id in list(self.clients):
                client = self.clients.get(session_id)
                client_time = client.time
                passed_time = time.process_time() - client_time;
                if passed_time > 300.0 and client.timer_on:
                    self.__client_close(client.client_addr, session_id)
            time.sleep(2)
            
    def __handle_keyboard(self):
        while self.running:
            text = sys.stdin.readline()
            logging.debug("server detected keyboard input...")
            if not text or (text == "q\n" and sys.stdin.isatty()):
                self.__server_close()

    def __handle_printing(self):
        while self.running:
            if self.message_queue.empty():
                continue
            
            logging.debug("server found message in printing queue...")
            message = self.message_queue.get()
            print(message.rstrip())
            
    def __server_close(self):
        logging.debug("terminating all client connections")
        # Iterate through all clients and send a goodbye
        for session_id in self.clients:
            print(f'closing {session_id}')
            goodbye = create_header(MessageType.GOODBYE, self.outgoing_seq_num, session_id)
            self.socket.sendto(goodbye, self.clients.get(session_id).client_addr)
            self.message_queue.put(f'{hex(session_id)} Session closed')
        self.running = False

    def __client_close(self, client_addr, session_id):
        self.sem.acquire()
        # Critical section
        goodbye = create_header(MessageType.GOODBYE, self.outgoing_seq_num, session_id)
        self.socket.sendto(goodbye, client_addr)
        if session_id in self.clients:
            user = self.clients[session_id].username
            del(self.clients[session_id])
            msg = f'{user} left the chat.'
            self.message_queue.put(msg)
            self.broadcast_queue.put((session_id, msg))
        self.sem.release()

        if self.testing:
            self.message_queue.put(f'{self.expected_num_of_packets} {self.outgoing_seq_num} : Loss Rate: {100 - (self.outgoing_seq_num / self.expected_num_of_packets) * 100}')
            self.outgoing_seq_num = 0
    
if __name__ == "__main__":
    # create server socket
    server_name = ''
    server_port = int(sys.argv[1])

    # Create server
    server = Server(server_name, server_port)