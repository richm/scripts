url = "ldap://localhost:1130/"
base = "cn=everyone,dc=example,dc=com"
search_flt = r'(objectClass=*)'

import ldap,pprint
import derefctrl

searchreq_attrlist=['cn']

#ldap.set_option(ldap.OPT_DEBUG_LEVEL,255)
ldap.set_option(ldap.OPT_REFERRALS, 0)
l = ldap.initialize(url,trace_level=1)
l.protocol_version = 3
l.simple_bind_s("cn=directory manager", "password")

derefspeclist = (
    ('member', ('uid', 'roomNumber', 'nsRoleDN', 'nsRole'))
    ,)

lc = derefctrl.DerefCtrl(derefspeclist)

# Send search request
msgid = l.search_ext(
  base,
  ldap.SCOPE_BASE,
  search_flt,
  attrlist=searchreq_attrlist,
  serverctrls=[lc]
)

while True:
    rtype, rdata, rmsgid, serverctrls = l.result3(msgid)
    print '%d results' % len(rdata)
    pprint.pprint(rdata)
    pprint.pprint(serverctrls)
    if rtype == ldap.RES_SEARCH_RESULT:
        break
