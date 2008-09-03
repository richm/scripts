
import os
import time
import ldap
import ldif
import tempfile
from dsadmin import DSAdmin, Entry

host1 = "localhost.localdomain"
host2 = host1
cfgport = 1100
port1 = cfgport + 30
port2 = port1 + 10

#os.environ['USE_DBX'] = "1"
m1 = DSAdmin.createInstance({
	'newrootpw': 'password',
	'newhost': host1,
	'newport': port1,
	'newinst': 'm1',
	'newsuffix': 'dc=example,dc=com',
	'verbose': True,
    'no_admin': True
})
#del os.environ['USE_DBX']

initfile = ''
if os.environ.has_key('SERVER_ROOT'):
    initfile = "%s/slapd-%s/ldif/Example.ldif" % (m1.sroot,m1.inst)
else:
    initfile = "%s/share/dirsrv/data/Example.ldif" % os.environ.get('PREFIX', '/usr')

print "add index for uidNumber attribute"
m1.addIndex("dc=example,dc=com", "uidNumber", ('eq', 'pres'), ('integerOrderingMatch'))
#m1.addIndex("dc=example,dc=com", "gidNumber", 'eq', 'pres')

print "add a new integer syntax attribute with an ORDERING integerOrderingMatch"
m1.addAttr("( 2.16.840.1.113730.3.1.99999999 NAME 'myintattr' DESC 'my integer attribute' EQUALITY integerMatch ORDERING integerOrderingMatch SYNTAX 1.3.6.1.4.1.1466.115.121.1.27 SINGLE-VALUE )")
print "add a new objectclass to use the new attribute"
m1.addObjClass("( 2.16.840.1.113730.3.2.99999999 NAME 'myintobjclass' DESC 'my integer objectclass' SUP top AUXILIARY MAY myintattr )")
print "add index for myintattr attribute"
m1.addIndex("dc=example,dc=com", "myintattr", ('eq', 'pres'))

print "fix the file %s to add the posixSchema for the uidNumber attribute" % initfile

class AddPosix(ldif.LDIFParser):
    def __init__(
        self,
        input_file,
        output_file,
        startuid,
        ignored_attr_types=None,max_entries=0,process_url_schemes=None
    ):
        """
        See LDIFParser.__init__()
        
        Additional Parameters:
        all_records
        List instance for storing parsed records
        """
        self.uidNumber = startuid
        self.output_file = output_file
        myfile = input_file
        if isinstance(input_file,str) or isinstance(input_file,unicode):
            myfile = open(input_file, "r")
        ldif.LDIFParser.__init__(self,myfile,ignored_attr_types,max_entries,process_url_schemes)
        self.parse()
        if isinstance(input_file,str) or isinstance(input_file,unicode):
            myfile.close()

    def handle(self,dn,entry):
        """
        Append single record to dictionary of all records.
        """
        if not dn:
            dn = ''
        newentry = Entry((dn, entry))
        objclasses = newentry.getValues('objectclass')
        if 'inetOrgPerson' in objclasses:
            print "adding posixAccount to ", dn
            objclasses.append('posixAccount')
            objclasses.append('myintobjclass')
            newentry.setValue('objectclass', objclasses)
            newentry.setValue('uidNumber', str(self.uidNumber))
            newentry.setValue('gidNumber', str(self.uidNumber))
            newentry.setValue('homeDirectory', '/home/foo')
            newentry.setValue('myintattr', str(self.uidNumber))
            self.uidNumber = self.uidNumber + 1
        print>>self.output_file, str(newentry)

ntf = tempfile.NamedTemporaryFile()
ap = AddPosix(initfile, ntf.file, -50)
ntf.file.close()

print "The last uidNumber is ", ap.uidNumber

print "import the ldif file"
m1.importLDIF(ntf.name, '', "userRoot", True)

