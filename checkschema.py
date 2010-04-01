
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
dupattrs = ldap.cidict.cidict()
allocs = ldap.cidict.cidict()
dupocs = ldap.cidict.cidict()
alloids = {}
dupoids = {}
attrclass = ldap.schema.models.AttributeType
occlass = ldap.schema.models.ObjectClass
for myfile in sys.argv[1:]:
    sc = SchemaChk(myfile)
    for oid in sc.listall(attrclass) + sc.listall(occlass):
        se = sc.get_obj(attrclass, oid, sc.get_obj(occlass, oid, None))
        assert(se)
        if alloids.has_key(oid):
            if not dupoids.has_key(oid):
                dupoids[oid] = [alloids[oid]]
            dupoids[oid].append((se, myfile))
        else:
            alloids[oid] = (se, myfile)
    for attr in sc.name2oid[attrclass].keys():
        se = sc.get_obj(attrclass, attr)
        if allattrs.has_key(attr):
            if not dupattrs.has_key(attr):
                dupattrs[attr] = [allattrs[attr]]
            dupattrs[attr].append((se, myfile))
        else:
            allattrs[attr] = (se, myfile)
    for oc in sc.name2oid[occlass].keys():
        se = sc.get_obj(occlass, oc)
        if allocs.has_key(oc):
            if not dupocs.has_key(oc):
                dupocs[oc] = [allocs[oc]]
            dupocs[oc].append((se, myfile))
        else:
            allocs[oc] = (se, myfile)

for oid,lst in dupoids.iteritems():
    print "\n\nDuplicate oid", oid
    for se,myfile in lst:
        print "\tfile %s element %s" % (myfile, se)

for attr,lst in dupattrs.iteritems():
    print "\n\nDuplicate attribute", attr
    for se,myfile in lst:
        print "\tfile %s element %s" % (myfile, se)

for oc,lst in dupocs.iteritems():
    print "\n\nDuplicate objectclass", oc
    for se,myfile in lst:
        print "\tfile %s element %s" % (myfile, se)
