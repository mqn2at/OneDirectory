import json, os, re, MySQLdb
# from protocol import Protocol
from twisted.internet import protocol, reactor, inotify
from twisted.python import filepath
from shutil import rmtree
from datetime import datetime
from os.path import expanduser, getsize, isfile, join, exists

PORT = 2121
HOME = expanduser('~')

with open('password.txt') as f:
    db = MySQLdb.connect(host="dbm2.itc.virginia.edu", user="dlf3x", passwd=f.read().strip(), db="cs3240onedir")
db.autocommit(True)
cursor = db.cursor()

def adjustPath(path):
    index = path.find('onedir')
    return path[index:]

def getAbsolutePath(path, user):
    return '{0}/CS3240/{1}/{2}'.format(HOME, user, path)

# class ServerProtocol(Protocol):
#     def _getAbsolutePath(self, path, user):
#         return '{0}/CS3240/{1}/{2}'.format(HOME, user, path)        

class ServerProtocol(protocol.Protocol):
    def connectionMade(self):
        print 'Connected from ' + str(self.transport.getPeer().host)
        
    def dataReceived(self, data):
        print 'received ' + str(data)
        received = filter(None, re.split('({.*?})', data))
        for item in received:
            message = json.loads(item)
            self.dispatch(message)

    def dispatch(self, message):
        user = message['user']
        cmd = message['cmd']
        commands = {
            'create account' : self._handleCreateAccount,
            'touch' : self._handleTouch,
            'mkdir' : self._handleMkdir,
            'rm' : self._handleRm,
            'rmdir' : self._handleRmdir,
        }
        commands.get(cmd, lambda a, b: None)(message, user)

    def _handleTouch(self, message, user):
        path = message['path']
        absolute_path = getAbsolutePath(path, user)
        if not isfile(absolute_path):
            with open(absolute_path, 'a'):
                os.utime(absolute_path, None)

    def _handleCreateAccount(self, message, user):
        absolute_path = '{0}/CS3240/{1}/onedir'.format(HOME, user)
        if not exists(absolute_path):
            os.makedirs(absolute_path)

    def _handleMkdir(self, message, user):
        path = message['path']
        absolute_path = getAbsolutePath(path, user)
        if not exists(absolute_path):
            os.mkdir(absolute_path)

    def _handleRm(self, message, user):
        path = message['path']
        absolute_path = getAbsolutePath(path, user)
        if isfile(absolute_path):
            os.remove(absolute_path)
            
    def _handleRmdir(self, message, user):
        path = message['path']
        absolute_path = getAbsolutePath(path, user)
        if exists(absolute_path):
            rmtree(absolute_path)
    
class ServerFactory(protocol.ServerFactory):
    def __init__(self, path):
        self._path = filepath.FilePath(path)
        self._protocol = ServerProtocol()
        self._notifier = inotify.INotify()

    def startFactory(self):
        self._notifier.startReading()
        self._notifier.watch(self._path, autoAdd=True, callbacks=[self.onChange], recursive=True)

    def buildProtocol(self, addr):
        return self._protocol

    def onChange(self, watch, fpath, mask):
        index = fpath.path.find('onedir')
        path = fpath.path[index:]
        user = re.search('CS3240/(.*)/onedir', fpath.path).group(1)
        cmd = ' '.join(inotify.humanReadableMask(mask))
        self.dispatch(path, cmd, user)

    def dispatch(self, path, cmd, user):
        commands = {
            'create' : self._handleCreate,
            'create is_dir' : self._handleCreateDir,
            'delete' : self._handleDelete,
            'delete is_dir' : self._handleDeleteDir,
            # 'modify' : self._handleModify,
        }
        commands.get(cmd, lambda a, b: None)(path, user)

    def _handleCreate(self, path, user):
        data = json.dumps({
                'user' : user,
                'cmd' : 'touch',
                'path' : path,
            })
        cursor.execute("SELECT * FROM file WHERE path = %s AND user_id = %s", (path, user))
        if len(cursor.fetchall()) == 0:
            cursor.execute("INSERT INTO file VALUES (%s, %s, %s)", (path, user, 0))
            cursor.execute("INSERT INTO log VALUES (%s, %s, %s, %s)", (user, path, datetime.now(), 'create'))
            self._protocol.transport.write(data)

    def _handleCreateDir(self, path, user):
        data = json.dumps({
            'user' : user,
            'cmd' : 'mkdir',
            'path' : path,
            })
        self._protocol.transport.write(data)

    def _handleDelete(self, path, user):
        data = json.dumps({
            'user' : user,
            'cmd' : 'rm',
            'path' : path,
            })
        cursor.execute("SELECT * FROM file WHERE path = %s AND user_id = %s", (path, user))
        if len(cursor.fetchall()) > 0:
            cursor.execute("DELETE FROM file WHERE path = %s AND user_id = %s", (path, user))
            cursor.execute("INSERT INTO log VALUES (%s, %s, %s, %s)", (user, path, datetime.now(), 'delete'))
            self._protocol.transport.write(data)
        self._protocol.transport.write(data)

    def _handleDeleteDir(self, path, user):
        data = json.dumps({
                'user' : user,
                'cmd' : 'rmdir',
                'path' : path,
            })
        absolute_path = getAbsolutePath(path, None)
        for (fpath, _, files) in os.walk(absolute_path):
            cursor.execute("SELECT * FROM file WHERE path = %s AND user_id = %s", (adjustPath(join(fpath, files[0])), user))
            if len(cursor.fetchall()) == 0:
                return
            for f in files:
                final_path = adjustPath(join(fpath, f))
                cursor.execute("DELETE FROM file WHERE path = %s AND user_id = %s", (final_path, user))
                cursor.execute("INSERT INTO log VALUES (%s, %s, %s, %s)", (user, final_path, datetime.now(), 'delete'))
        self._protocol.transport.write(data)

def main():
    """Creates a factory and runs the reactor"""
    path = '{0}/CS3240'.format(HOME)
    factory = ServerFactory(path)
    reactor.listenTCP(PORT, factory)
    reactor.run()
        
if __name__ == "__main__":
    main()

db.close()