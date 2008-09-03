import sys
import os
import errno
import time
import ldif

errlogfifo = '/tmp/errlogfifo'
accesslogfifo = '/tmp/accesslogfifo'
auditlogfifo = '/tmp/auditlogfifo'

instdir = "/opt/redhat-ds/slapd-localhost"
maxbufsize = 1000 # set on command line
errorloglevel = '0' # set on command line
doaccesslog = False
doauditlog = False

class LDIFFilter(ldif.LDIFCopy):
  """
  Copy LDIF input to LDIF output allowing entry mods
  """

  def __init__(
    self,
    input_file,output_file,
    ignored_attr_types=None,max_entries=0,process_url_schemes=None,
    base64_attrs=None,cols=76,line_sep='\n'
  ):
    """
    See LDIFParser.__init__() and LDIFWriter.__init__()
    """
    ldif.LDIFCopy.__init__(self,input_file,output_file,ignored_attr_types,max_entries,process_url_schemes)

  def handle(self,dn,entry):
    """
    Write single LDIF record to output file.
    """
    if dn == "cn=config":
        entry['nsslapd-errorlog-level'] = [errorloglevel]
        entry['nsslapd-errorlog-maxlogsperdir'] = [str(1)]
        entry['nsslapd-errorlog'] = [errlogfifo]
        if doaccesslog:
            entry['nsslapd-accesslog-maxlogsperdir'] = [str(1)]
            entry['nsslapd-accesslog-logbuffering'] = ['off']
            entry['nsslapd-accesslog-logging-enabled'] = ['on']
            entry['nsslapd-accesslog'] = [accesslogfifo]
        if doauditlog:
            entry['nsslapd-auditlog-maxlogsperdir'] = [str(1)]
            entry['nsslapd-auditlog-logging-enabled'] = ['on']
            entry['nsslapd-auditlog'] = [auditlogfifo]
    self._output_ldif.unparse(dn,entry)


def save_server_config(instdir):
    dseldif = instdir + "/config/dse.ldif"
    dsesave = instdir + "/config/dse.ldif.save"
    os.system("cp %s %s" % (dseldif, dsesave))

def restore_server_config(instdir):
    dseldif = instdir + "/config/dse.ldif"
    dsesave = instdir + "/config/dse.ldif.save"
    os.system("cp %s %s" % (dsesave, dseldif))

def change_server_config(instdir):
    dseldif = instdir + "/config/dse.ldif"
    dsesave = instdir + "/config/dse.ldif.save"
    input = open(dsesave, "r")
    output = open(dseldif, "w")
    ldif = LDIFFilter(input, output)
    ldif.parse()
    input.close()
    output.close()

def getargs():
    global instdir, maxbufsize, errorloglevel, doaccesslog, doauditlog
    instdir = sys.argv[1]
    maxbufsize = int(sys.argv[2])
    errorloglevel = sys.argv[3]
    if len(sys.argv) > 4:
        doaccesslog = True
    if len(sys.argv) > 5:
        doauditlog = True

def mkfifos():
    os.mkfifo(errlogfifo)
    if doaccesslog:
        os.mkfifo(accesslogfifo)
    if doauditlog:
        os.mkfifo(auditlogfifo)

def rmfifos():
    for fname in [errlogfifo, errlogfifo + ".rotationinfo",
                  accesslogfifo, accesslogfifo + ".rotationinfo",
                  auditlogfifo, auditlogfifo + ".rotationinfo"]:
        try:
            os.unlink(fname)
        except OSError, e:
            if e.errno == errno.ENOENT:
                print "Notice: file not found", fname
            else:
                raise Exception, "%s [%d]" % (e.strerror, e.errno)

def start_server(instdir,errlogfifo):
    print "Starting server %s" % instdir
    os.system(instdir + "/start-slapd > " + errlogfifo + " 2>&1 &")
    print "Started server %s" % instdir
    return

def buffer_log(logfifo,maxbufsize):
    pid = os.fork()
    if pid == 0:
        buffer = []
        totallines = 0
        print "Listening to fifo ", logfifo
        for line in open(logfifo, 'r'):
            buffer.append(line)
            totallines = totallines + 1
            if len(buffer) > maxbufsize:
                del buffer[0]

        print logfifo, "=" * 60
        print "Read %d total lines" % totallines
        output = open(logfifo + ".log", "w")
        output.writelines(buffer)
        output.close()
        os._exit(0)

    return pid
        
def run():
    print "Starting"
    getargs()
    print "Using %s %d %s" % (instdir, maxbufsize, errorloglevel)
    mkfifos()
    print "Created fifos"
    save_server_config(instdir)
    print "Saved server config"
    change_server_config(instdir)
    print "Changed server config"
    if doauditlog:
        auditpid = buffer_log(auditlogfifo, maxbufsize)
        print "Started buffer logger for", auditlogfifo, "pid =", auditpid
    pid = buffer_log(errlogfifo, maxbufsize)
    print "Started buffer logger for", errlogfifo, "pid =", pid
    start_server(instdir, errlogfifo)
    if doaccesslog:
        time.sleep(5)
        accesspid = buffer_log(accesslogfifo, maxbufsize)
        print "Started buffer logger for", accesslogfifo, "pid =", accesspid
    (mypid, status) = os.waitpid(pid, 0)
    print "buffer logger", errlogfifo, "exited with status =", status
    if doaccesslog:
        (mypid, status) = os.waitpid(accesspid, 0)
        print "buffer logger", accesslogfifo, "exited with status =", status
    if doauditlog:
        (mypid, status) = os.waitpid(auditpid, 0)
        print "buffer logger", auditlogfifo, "exited with status =", status
    
    restore_server_config(instdir)
    rmfifos()

def usage():
    print "%s instancedir numlines errloglevel [accesslog] [auditlog]" % sys.argv[0]
    print "e.g. %s /opt/redhat-ds/slapd-foo 1000 8192" % sys.argv[0]
    print "This will capture the last 1000 lines to the error log with log level 8192"
    print "     %s /opt/redhat-ds/slapd-foo 1000 8192 1" % sys.argv[0]
    print "Like above, but also capture the access log output"
    print "     %s /opt/redhat-ds/slapd-foo 1000 8192 1 1" % sys.argv[0]
    print "Like above, but also capture the audit log output"
    print "When the server exits, the last numlines of each log will be printed to"
    print "     %s.log - error log output" % errlogfifo
    print "     %s.log - access log output" % accesslogfifo
    print "     %s.log - audit log output" % auditlogfifo

if __name__ == '__main__':
    if len(sys.argv) < 4:
        usage()
        sys.exit(2)
    run()
