"""
Thread that sits in an IO loop waiting for things to happen.

"""

# Copyright (C) 2009 Justin Tulloss <justin@harmonize.fm>
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

from threading import Thread
import ioloop

class IOThread(object):
    def __init__(self):
        self.thread = Thread(None, self, "AMQP IO Thread")
        self.thread.daemon = True
        self.thread.start()

    def __del__(self):
        ioloop.IOLoop.instance().stop()

    @classmethod
    def start(cls):
        if not hasattr(cls, '_instance'):
            cls._instance = cls()
        return True

    def __call__(self):
        ioloop.IOLoop.instance().start()
