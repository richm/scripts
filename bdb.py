import sys
import bsddb.db

txn_flags = 0 # bsddb.db.DB_TXN_SNAPSHOT
cur_flags = 0 # bsddb.db.DB_TXN_SNAPSHOT

def print_records(db, txn=None):
    flags = cur_flags
    if txn:
        print "txn records"
    else:
        print "no txn records"
    cur = db.cursor(txn, flags)
    rec = cur.first()
    while rec:
        try:
            print "\tkey=%s val=%s" % rec
            rec = cur.next()
        except Exception, ex:
            print "caught", ex
            break
    cur.close()

dbdir = "/var/tmp/dbtest"
env = bsddb.db.DBEnv()
envflags = bsddb.db.DB_CREATE|bsddb.db.DB_RECOVER|bsddb.db.DB_INIT_LOCK|bsddb.db.DB_INIT_LOG|bsddb.db.DB_INIT_TXN|bsddb.db.DB_INIT_MPOOL|bsddb.db.DB_THREAD
print "open dbenv in", dbdir
env.open(dbdir, envflags)

allow_uncommitted = False
db = bsddb.db.DB(env)
dbflags = bsddb.db.DB_CREATE|bsddb.db.DB_AUTO_COMMIT|bsddb.db.DB_THREAD
#dbflags = bsddb.db.DB_CREATE|bsddb.db.DB_AUTO_COMMIT|bsddb.db.DB_THREAD|bsddb.db.DB_MULTIVERSION
if allow_uncommitted:
    dbflags = dbflags|bsddb.db.DB_READ_UNCOMMITTED
dbfile = dbdir + "/dbtest.db4"
print "open db", dbfile
db.open(dbfile, dbtype=bsddb.db.DB_BTREE, flags=dbflags)

seq_flags = bsddb.db.DB_CREATE|bsddb.db.DB_THREAD
uidseq = bsddb.db.DBSequence(db)
uidseq.open("uidnumber", None, seq_flags)
usnseq = bsddb.db.DBSequence(db)
usnseq.open("usn", None, seq_flags)

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

test1()
test2()
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
