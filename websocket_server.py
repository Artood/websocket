from autobahn.twisted.websocket import WebSocketServerProtocol, \
    WebSocketServerFactory
import json, time
from twisted.internet import task

import win32com.client

XSSOWebSocketServerVersion = 'XSSO Webserver Socket Server 1.0/Py'
END_OUTPUT = '@end@'


# --------XSSOServerProtocol class------------------
class XSSOServerProtocol(WebSocketServerProtocol):
    LOCAL_CONNECTION_SIGNATURE = '1a6da227-d6d3-4953-8611-9bf975ca9703'

    def onConnect(self, request):
        custom_log("Client connecting: {0}".format(request.peer))

    def onOpen(self):
        # custom_log("WebSocket connection open.".format(self.websocket_extensions_in_use))
        self.write_json({'status': XSSOWebSocketServerVersion})

    def onMessage(self, payload, isBinary):
        if isBinary:
            custom_log("Binary message received: {0} bytes".format(len(payload)))
        else:
            # custom_log("Text message received: {0}".format(payload.decode('utf8')))
            self.parse(payload.decode('utf8'));

    def onClose(self, wasClean, code, reason):
        # custom_log("WebSocket connection closed: {0}".format(reason))
        self.factory.remove_user(self)

    #
    def parse(self, data):
        json_data = json.loads(data)
        if json_data['cmd'] == 'localconnection':
            if json_data['signature'] == self.LOCAL_CONNECTION_SIGNATURE:
                self.parse_localcontent(json_data['content'])
                return
        if json_data['cmd'] == 'connect':
            self.connect(json_data)
            return
        if json_data['cmd'] == 'check':
            self.check(json_data)
            return

        self.sendClose()

    #
    def connect(self, json_obj):
        checked = self.factory.VerifyAK(json_obj['ak'], json_obj['user_id']);
        if checked == True:
            req = {'cmd': 'connect', 'status': 'connected', \
                   'user_id': json_obj['user_id'], 'session_id': json_obj['session_id'], 'ip': '',
                   'net_id': json_obj['net_id']}
            self.factory.add_user(self, json_obj)
            self.write_json(req)
        else:
            self.write_status('failed')

    #
    def check(self, jo):
        req = {'cmd': 'check', 'status': 'connected', \
               'user_id': jo['user_id'], 'session_id': jo['session_id'], 'net_id': jo['net_id']}
        user_id = int(jo['user_id'])
        for u in self.factory.SOCKET_USERS:
            if self.factory.SOCKET_USERS[u]['user_id'] == user_id and u == jo['session_id']:
                self.factory.SOCKET_USERS[u]['connection'] = self
                self.write_json(req)
                return
        req['status'] = 'failed'
        self.write_json(req)
        self.sendClose()

    # local connection
    def parse_localcontent(self, json_content):
        # print("Local request:",json.dumps(json_content))

        if json_content['object'] == 'chat':
            self.write_status('connected')
            self.chat_notify(json_content)
            return

        if json_content['object'] == 'update_news':
            self.update_notify(json_content)
            return

        if json_content['object'] == 'userlist':
            self.userlist(json_content);
            return

        if json_content['object'] == 'stop':
            self.stop_server(json_content)
            return

        self.write_status('failed')

    #
    def chat_notify(self, json_data):
        chatreq = {'cmd': 'chat', 'user_id': json_data['initiator'], 'chat_id': json_data['chat_id'],
                   'net_id': json_data['net_id']}
        self.send_json_to_list(int(json_data['net_id']), json_data['userlist'], chatreq);

    #
    def update_notify(self, json_data):
        req = {'cmd': json_data['object'], 'user_id': json_data['initiator'], 'net_id': json_data['net_id']}
        self.send_json_to_list(int(json_data['net_id']), json_data['userlist'], req);

    #
    def stop_server(self, json_data):
        custom_log("Local request to stop server");
        secs = 10;
        stop_message = "Stopping server during " + str(secs) + " seconds..."
        print(stop_message);
        self.sendMessage(stop_message.encode('utf8'), False)
        reactor.callLater(secs, stop_socket_server)

    #
    def userlist(self, jo):
        custom_log("Local request to receive connected users");
        self.write_str("\n" + XSSOWebSocketServerVersion + "\n")
        self.write_str("\n--Users--:\n")
        nusers = 0
        for u in self.factory.SOCKET_USERS:
            user = self.factory.SOCKET_USERS[u]
            line = "user_id: " + str(user['user_id']) + ", net_id: " + str(user['net_id']) + ", ip: " + user[
                'ip'] + "\n";
            nusers += 1
            self.write_str(line)

        self.write_str("connected users: " + str(nusers) + "\n")
        self.write_str(END_OUTPUT)

    ###########################################3
    def write_json(self, json_data):
        self.sendMessage(json.dumps(json_data).encode('utf8'), False)

    #
    def write_status(self, status):
        self.write_json({'status': status})

    #
    def write_str(self, s):
        self.sendMessage(s.encode('utf8'), False)

    #
    def send_json_to_list(self, net_id, userlist, req):
        active_users = list(map(int, userlist.split(',')))
        custom_log("send_json_to_list:", active_users)
        send_number = len(active_users)
        for u in self.factory.SOCKET_USERS:
            for i in range(send_number):
                if self.factory.SOCKET_USERS[u]['user_id'] == active_users[i] and self.factory.SOCKET_USERS[u][
                    'net_id'] == net_id:
                    try:
                        # custom_log("send request to: ",active_users[i])
                        self.factory.SOCKET_USERS[u]['connection'].write_json(req)
                    except BaseException as error:
                        print('An exception occurred: {}'.format(error))


