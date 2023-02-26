#!/usr/bin/env python3
import enum
import struct

from email.message import Message

_HEADER = '!HBBII'

# Define enum for message types
class MessageType(enum.IntEnum):
    HELLO = 1
    DATA = 2
    ALIVE = 3
    GOODBYE = 4

# Define enums for client states
class ClientState(enum.IntEnum):
    UNDEFINED = -1
    HELLO_WAIT = 0
    READY = 1
    READY_TIMER = 2
    CLOSING = 3
    CLOSED = 4

# Define enums for server state
class ServerState(enum.IntEnum):
    UNDEFINED = -1
    RECEIVE = 0
    DONE = 1

def command_to_ascii(command):
    return MessageType(command).name

def create_header(command, sequence_number, session_id):
    return struct.pack(_HEADER, 50006, 1, command, sequence_number, session_id)

def unpack_header(data):
    return struct.unpack(_HEADER, data[0:12])
