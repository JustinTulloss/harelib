"""
AMQP Library

2007-11-05 Barry Pederson <bp@barryp.org>

"""
from calendar import timegm
from datetime import datetime
import socket
from struct import pack, unpack
try:
    from cStringIO import StringIO
except:
    from StringIO import StringIO


AMQP_PORT = 5672
AMQP_PROTOCOL_HEADER = 'AMQP\x01\x01\x09\x01'


def hexdump(s):
    while s:
        x, s = s[:16], s[16:]
        for ch in x:
            print '0x%02x ' % ord(ch),
        print ''


class _AMQPReader(object):
    """
    Parse data from AMQP

    """
    def __init__(self, source):
        """
        source should be either a file-like object with a read() method, or
        a plain (non-unicode) string.

        """
        if isinstance(source, str):
            self.input = StringIO(source)
        elif hasattr(source, 'read'):
            self.input = source
        else:
            raise ValueError('_AMQPReader needs a file-like object or plain string')

    def read(self, n):
        return self.input.read(n)

    def read_octet(self):
        return unpack('B', self.input.read(1))[0]

    def read_short(self):
        return unpack('>H', self.input.read(2))[0]

    def read_long(self):
        return unpack('>I', self.input.read(4))[0]

    def read_longlong(self):
        return unpack('>Q', self.input.read(8))[0]

    def read_shortstr(self):
        len = unpack('B', self.input.read(1))[0]
        return self.input.read(len).decode('utf-8')

    def read_longstr(self):
        len = unpack('>I', self.input.read(4))[0]
        return self.input.read(len)

    def read_table(self):
        len = unpack('>I', self.input.read(4))[0]
        table_data = _AMQPReader(self.input.read(len))
        result = {}
        while table_data.input.tell() < len:
            name = table_data.read_shortstr()
            ftype = table_data.input.read(1)
            if ftype == 'S':
                val = table_data.read_longstr()
            elif ftype == 'I':
                val = unpack('i', table_data.input.read(4))[0]
            elif ftype == 'D':
                d = table_data.read_octet()
                n = table_data.read_long()
                val = decimal(n) / decimal(10 ** d)
            elif ftype == 'T':
                val = datetime.fromtimestamp(table_data.read_longlong())
                ## FIXME: timezone ?
            elif ftype == 'F':
                val = table_data.read_table() # recurse
            result[name] = val
        return result

class _AMQPWriter(object):
    def __init__(self):
        self.out = StringIO()

    def getvalue(self):
        return self.out.getvalue()

    def write(self, s):
        self.out.write(s)

    def write_octet(self, n):
        self.out.write(pack('B', n))

    def write_short(self, n):
        self.out.write(pack('>H', n))

    def write_long(self, n):
        self.out.write(pack('>I', n))

    def write_longlong(self, n):
        self.out.write(pack('>Q', n))

    def write_shortstr(self, s):
        if isinstance(s, unicode):
            s = s.encode('utf-8')
        if len(s) > 255:
            raise ValueError('String too long')
        self.write_octet(len(s))
        self.out.write(s)

    def write_longstr(self, s):
        if isinstance(s, unicode):
            s = s.encode('utf-8')
        self.write_long(len(s))
        self.out.write(s)

    def write_table(self, d):
        table_data = _AMQPWriter()
        for k, v in d.items():
            table_data.write_shortstr(k)
            if isinstance(v, basestring):
                if isinstance(v, unicode):
                    v = v.encode('utf-8')
                table_data.write('S')
                table_data.write_longstr(v)
            elif isinstance(v, [int, long]):
                table_data.write('I')
                table_data.write(pack('>i', v))
            elif isinstance(v, decimal):
                table_data.write('D')
                table_data.write_octet(4)
                table_data.write_long(int(v * 10))
            elif isinstance(v, datetime):
                table_data.write('T')
                table_data.write_longlong(v, long(timegm(v.timetuple)))
                ## FIXME: timezone ?
            elif isinstance(v, dict):
                table_data.write('F')
                table_data.write_table(v)
        table_data = table_data.getvalue()
        self.write_long(len(table_data))
        self.out.write(table_data)


