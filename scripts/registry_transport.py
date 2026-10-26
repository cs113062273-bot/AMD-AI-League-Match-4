"""Thread-local, certificate-validating HTTPS connections for immutable blob ranges."""
import http.client
import threading
from urllib.parse import urlsplit


class RangeConnections:
    def __init__(self,context,timeout=45):
        self.context=context
        self.timeout=timeout
        self.local=threading.local()
        self.connections=set()
        self.lock=threading.Lock()

    def reset(self):
        connection=getattr(self.local,'connection',None)
        if connection:
            connection.close()
            with self.lock:self.connections.discard(connection)
        self.local.connection=None

    def open(self,url,headers):
        parsed=urlsplit(url)
        if parsed.scheme!='https' or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError('HTTPS blob endpoint required')
        key=(parsed.hostname,parsed.port or 443)
        connection=getattr(self.local,'connection',None)
        if connection is None or getattr(self.local,'key',None)!=key:
            self.reset()
            connection=http.client.HTTPSConnection(*key,timeout=self.timeout,context=self.context)
            self.local.connection=connection;self.local.key=key
            with self.lock:self.connections.add(connection)
        target=(parsed.path or '/')+('?' + parsed.query if parsed.query else '')
        connection.request('GET',target,headers={'Accept-Encoding':'identity',**headers})
        return connection.getresponse()

    def close(self):
        with self.lock:
            for connection in self.connections:connection.close()
            self.connections.clear()
