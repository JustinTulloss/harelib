"""
Read/Write AMQP frames over network transports.

2009-01-14 Barry Pederson <bp@barryp.org>

"""
# Copyright (C) 2009 Barry Pederson <bp@barryp.org>
#
# This library is free software; you can redistribute it and/or
# modify it under the terms of the GNU Lesser General Public
# License as published by the Free Software Foundation; either
# version 2.1 of the License, or (at your option) any later version.
#
# This library is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public
# License along with this library; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301

import socket
from iostream import IOStream
from iothread import IOThread

#
# See if Python 2.6+ SSL support is available
#
try:
    import ssl
    HAVE_PY26_SSL = True
except:
    HAVE_PY26_SSL = False

from struct import pack, unpack

AMQP_PORT = 5672

# Yes, Advanced Message Queuing Protocol Protocol is redundant
AMQP_PROTOCOL_HEADER = 'AMQP\x01\x01\x09\x01'


class _AbstractTransport(object):
    """
    Common superclass for TCP and SSL transports

    """
    def __init__(self, host, connect_timeout):
        if ':' in host:
            host, port = host.split(':', 1)
            port = int(port)
        else:
            port = AMQP_PORT

        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.settimeout(connect_timeout)

        try:
            self.sock.connect((host, port))
        except self.socket.error:
            self.sock.close()
            raise
        self.sock.settimeout(None)


        self._setup_transport()

        self.stream = IOStream(self.sock)

        self._write(AMQP_PROTOCOL_HEADER)

    def __del__(self):
        self.close()


    def _read(self, n, callback = None):
        """
        Read exactly n bytes from the peer, call back when you're done.

        """
        def cb(data):
            print "received %d bytes" % len(data)
            if callable(callback):
                callback(data)

        self.stream.read_bytes(n, cb)


    def _setup_transport(self):
        """
        Do any additional initialization of the class (used
        by the subclasses).

        """
        pass


    def _write(self, s, callback = None):
        """
        Completely write a string to the peer, call the callback on completion.

        """
        def cb():
            if callable(callback):
                callback()

        self.stream.write(s, cb)


    def close(self):
        if self.stream is not None:
            self.stream.close()
        if self.sock is not None:
            self.sock.close()

    def read_frame(self, callback = None):
        """
        Read an AMQP frame, call the callback when you're done.

        """

        """
        Python can be deeply twisted, so in async code, just keep in mind that
        the least indented code is what happens first. Just because it's written
        further down the page doesn't mean it happens later.
        """
        def received_data(data):
            frame_type, channel, size = unpack('>BHI', data)
            def received_payload(payload):
                def received_ch(ch):
                    if ch == '\xce':
                        print "successfully read shit, calling back"
                        callback(frame_type, channel, payload)
                    else:
                        raise Exception(
                            'Framing Error, received 0x%02x while expecting 0xce' % ord(ch))
                self._read(1, received_ch)
            self._read(size, received_payload)
        self._read(7, received_data)

    def write_frame(self, frame_type, channel, payload, callback = None):
        """
        Write out an AMQP frame, call the callback when you're done.

        """
        size = len(payload)
        self._write(pack('>BHI%dsB' % size,
            frame_type, channel, size, payload, 0xce), callback)

class SSLTransport(_AbstractTransport):
    """
    Transport that works over SSL

    """
    def _setup_transport(self):
        """
        Wrap the socket in an SSL object, either the
        new Python 2.6 version, or the older Python 2.5 and
        lower version.

        """
        if HAVE_PY26_SSL:
            self.sock= ssl.wrap_socket(self.sock)
            self.sock.do_handshake()
        else:
            self.sock = socket.ssl(self.sock)

    def _write(self, *args, **kwargs):
        self.stream.write(*args, **kwargs)

    def _read(self, *args, **kwargs):
        self.stream.read(*args, **kwargs)



class TCPTransport(_AbstractTransport):
    """
    Transport that deals directly with TCP socket.

    """
    pass

def create_transport(host, connect_timeout, ssl=False):
    """
    Given a few parameters from the Connection constructor,
    select and create a subclass of _AbstractTransport.

    """
    IOThread.start()
    if ssl:
        return SSLTransport(host, connect_timeout)
    else:
        return TCPTransport(host, connect_timeout)
