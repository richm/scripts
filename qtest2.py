import sys
import time
import pprint
import json
from qpid.messaging import *

broker = "localhost:5672"
#address = "nova"
address = "notifications.info"

connection = Connection(broker)

connection.open()

session = connection.session()

receiver = session.receiver(address)

while True:
    message = receiver.fetch()
    session.acknowledge(message)
    msg = message.content
    if isinstance(msg, dict):
        if 'oslo.message' in msg:
            msg = json.loads(msg['oslo.message'])

    pprint.pprint(msg)
    print ""
    sys.stdout.flush()
