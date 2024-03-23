#!/usr/bin/env python3
import struct
from email.message import Message

_HEADER = '!HBBII'

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

def create_header(command, sequence_number, session_id):
    return struct.pack(_HEADER, 50006, 1, command, sequence_number, session_id)

def unpack_header(data):
    return struct.unpack(_HEADER, data[0:12])
