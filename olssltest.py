import sys
import shutil
import errno
import re
import os, os.path
import ldap
import ldif
import time
from subprocess import Popen, PIPE, STDOUT
import olserver

src = sys.argv[1]
srchostname = sys.argv[2]
srcport = int(sys.argv[3])
cafile = sys.argv[4]
cert = sys.argv[5]
key = sys.argv[6]
basedn = "dc=example,dc=com"
rootdn = "cn=manager," + basedn
rootpw = "secret"

rootdir = os.path.dirname(os.path.dirname(os.path.dirname(src)))

olserver.setupserver(rootdir, rootpw)
olserver.createscript(src, srcport, srchostname)
olserver.startserver(src, srcport, True)
print "wait for server to be up and listening"
time.sleep(1)
print "open conection to server"
srv1url = "ldap://%s:%d" % (srchostname, srcport)
srv1 = ldap.initialize(srv1url)
srv1.simple_bind_s("cn=config", rootpw)
olserver.addschema(srv1, rootdir, ['core', 'cosine', 'inetorgperson', 'openldap', 'nis'])
olserver.addbackend(srv1, rootdir, rootpw, basedn)
olserver.setuptls(srv1, cafile, None, cert, key)
