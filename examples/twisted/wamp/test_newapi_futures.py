from __future__ import print_function

from os import urandom
import hmac
import hashlib
from base64 import b64encode

from twisted.internet import reactor, task
from twisted.internet.defer import inlineCallbacks, DeferredList
from autobahn.twisted.wamp import Connection
from autobahn.twisted.util import sleep
from autobahn.wamp.exception import ApplicationError

import txaio


_private_key = b'123456789012345678901234567890AA'
_users = dict()

def _activate_token(token):
    print("Activating token:", b64encode(token))
    alleged_sig = hmac.new(_private_key, token, hashlib.sha256).digest()
    (user, sig) = _users.get(token, ("invalid", b'0'*32))
    if sig != alleged_sig:
        raise ApplicationError(u"com.example.invalid_token", u"Token is not valid")
    # do whatever to create user
    print("  created user:", user)
    return user

@inlineCallbacks
def public_api(session):#connection):
    #print('public_api', connection)
    #session = connection.session
    # db = yield connect_to_database()
    print('public_api, connected on realm', session.config.realm)

    details = yield session.joined
    print("public_api joined, session_id={details.session}".format(details=details))
    yield session.register(_activate_token, u"com.example.activate")

    def quit():
        session.leave()
    yield session.register(quit, u"com.example.quit")
    yield session.publish(u"com.example.public_api.ready")

    details = yield session.left
    print("public_api completed: {details.reason}".format(details=details))


def _create_token(user):
    print("create_token", user)
    if user in _users:
        raise ApplicationError("com.example.invalid_token", "The token is invalid")
    #raise Exception("Duplicate user '{}'".format(user))

    nonce = urandom(32)
    sig = hmac.new(_private_key, nonce, hashlib.sha256).digest()
    _users[nonce] = (user, sig)
    return nonce


@inlineCallbacks
def backend_api(session):#connection):
    print('backend_api, connected on realm', session.config.realm)
    #session = connection.session

    details = yield session.joined
    print("backend_api joined, session_id={details.session}".format(details=details))
    yield session.register(_create_token, u"com.example.private.create_token")
    yield session.publish(u"com.example.private.ready")

    def quit():
        session.leave()
    yield session.register(quit, u"com.example.private.quit")
    details = yield session.left
    print("backend_api completed:", details.reason)

@inlineCallbacks
def simulate_client(session):#connection):
    #session = connection.session
    yield session.joined
    print("simluated client joined; waiting 1 second")
    yield sleep(1)
    print("  . calling private and public APIs:")
    token = yield session.call(u"com.example.private.create_token", "meejah@example.com")
    user = yield session.call(u"com.example.activate", token)
    print("  . succeess: created user '{}'".format(user))

    token = urandom(32)
    try:
        print("  . trying to activate invalid token (should get error):")
        user = yield session.call(u"com.example.activate", token)
    except Exception as e:
        print("  . Error (expected): {}".format(e))
    if False:
        print("Done. stopping reactor")
        from twisted.internet import reactor
        reactor.stop()
    else:
        session.call(u"com.example.private.quit")
        session.call(u"com.example.quit")
        yield session.leave()

@inlineCallbacks
def run(reactor, entry_points):
    transports = [
        {
            "type": "websocket",
            "url": u"ws://127.0.0.1:8080/ws"
        }
    ]

    connections = []
    for main in entry_points:
        # print("entry:", main)
        connections.append(
            Connection(
                transports,
                main=main,
                realm=u'realm1',
                loop=reactor,
            )
        )

    res = yield DeferredList([c.open() for c in connections])
    print("all connections done", res)
    reactor.stop()


if __name__ == '__main__':
    args = ([public_api, backend_api, simulate_client], )
    txaio.start_logging(level='debug')
    task.react(run, args)