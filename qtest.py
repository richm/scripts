from oslo.config import cfg
from designate.openstack.common import log as logging
from oslo import messaging
import pprint
import sys
from designate import utils


CONF = cfg.CONF


class NotificationEndpoint(object):
    def warn(self, ctxt, publisher_id, event_type, payload, metadata):
        print "warn"
        pprint.pprint(payload)
	sys.stdout.flush()

    def error(self, ctxt, publisher_id, event_type, payload, metadata):
        print "error"
        pprint.pprint(payload)
	sys.stdout.flush()

    def audit(self, ctxt, publisher_id, event_type, payload, metadata):
        print "audit"
        pprint.pprint(payload)
	sys.stdout.flush()

    def debug(self, ctxt, publisher_id, event_type, payload, metadata):
        print "debug"
        pprint.pprint(payload)
	sys.stdout.flush()

    def info(self, ctxt, publisher_id, event_type, payload, metadata):
        print "info"
        pprint.pprint(payload)
	sys.stdout.flush()

    def critical(self, ctxt, publisher_id, event_type, payload, metadata):
        print "critical"
        pprint.pprint(payload)
	sys.stdout.flush()

    def sample(self, ctxt, publisher_id, event_type, payload, metadata):
        print "sample"
        pprint.pprint(payload)
	sys.stdout.flush()


TRANSPORT_ALIASES = {
    'designate.openstack.common.rpc.impl_kombu': 'rabbit',
    'designate.openstack.common.rpc.impl_qpid': 'qpid',
    'designate.openstack.common.rpc.impl_zmq': 'zmq',
    'designate.rpc.impl_kombu': 'rabbit',
    'designate.rpc.impl_qpid': 'qpid',
    'designate.rpc.impl_zmq': 'zmq',
}

utils.read_config('designate', sys.argv)
logging.setup('designate')

transport = messaging.get_transport(cfg.CONF, aliases=TRANSPORT_ALIASES)
targets = [
    messaging.Target(exchange='nova', topic='notifications'),
    messaging.Target(exchange='neutron', topic='notifications')
]
endpoints = [
    NotificationEndpoint()
]
server = messaging.get_notification_listener(transport, targets, endpoints)
server.start()
server.wait()
