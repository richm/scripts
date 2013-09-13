import sys
import os
import bsddb.db

txn_flags = 0 # bsddb.db.DB_TXN_SNAPSHOT
cur_flags = 0 # bsddb.db.DB_TXN_SNAPSHOT
cur_flags_notxn = 0 # bsddb.db.DB_READ_UNCOMMITTED # bsddb.db.DB_TXN_SNAPSHOT DB_READ_COMMITTED

def print_records(db, txn=None, cur=None):
    flags = cur_flags
    if txn:
        print "records for txn", txn
    else:
        print "no txn records"
    closecur = False
    if not cur:
        cur = db.cursor(txn, flags)
        closecur = True
    rec = cur.first()
    while rec:
        try:
            print "\tkey=%s val=%s" % rec
            print "\textra=%s" % str(cur.get(bsddb.db.DB_GET_RECNO))
            rec = cur.next()
        except Exception, ex:
            print "caught", ex
            break
    if closecur:
        cur.close()

dbdir = "/var/tmp/dbtest"
try: os.mkdir(dbdir)
except OSError, e:
    if e.errno == os.errno.EEXIST: pass
    else: raise e
env = bsddb.db.DBEnv()
envflags = bsddb.db.DB_CREATE|bsddb.db.DB_RECOVER|bsddb.db.DB_INIT_LOCK|bsddb.db.DB_INIT_LOG|bsddb.db.DB_INIT_TXN|bsddb.db.DB_INIT_MPOOL|bsddb.db.DB_THREAD
print "open dbenv in", dbdir
env.open(dbdir, envflags)

allow_uncommitted = False
db = bsddb.db.DB(env)
db.set_flags(bsddb.db.DB_DUPSORT|bsddb.db.DB_RECNUM)
dbflags = bsddb.db.DB_CREATE|bsddb.db.DB_AUTO_COMMIT|bsddb.db.DB_THREAD
#dbflags = bsddb.db.DB_CREATE|bsddb.db.DB_AUTO_COMMIT|bsddb.db.DB_THREAD|bsddb.db.DB_MULTIVERSION
if allow_uncommitted:
    dbflags = dbflags|bsddb.db.DB_READ_UNCOMMITTED
dbfile = dbdir + "/dbtest.db4"
print "open db", dbfile
db.open(dbfile, dbtype=bsddb.db.DB_BTREE, flags=dbflags)

#seq_flags = bsddb.db.DB_CREATE|bsddb.db.DB_THREAD
#uidseq = bsddb.db.DBSequence(db)
#uidseq.open("uidnumber", None, seq_flags)
#usnseq = bsddb.db.DBSequence(db)
#usnseq.open("usn", None, seq_flags)

def loaddb():
    for ii in xrange(0,10):
        db.put("key" + str(ii), "data" + str(ii))
    flags = bsddb.db.DB_NODUPDATA
#    flags = bsddb.db.DB_NOOVERWRITE
    for ii in xrange(0,10):
        db.put("multikey", "multidata" + str(ii), None, flags)
loaddb()
cur = db.cursor(None, cur_flags_notxn)
print_records(db, None, cur)

def test1():
    print "test 1 - abort child txn but commit parent txn"
    print_records(db)
    print "create parent txn"
    partxn = env.txn_begin(None, txn_flags)
    print "do a write inside the parent before the child"
    db.put("parent before key", "parent before data", partxn)
    print_records(db, partxn)
    uidnum = uidseq.get(1, partxn)
    print "uidnumber is", uidnum

    print "create child transaction"
    chitxn = env.txn_begin(partxn, txn_flags)

    print "do a write inside the child"
    db.put("child key", "child data", chitxn)
    print_records(db,chitxn)
    usnnum = usnseq.get(1, chitxn)
    print "usn is", usnnum

    print "abort the child txn"
    chitxn.abort()

    print_records(db,partxn)
    print "do a write inside the parent after the child"
    db.put("parent after key", "parent after data", partxn)
    print_records(db,partxn)

    print "commit the transaction"
    partxn.commit()
    print_records(db)

