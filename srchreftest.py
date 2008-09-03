
import os
import time
import ldap
from dsadmin import DSAdmin, Entry

host = "localhost.localdomain"
port = 10200

#os.environ['USE_DBX'] = "1"
#del os.environ['USE_DBX']

binddn = "cn=directory manager"
bindpw = "secret12"
conn = DSAdmin(host,port,binddn,bindpw)

suffix = "dc=example2,dc=com"
conn.addSuffix(suffix)

initfile = "/var/tmp/reftest.ldif"
conn.importLDIF(initfile, suffix, None, True)
