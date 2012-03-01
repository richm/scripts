
import ldap
from ldap.schema import SubSchema
import ldif
import sys
import pprint

class SchemaChk(ldif.LDIFParser, SubSchema):
    def __init__(
        self,
        input_file,
        ignored_attr_types=None,max_entries=0,process_url_schemes=None
    ):
        """
        See LDIFParser.__init__()
        
        Additional Parameters:
        all_records
        List instance for storing parsed records
        """
        self.input_file = input_file
        self.entry = None
        myfile = open(input_file, "r")
        ldif.LDIFParser.__init__(self,myfile,ignored_attr_types,max_entries,process_url_schemes)
        self.parse()
        myfile.close()
        try:
            SubSchema.__init__(self,self.entry)
        except:
            print "Error reading entry in file", input_file
            if self.entry:
                pprint.pprint(self.entry)
                raise
    def handle(self,dn,entry):
        """
        Append single record to dictionary of all records.
        """
        self.entry = entry

# read and parse each schema file given on the command line
allattrs = ldap.cidict.cidict()
allocs = ldap.cidict.cidict()
alloids = {}
attrclass = ldap.schema.models.AttributeType
occlass = ldap.schema.models.ObjectClass
oldattrswithaliases = {}
sys.argv.pop(0)
while len(sys.argv) > 0:
    myfile = sys.argv.pop(0)
    if myfile == 'NEW': break
    sc = SchemaChk(myfile)
    for oid in sc.listall(attrclass):
        at = sc.get_obj(attrclass, oid)
        if len(at.names) > 1:
            oldattrswithaliases[oid] = at.names

#print "these are the old attrs with aliases:"
#for oid in attrswithaliases:
#    print oid

newattrs = []
while len(sys.argv) > 0:
    myfile = sys.argv.pop(0)
    sc = SchemaChk(myfile)
    for oid in sc.listall(attrclass):
        if oid in oldattrswithaliases:
            at = sc.get_obj(attrclass, oid)
            oldnames = oldattrswithaliases[oid]
            if at.names != oldnames:
                print "new attribute", at.names, "has different aliases than old definition", oldnames