def test2():
    print "test 2 - commit child txn but abort parent txn"
    print "create parent txn"
    partxn = env.txn_begin(None, txn_flags)
    print "do a write inside the parent before the child"
    db.put("parent before key2", "parent before data2", partxn)
    print_records(db,partxn)
    uidnum = uidseq.get(1, partxn)
    print "uidnumber is", uidnum

    print "create child transaction"
    chitxn = env.txn_begin(partxn, txn_flags)

    print "do a write inside the child"
    db.put("child key2", "child data2", chitxn)
    print_records(db,chitxn)
    usnnum = usnseq.get(1, chitxn)
    print "usn is", usnnum

    print "commit the child txn"
    chitxn.commit()

    print_records(db,partxn)
    print "do a write inside the parent after the child"
    db.put("parent after key2", "parent after data2", partxn)

    print "abort the transaction"
    partxn.abort()
    print_records(db)

def test3():
    print "test 3 - commit child and parent"
    print "create parent txn"
    partxn = env.txn_begin(None, txn_flags)
    print "read records in empty database"
    print_records(db, partxn)
#print_records(db)
    print "do a write inside the parent before the child"
    db.put("parent before key3", "parent before data3", partxn)
#print "run db_stat -C A and press Enter"
#null = sys.stdin.readline()
#print "read records"
    print_records(db, partxn)
#print "run db_stat -C A and press Enter"
#null = sys.stdin.readline()
    uidnum = uidseq.get(1, partxn)
    print "uidnumber is", uidnum
#print_records(db)
    print "create child transaction"
    chitxn = env.txn_begin(partxn, txn_flags)
    print "read records"
    print_records(db, chitxn)
    print_records(db, partxn)
#print_records(db)
    print "do a write inside the child"
    db.put("child key3", "child data3", chitxn)
    print "read records"
    print_records(db, chitxn)
    print_records(db, partxn)
#print_records(db)
    usnnum = usnseq.get(1, chitxn)
    print "usn is", usnnum
    print "commit the child txn"
    chitxn.commit()
    print "read records"
    print_records(db, partxn)
#print_records(db)
    print "do a write inside the parent after the child"
    db.put("parent after key3", "parent after data3", partxn)
    print "read records"
    print_records(db, partxn)
#print_records(db)
    print "commit the transaction"
    partxn.commit()
    print "read records"
    print_records(db)
    uidnum = uidseq.get()
    print "uidnumber is", uidnum
    usnnum = usnseq.get()
    print "usn is", usnnum

def test4():
    print "attempt to start a new transaction while another transaction is open"
    txn1 = env.txn_begin(None, txn_flags)
    print "read records in empty database"
    print_records(db, txn1)
    print "add record with txn1"
    db.put("test4 key1", "test4 data1", txn1)
    print "read records with txn1"
    print_records(db, txn1)
    print "start a new transaction"
    txn2 = env.txn_begin(None, txn_flags)
    print "add record with txn2"
    db.put("test4 key2", "test4 data2", txn2)
    print "read records with txn2"
    print_records(db, txn2)

def test5():
    print "attempt to read the db without a txn while another transaction is open"
    txn1 = env.txn_begin(None, txn_flags)
    print "read records in empty database"
    print_records(db, txn1)
    print "read records without txn"
    print_records(db)
    print "add record with txn1"
    db.put("test5 key1", "test5 data1", txn1)
    print "read records with txn1"
    print_records(db, txn1)
    print "read records without txn"
    print_records(db)
    print "commit txn"
    txn1.commit()
    print "read records without txn"
    print_records(db)

def test6():
    print "start a read-only cursor notxn, then start a txn"
    cur1 = db.cursor(None, cur_flags_notxn)
    print "read data using notxn cursor"
    print_records(db, None, cur1)
    print "create txn"
    txn1 = env.txn_begin(None, txn_flags)
    print "create txn cursor"
    cur2 = db.cursor(txn1, cur_flags)
    print "position cursor"
    cur2.last()
    print "put data using cursor"
    cur2.put("txnkey", "txndata", bsddb.db.DB_CURRENT)
    print "read data using txn cursor"
    print_records(db, None, cur2)
    print "modify data inside the txn"
    print "read data using notxn cursor"
    print_records(db, None, cur1)
    print "read data using txn cursor"
    print_records(db, None, cur2)

    cur1.close()
    cur2.close()
    txn1.abort()

#test1()
#test2()
#test3()
#test4()
#test5()
#test6()
#loaddb()
