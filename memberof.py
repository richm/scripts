import os
import sys
import time
import ldap
import tempfile
import shutil
from dsadmin import DSAdmin, Entry
import ldif

print "start"
host1 = "localhost.localdomain"
port1 = 1389
basedn = "dc=example,dc=com"
dom = 'example.com'
dnsdom = 'localdomain'

cfgfd = tempfile.NamedTemporaryFile(delete=False)
print "enable memberof"
dn1 = "cn=MemberOf Plugin,cn=plugins,cn=config"
cfgfd.write("""dn: %s
changetype: modify
replace: nsslapd-pluginEnabled
replace: nsslapd-pluginType
replace: memberofgroupattr
nsslapd-pluginEnabled: on
nsslapd-pluginType: betxnpostoperation
memberofgroupattr: member
memberofgroupattr: uniquemember
""" % dn1)
cfgfd.close()
os.chmod(cfgfd.name, 0644)

def addLDIF(conn, file, cont=False):
    class LDIFAdder(ldif.LDIFParser):
        def __init__(self, input_file, conn, cont=False,
                     ignored_attr_types=None,max_entries=0,process_url_schemes=None
                     ):
            myfile = input_file
            if isinstance(input_file,basestring):
                myfile = open(input_file, "r")
            self.conn = conn
            self.cont = cont
            ldif.LDIFParser.__init__(self,myfile,ignored_attr_types,max_entries,process_url_schemes)
            self.parse()
            if isinstance(input_file,basestring):
                myfile.close()

        def handle(self,dn,entry):
            if not dn:
                dn = ''
            newentry = Entry((dn, entry))
            if newentry.hasValueCase('objectclass', 'inetorgperson'):
                ocvals = newentry.getValues('objectclass')
                ocvals.append('inetUser')
                newentry.setValue('objectclass', ocvals)
            try: self.conn.add_s(newentry)
            except ldap.LDAPError, e:
                if not self.cont: raise e
                print "Error: could not add entry %s: error %s" % (dn, str(e))

    adder = LDIFAdder(file, conn, cont)        

os.environ['USE_GDB'] = '1'
ds = DSAdmin.createInstance({
	'newrootpw': 'password',
	'newhost': host1,
	'newport': port1,
	'newinst': 'ds',
	'newsuffix': basedn,
	'no_admin': True,
        'ConfigFile': [cfgfd.name],
        'InstallLdifFile': 'none'
})
os.unlink(cfgfd.name)

initfile = ''
if os.environ.has_key('SERVER_ROOT'):
    initfile = "%s/slapd-%s/ldif/Example.ldif" % (ds.sroot,ds.inst)
else:
    initfilesrc = "%s/share/dirsrv/data/Example.ldif" % os.environ.get('PREFIX', '/usr')
    initfile = "%s/var/lib/dirsrv/slapd-%s/ldif/Example.ldif" % (os.environ.get('PREFIX', ''), 'ds')
    shutil.copy(initfilesrc, initfile)
print "importing database"
addLDIF(ds, initfile, True)

print "get the list of all users"
ents = ds.search_s(basedn, ldap.SCOPE_SUBTREE, "memberof=*")
for ent in ents:
    print ent
