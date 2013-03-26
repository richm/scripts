from bug_harness import DSAdminHarness as DSAdmin
from dsadmin import Entry
from dsadmin_utils import *
"""
    An harness for bug replication.

"""
import os

REPLBINDDN = ''
REPLBINDPW = ''


@static_var("REPLICAID", 1)
def get_next_replicaid(replica_id=None, replica_type=None):            
    if replica_id:
        REPLICAID = replica_id
        return REPLICAID
    # get a default replica_id if it's a MASTER,
    # or 0 if consumer
    if replica_type == MASTER_TYPE:
        REPLICAID += 1
        return REPLICAID

    return 0



class DSAdminHarness(DSAdmin):
    """Harness wrapper around dsadmin.

       Specialize the DSAdmin behavior (No, I don't care about Liskov ;))
    """
    def setupSSL(self, secport=0, sourcedir=os.environ['SECDIR'], secargs=None):
        """Bug scripts requires SECDIR."""
        return DSAdmin.setupSSL(self, secport, sourcedir, secargs)

    def setupAgreement(self, repoth, args):
        """Set default replia credentials """
        args.setdefault('binddn', REPLBINDDN)
        args.setdefault('bindpw', REPLBINDPW)

        return DSAdmin.setupAgreement(self, repoth, args)
        
    def setupReplica(self, args):
        """Set default replia credentials """
        args.setdefault('binddn', REPLBINDDN)
        args.setdefault('bindpw', REPLBINDPW)
        # manage a progressive REPLICAID
        args.setdefault('id', get_next_replicaid(args.get('id'), args.get('type')))
        return DSAdmin.setupReplica(self, args)
        
   def setupBindDN(self, binddn=REPLBINDDN, bindpw=REPLBINDPW):
       return DSAdmin.setupBindDN(self, binddn, bindpw)
     
