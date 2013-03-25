from dsadmin import Entry
import dsadmin
from nose import SkipTest
from nose.tools import raises

import logging
logging.basicConfig(level=logging.DEBUG)
log = logging.getLogger(__name__)


class TestEntry(object):

    def test_init_empty(self):
        e = Entry('')
        assert not e.dn

    def test_init_with_str(self):
        e = Entry('o=pippo')
        assert e.dn == 'o=pippo'

    @raises(ValueError)
    def test_init_badstr(self):
        # This should not be allowed
        e = Entry('no equal sign here')

    def test_init_with_tuple(self):
        t = ('o=pippo', {
             'o': ['pippo'],
             'objectclass': ['organization', 'top']
             })
        e = Entry(t)
        assert e.dn == 'o=pippo'
        assert 'pippo' in e.o

    def test_update(self):
        t = ('o=pippo', {
             'o': ['pippo'],
             'objectclass': ['organization', 'top']
             })

        e = Entry(t)
        e.update({'cn': 'pluto'})
        assert e.cn == 'pluto'

    @SkipTest # is there a way to compare two entries?
    def test_update_complex(self):
        nsuffix, replid, replicatype = "dc=example,dc=com", 5, dsadmin.REPLICA_RDWR_TYPE
        binddnlist, legacy = ['uid=pippo, cn=config'], 'off'
        dn = "dc=example,dc=com"
        entry = Entry(dn)
        entry.setValues(
            'objectclass', "top", "nsds5replica", "extensibleobject")
        entry.setValues('cn', "replica")
        entry.setValues('nsds5replicaroot', nsuffix)
        entry.setValues('nsds5replicaid', str(replid))
        entry.setValues('nsds5replicatype', str(replicatype))
        entry.setValues('nsds5flags', "1")
        entry.setValues('nsds5replicabinddn', binddnlist)
        entry.setValues('nsds5replicalegacyconsumer', legacy)

        uentry = Entry((
            dn, {
            'objectclass': ["top", "nsds5replica", "extensibleobject"],
            'cn': "replica",
            })
        )
        # Entry.update *replaces*, so be careful with multi-valued attrs
        uentry.update({
            'nsds5replicaroot': nsuffix,
            'nsds5replicaid': str(replid),
            'nsds5replicatype': str(replicatype),
            'nds5flags': '1',
            'nsds5replicabinddn': binddnlist,
            'nsds5replicalegacyconsumer': legacy
        })

        log.info("Mismatching entries %r vs %r" % (uentry, entry))
