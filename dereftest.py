import os
import sys
import time
import ldap
from ldap.controls import LDAPControl
from ldap.ldapobject import LDAPObject
import struct
import pprint
import derefctrl
from dsadmin import DSAdmin, Entry

host1 = "vmhost"
cfgport = 1100
port1 = cfgport + 30

basedn = 'dc=example,dc=com'
newinst = 'srv'
#os.environ['USE_GDB'] = "1"
srv = DSAdmin.createInstance({
	'newrootpw': 'password',
	'newhost': host1,
	'newport': port1,
	'newinst': newinst,
	'newsuffix': basedn,
    'no_admin': True
})

ldiffile = os.environ["PREFIX"] + "/share/dirsrv/data/Example-roles.ldif"
srv.importLDIF(ldiffile,basedn)

#srv = DSAdmin(host1, port1, "cn=directory manager", "password")

srv.set_option(ldap.OPT_DEBUG_LEVEL, 1)
# create a group containing all users
entsbydn = {}
ents = srv.search_s(basedn, ldap.SCOPE_SUBTREE, "uid=*")
for ent in ents:
    entsbydn[ent.dn] = ent

groupent = Entry("cn=everyone," + basedn)
groupent.setValues('objectclass', 'top', 'groupOfNames')
groupent.setValues("member", entsbydn.keys())
try: srv.add_s(groupent)
except: ldap.ALREADY_EXISTS

# as root, do a deref search of cn=everyone, deref
# the member attr, and return uid, roomNumber, nsRoleDN
# and nsRole
derefspeclist = (
    ('member', ('uid', 'roomNumber', 'nsRoleDN', 'nsRole'))
    ,)

dc = derefctrl.DerefCtrl(derefspeclist,False)
serverctrls = [dc]
filter = "objectclass=*"
attrlist = ['cn']
msgid = srv.search_ext(groupent.dn, ldap.SCOPE_BASE, filter, attrlist, 0, serverctrls)
while True:
    rtype, rdata, rmsgid, decoded_serverctrls, rspoid, rspval = srv.result4(msgid, 0, -1, 1)
    print "Search returned %d results" % len(rdata)
    pprint.pprint(decoded_serverctrls)
    for dn, ent, ctrls in rdata:
        pprint.pprint(ent)
        for oid,crit,val in ctrls:
            if oid == dc.controlType:
                dc.decodeControlValue(val)
                pprint.pprint(dc.dereflist)
        print ""
    if rtype == ldap.RES_SEARCH_RESULT:
        break
