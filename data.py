#!/usr/bin/env python3
from struct import pack, unpack

_HEADER = '!HBBII'

class ClientData:
    def __init__(self, username, client_addr, session_id, time):
        self.username = username
        self.client_addr = client_addr
        self.session_id = session_id
        self.expected_sequence_number = 1
        self.previous_sequence_number = 0
        self.time = time
        self.timer_on = True
        self.state = ClientState.UNDEFINED

# Define value for message types
class MessageType:
    HELLO = 1
    DATA = 2
    ALIVE = 3
    GOODBYE = 4

# Define value for client states
class ClientState:
    UNDEFINED = -1
    HELLO_WAIT = 0
    READY = 1
    READY_TIMER = 2
    CLOSING = 3
    CLOSED = 4

# Define value for server state
class ServerState:
    UNDEFINED = -1
    RECEIVE = 0
    DONE = 1

def create_header(command, sequence_number, session_id):
    return pack(_HEADER, 50006, 1, command, sequence_number, session_id)

def unpack_header(data):
    return unpack(_HEADER, data[0:12])
    

def command_to_ascii(command):
    match command: 
        case 1:
            return 'Hello'
        case 2:
            return 'Data'
        case 3:
            return 'Alive'
        case 4:
            return 'Goodbye'
    return 'Invalid Command'