# -------------------XSSOServer class -----------------------

class XSSOWebSocketServerFactory(WebSocketServerFactory):

    def __init__(self, url):
        WebSocketServerFactory.__init__(self, url)
        self.SOCKET_USERS = {}
        self.groupfactor = win32com.client.Dispatch("GroupFactor.Crypto")
        custom_log("GroupFactor", self.groupfactor)

    def VerifyAK(self, ak, user_id):
        r = self.groupfactor.VerifyAccessKey(ak, user_id);
        if type(r) is str:
            return True
        if r == 0:
            return True
        return False

    def add_user(self, connection, jo):
        if jo['session_id'] in self.SOCKET_USERS.keys():
            self.SOCKET_USERS[jo['session_id']]['connection'] = connection
            return
        custom_log("User's session added: " + jo['session_id'] + " from " + jo['ip'])
        self.SOCKET_USERS[jo['session_id']] = {'user_id': int(jo['user_id']),
                                               'session_id': jo['session_id'],
                                               'connection': connection,
                                               'ip': jo['ip'],
                                               'net_id': int(jo['net_id'])
                                               }

    def remove_user(self, connection):
        for u in self.SOCKET_USERS:
            if self.SOCKET_USERS[u]['connection'] == connection:
                custom_log(
                    "user's session removed: " + self.SOCKET_USERS[u]['session_id'] + " from " + self.SOCKET_USERS[u][
                        'ip'])
                self.SOCKET_USERS.pop(u)
                custom_log("WebSocket connection closed")
                return


def stop_socket_server():
    custom_log(XSSOWebSocketServerVersion + " stopped")
    reactor.callFromThread(reactor.stop)


enable_screen_log = False


def custom_log(*args):
    if enable_screen_log:
        print(args)


if __name__ == '__main__':

    import sys

    from twisted.python import log
    from twisted.internet import reactor

    print(XSSOWebSocketServerVersion)

    port = 8000
    debug_log = ""
    enable_screen_log = False
    address = "127.0.0.1"

    # print(f"Arguments count: {len(sys.argv)}")
    for i, arg in enumerate(sys.argv):
        param = list(arg.split('='))
        if len(param) == 2:
            param[0] = param[0].lower()
            if param[0] == 'enable_screen_log':
                if param[1].lower() == 'true':
                    enable_screen_log = True

            if param[0] == 'port':
                port = int(param[1])

            if param[0] == 'address':
                address = param[1]

            if param[0] == 'debug_log':
                debug_log = param[1]

    if debug_log != "":
        if debug_log == "stdout":
            log.startLogging(sys.stdout)
        else:
            log.startLogging(open(debug_log, 'a'))

    factory = XSSOWebSocketServerFactory("ws://" + address + ":" + str(port))
    factory.protocol = XSSOServerProtocol
    # factory.setProtocolOptions(maxConnections=2)

    reactor.listenTCP(port, factory)
    reactor.run()