class Connection(object):
    """
    An AMQP Connection

    """

    def __init__(self, host):
        self.channels = {}
        self.input = self.out = None

        if ':' in host:
            host, port = host.split(':', 1)
            port = int(port)
        else:
            port = AMQP_PORT

        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.connect((host, port))
        self.input = _AMQPReader(sock.makefile('r'))
        self.out = sock.makefile('w')
        self.out.write(AMQP_PROTOCOL_HEADER)
        self.out.flush()
        self.waiting = True
        while self.waiting:        
            self.wait()

    def __del__(self):
        if self.input is not None:
            self.close()

    def channel(self, channel_id):
        ch = self.channels.get(channel_id, None)
        if ch is None:
            self.channels[channel_id] = ch = Channel(self, channel_id)
        ch.open()
        return ch

    def close(self, reply_code=0, reply_text='', class_id=0, method_id=0):
        args = _AMQPWriter()
        args.write_short(reply_code)
        args.write_shortstr(reply_text)
        args.write_short(class_id)
        args.write_short(method_id)
        self.send_method_frame(0, 10, 60, args.getvalue())
        self.wait()
        
    def close_ok(self, args):
        self.input = self.out = None
        print 'Closed Connection!'

    def open(self, virtual_host, capabilities='', insist=False):
        args = _AMQPWriter()
        args.write_shortstr(virtual_host)
        args.write_shortstr(capabilities)
        args.write_octet(1 if insist else 0)
        self.send_method_frame(0, 10, 40, args.getvalue())
        
    def open_ok(self, args):
        self.known_hosts = args.read_shortstr()
        print 'Open OK! known_hosts [%s]' % self.known_hosts
        self.waiting = False

    def start(self, args):
        version_major = args.read_octet()
        version_minor = args.read_octet()
        properties = args.read_table()
        mechanisms = args.read_longstr().split(' ')
        locales = args.read_longstr().split(' ')
        print 'Start from server, version: %d.%d, properties: %s, mechanisms: %s, locales: %s' % (version_major, version_minor, str(properties), mechanisms, locales)

        login = _AMQPWriter()
        login.write_table({"LOGIN": "guest", "PASSWORD": "guest"})
        login = login.getvalue()[4:]    #Skip the length at the beginning

        self.start_ok({'product': 'Python AMQP', 'version': '0.1'}, 'AMQPLAIN', login, 'en_US')

    def start_ok(self, client_properties, mechanism, response, locale):
        args = _AMQPWriter()
        args.write_table(client_properties)
        args.write_shortstr(mechanism)
        args.write_longstr(response)
        args.write_shortstr(locale)
        self.send_method_frame(0, 10, 11, args.getvalue())

    def send_method_frame(self, channel, class_id, method_id, packed_args):
        pkt = _AMQPWriter()
        pkt.write_octet(1)
        pkt.write_short(channel)
        pkt.write_long(len(packed_args)+4)
        pkt.write_short(class_id)
        pkt.write_short(method_id)
        pkt.write(packed_args)
        pkt.write_octet(0xce)
        pkt = pkt.getvalue()
#        hexdump(pkt)
        self.out.write(pkt)
        self.out.flush()

    def tune(self, args):
        self.channel_max = args.read_short()
        self.frame_max = args.read_long()
        self.heartbeat = args.read_short()
        self.tune_ok(self.channel_max, self.frame_max, 0)

    def tune_ok(self, channel_max, frame_max, heartbeat):
        args = _AMQPWriter()
        args.write_short(channel_max)
        args.write_long(frame_max)
        args.write_short(heartbeat)
        self.send_method_frame(0, 10, 31, args.getvalue())
        self.open('/')

    def wait(self):
        """
        Wait for a frame from the server

        """
        frame_type = self.input.read_octet()
        channel = self.input.read_short()
        size = self.input.read_long()
        print 'frame_type: %d, channel: %d, size: %d' % (frame_type, channel, size)
        payload = self.input.read(size)

        ch = self.input.read_octet()
        if ch != 0xce:
            raise Exception('Framing error, unexpected byte: %x' % ch)

        if frame_type == 1:
            self.dispatch_method(channel, payload)

    def dispatch_method(self, channel, payload):
        if len(payload) < 4:
            raise Exception('Method frame too short')
        class_id, method_id = unpack('>HH', payload[:4])
        args = _AMQPReader(payload[4:])
    
        if class_id == 10:
            return self.dispatch_method_connection(method_id, args)
        if class_id == 20:
            ch = self.channels[channel]
            return ch.dispatch_method(method_id, args)
            
    def dispatch_method_connection(self, method_id, args):          
        if method_id == 10:
            return self.start(args)
        elif method_id == 30:
            return self.tune(args)
        elif method_id == 41:
            return self.open_ok(args)
        elif method_id == 61:
            return self.close_ok(args)
        print 'unknown connection method_id:', method_id


class Channel(object):
    def __init__(self, connection, channel_id):
        print 'channels:', connection.channels
        self.connection = connection
        self.channel_id = channel_id
        self.is_open = False

    def __del__(self):
        if self.connection:
            self.close(msg='destroying channel')

    def close(self, reply_code=0, reply_text='', class_id=0, method_id=0):
        args = _AMQPWriter()
        args.write_short(reply_code)
        args.write_shortstr(reply_text)
        args.write_short(class_id)
        args.write_short(method_id)
        self.send_method_frame(40, args.getvalue())
        self.connection.wait()
        
    def close_ok(self, args):
        self.is_open = False
        print 'Closed Channel!'
    
    def open(self, out_of_band=''):
        if not self.is_open:
            args = _AMQPWriter()
            args.write_shortstr(out_of_band)
            self.send_method_frame(10, args.getvalue())
            self.connection.wait()
        
    def open_ok(self, args):
        self.is_open = True
        print 'Channel open'
        
    def dispatch_method(self, method_id, args):
        if method_id == 11:
            return self.open_ok(args)
        if method_id == 41:
            return self.close_ok(args)
        print 'Unknown channel method: ', method_id
        
    def send_method_frame(self, method_id, packed_args):
        self.connection.send_method_frame(self.channel_id, 20, method_id, packed_args)
        




AMQP_METHODS = {
    10: {
        10: Connection.start,
        },
    20: {
        },
    }



def main():
    conn = Connection('10.66.0.8')
    ch = conn.channel(1)
#    ch.basic_publish('hello world')
    ch.close()
    conn.close()

if __name__ == '__main__':
    main()