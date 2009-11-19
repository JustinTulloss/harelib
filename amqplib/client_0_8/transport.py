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
import iostream
import ioloop

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

        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(connect_timeout)

        try:
            sock.connect((host, port))
        except socket.error:
            sock.close()
            raise
        sock.settimeout(None)

        self.stream = IOStream(sock)

        self._setup_transport()

        self._write(AMQP_PROTOCOL_HEADER)

        ioloop.IOLoop.instance().start()

    def __del__(self):
        self.close()


    def _read(self, n, callback = None):
        """
        Read exactly n bytes from the peer, call back when you're done.

        """
        raise NotImplementedError('Must be overriden in subclass')


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
        raise NotImplementedError('Must be overriden in subclass')


    def close(self):
        if self.stream is not None:
            self.stream.close()
            ioloop.IOLoop.instance().stop()

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
                        callback(frame_type, channel, payload)
                    else:
                        raise Exception(
                            'Framing Error, received 0x%02x while expecting 0xce' % ord(ch))
                self._read(1, received_ch)
            self._read(size, received_payload)
        self._read(7, received_data))

    def write_frame(self, frame_type, channel, payload, callback = None):
        """
        Write out an AMQP frame, call the callback when you're done.

        """
        size = len(payload)
        self._write(pack('>BHI%dsB' % size,
            frame_type, channel, size, payload, 0xce))


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
            self.sslobj = ssl.wrap_socket(self.sock)
            self.sslobj.do_handshake()
        else:
            self.sslobj = socket.ssl(self.sock)


    def _read(self, n):
        """
        It seems that SSL Objects read() method may not supply as much
        as you're asking for, at least with extremely large messages.
        somewhere > 16K - found this in the test_channel.py test_large
        unittest.

        """
        result = self.sslobj.read(n)

        while len(result) < n:
            s = self.sslobj.read(n - len(result))
            if not s:
                raise IOError('Socket closed')
            result += s

        return result


    def _write(self, s):
        """
        Write a string out to the SSL socket fully.

        """
        while s:
            n = self.sslobj.write(s)
            if not n:
                raise IOError('Socket closed')
            s = s[n:]



class TCPTransport(_AbstractTransport):
    """
    Transport that deals directly with TCP socket.

    """
    def _setup_transport(self):
        """
        Setup to _write() directly to the socket, and
        do our own buffered reads.

        """
        self._write = self.stream.write
        self._read = self.stream.read

def create_transport(host, connect_timeout, ssl=False):
    """
    Given a few parameters from the Connection constructor,
    select and create a subclass of _AbstractTransport.

    """
    if ssl:
        return SSLTransport(host, connect_timeout)
    else:
        return TCPTransport(host, connect_timeout)
