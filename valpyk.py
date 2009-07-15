#!/usr/bin/env python
# -*- coding: ASCII -*-
"""
Copyright(C) 2006 INL
Written by Victor Stinner <victor.stinner@inl.fr>

This program is free software; you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, version 2 of the License.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program; if not, write to the Free Software
Foundation, Inc., 59 Temple Place - Suite 330, Boston, MA 02111-1307, USA.
---
Script to parse memory leaks in Valgrind log.

Run it without argument for more information.

Warnings and errors are written in stderr.
"""

import re
import sys

class TextParser:
    """
    Very basic plain text parser useful to read one line after the other.

    It calls a different function for each line, and each function returns
    next function to be called for next line.

    Interresting methods and attributes:
    - line_number is the current line number of input file (starting at 1)
    - reset(): function called when parser is created
    - stop(): function called when the parser is done
    - parserError(): raise an exception with reason and line number
    """
    def __init__(self, input, first_parser):
        """
        Parse input file object, first_parser is the first function
        used to parse the file content.
        """
        self.input = input
        self.line_number = 0
        self.first_parser = first_parser
        self.reset()
        self.runParser()

    def parserError(self, message):
        raise Exception("Error at line %s: %s" % \
            (self.line_number, message))

    def reset(self):
        pass

    def stop(self):
        pass

    def runParser(self):
        parser = self.first_parser
        while True:
            line = self.input.readline()
            if len(line) == 0:
                break
            line = line.rstrip()
            self.line_number += 1
            new_parser = parser(line)
            if new_parser:
                parser = new_parser
        self.stop()

class Function:
    """
    A function with attributes: name, file, line number, address.
    File and line address are optional.

    You can compare functions using hash(func) and convert to
    string using str(func)
    """
    def __init__(self, name, addr, file=None, line=None):
        if name and name != "???":
            self.name = name # a function name
        else:
            self.name = "" # an object - no function name
        self.file = file
        self.line = line
        self.addr = addr

    def __hash__(self):
        if self.line:
            line = self.line//10
        else:
            line = None
        return hash((self.name, self.file, line))

    def __str__(self):
        if len(self.name) > 0:
            text = [self.name + "()"]
        else:
            text = ["--unknown--"]
        if self.file:
            if self.line is not None:
                text.append(" at %s:%s" % (self.file, self.line))
            else:
                text.append(" at %s" % self.file)
        return "".join(text)

    def assupp(self):
        if len(self.name) > 0:
            return "fun:" + self.name
        else: # library
            return "obj:" + self.file

class BaseError:
    """
    Base class for errors and leaks

    Attributes: backtrace (list of functions)

    Methods:
    - hash(err): use it to compare errors and find duplicates
    - str(err): Create one line of text to describe the error
    """
    def __init__(self,sourcefile):
        """source file is the valgrind report file where the error occurred"""
        self.backtrace = []
        self.extra_backtrace = [] # some errors have additional backtrace info
        self.sourcefile = sourcefile
        self.duplicates = 0 # record how many duplicates this bug had
        self.bytes = 0 # not all types of errors will use this

    def __hash__(self):
        data = [hash(func) for func in self.backtrace]
        return hash(tuple(data))

    def __nonzero__(self):
        """Used to test if error: """
        return len(self.backtrace) > 0

    def __str__(self):
        """Create one line of text to describe the error"""
        return self.sourcefile + ":"

    def supptype(self):
        """Type to use for suppression e.g. Cond Leak etc."""
        assert(False) # base class must override

    def suppmore(self):
        """Additional information to provide with suppression
        e.g. a Param error has the syscall"""
        return None

    def founddup(self, error):
        # if verbose, print error
        self.duplicates = self.duplicates + 1

class ConditionalError(BaseError):
    """
    "Conditional jump or move depends on uninitialised value(s)" error

    Attributes: backtrace (list of functions)

    Methods:
    - hash(err): use it to compare errors and find duplicates
    - str(err): Create one line of text to describe the error
    """
    def __str__(self):
        return BaseError.__str__(self) + "Conditional jump or move depends on uninitialised value(s)"

    def supptype(self):
        """What type of suppression to generate e.g. Cond, Value4, etc."""
        return "Cond"

class ParamError(BaseError):
    """
    "Syscall param (\S+) points to uninitialised byte(s)"

    Attributes: backtrace (list of functions)

    Methods:
    - hash(err): use it to compare errors and find duplicates
    - str(err): Create one line of text to describe the error
    """
    def __init__(self, sourcefile, syscall):
        BaseError.__init__(self, sourcefile)
        self.syscall = syscall

    def __str__(self):
        return BaseError.__str__(self) + "Syscall param %s points to uninitialised byte(s)" % self.syscall

    def supptype(self):
        """What type of suppression to generate e.g. Cond, Value4, etc."""
        return "Param"

    def suppmore(self):
        return self.syscall

class UninitialisedValueError(BaseError):
    """
    "Use of uninitialised value of size (...)" error.

    Attributes: backtrace (list of functions) and bytes (size of uninitialized
    value).

    Methods:
    - hash(err): use it to compare errors and find duplicates
    - str(err): Create one line of text to describe the error
    """
    def __init__(self, sourcefile, bytes):
        BaseError.__init__(self, sourcefile)
        self.bytes = bytes

    def __hash__(self):
        data = [hash(func) for func in self.backtrace] + [hash(self.bytes)]
        return hash(tuple(data))

    def __nonzero__(self):
        return BaseError.__nonzero__(self) and (self.bytes != None)

    def __str__(self):
        return BaseError.__str__(self) + "Uninitialised value error: %s bytes" % self.bytes

    def supptype(self):
        """What type of suppression to generate e.g. Cond, Value4, etc."""
        return "Value" + str(self.bytes)

class InvalidReadError(UninitialisedValueError):
    """
    "Invalid read of size (...)" error.
    """
    def __str__(self):
        return BaseError.__str__(self) + "Invalid read: %s bytes" % self.bytes

class ProgramError(BaseError):
    """
    "Process terminating with (...)" error.
    """
    def __init__(self, sourcefile, exit_code):
        BaseError.__init__(self, sourcefile)
        self.exit_code = exit_code
        self.reason = None

    def __str__(self):
        return "Program terminating: %s (%s)" % (self.exit_code, self.reason)

class MemoryLeak(UninitialisedValueError):
    """
    Memory leak error, message like: "10 bytes in (...) loss record 2 of 9"
    """
    def __str__(self):
        return BaseError.__str__(self) + "Memory leak: %s bytes" % self.bytes

    def supptype(self):
        """What type of suppression to generate e.g. Cond, Value4, etc."""
        return "Leak"

class ValgrindParser(TextParser):
    """
    Valgrind log parser: convert plain text log to Python objects.

    Errors are filtered using methods:
    - filterLeak(): only for memory leaks
    - filterError(): for all other errors

    Note: filterError() calls filterLeak()
    """
    # from m_errormgr.c
    # there is no apparent way to override this - -chain-length= has no effect here
    VG_MAX_SUPP_CALLERS = 24 # Max number of callers for context in a suppression.

    regex_pid = r'==[0-9]+==' # matches pid at beginning of each line
    re_pid = re.compile("^" + regex_pid)
    regex_num = r'[0-9,]+' # matches numbers with commas in the usual US format
    regex_empty = re.compile(r"^%s$" % regex_pid)
    regex_indirect = r' \(%s direct, %s indirect\)' % (regex_num, regex_num)

    regex_terminating = re.compile("%s Process terminating with (.*)$" % regex_pid)
    regex_program_reason = re.compile("%s  (.*)$" % regex_pid)
    regex_cond = re.compile(r"^%s Conditional jump or move depends on uninitialised value\(s\)$" % regex_pid)
    regex_uninit = re.compile(r"^%s Use of uninitialised value of size (%s)$" % (regex_pid, regex_num))
    regex_invalid_read = re.compile(r"^%s Invalid read of size (%s)$" % (regex_pid, regex_num))
    # ==14149== Syscall param pwrite64(buf) points to uninitialised byte(s)
    regex_param = re.compile(r"^%s Syscall param (\S+) points to uninitialised byte\(s\)$" % regex_pid)
    # ==17108==  Address 0xbc20b08 is 0 bytes after a block of size 128 alloc'd
    regex_addr_alloc = re.compile(r"^%s  Address [0-9A-Fa-fx]+ is %s bytes (?:inside|after) a block of size %s alloc'd" % (regex_pid, regex_num, regex_num))
    # ==18511==  Address 0xd5cb3c6 is not stack'd, malloc'd or (recently) free'd
    regex_addr_none = re.compile(r"^%s  Address [0-9A-Fa-fx]+ is not stack'd, malloc'd or \(recently\) free'd" % regex_pid)
    regex_unhandled = re.compile(r"^%s Warning: noted but unhandled ioctl (0x[0-9A-Fa-f]+) with no size/direction hints" % regex_pid)
    regex_spurious = re.compile(r"^%s    This could cause spurious value errors to appear." % regex_pid)
    regex_missing = re.compile(r"^%s    See README_MISSING_SYSCALL_OR_IOCTL for guidance on writing a proper wrapper." % regex_pid)
    regex_thread = re.compile(r"^%s Thread .*$" % regex_pid)
    regex_toomany = re.compile(r"^%s More than (%s) errors detected.  Subsequent errors" % (regex_pid, regex_num))
    regex_toomany2 = re.compile(r"^%s will still be recorded, but in less detail than before." % regex_pid)

    # ==6471== 24 bytes in 1 blocks are definitely lost in loss record 271 of 1,254 
    regex_leak_header = re.compile(r"^%s (%s)(?:%s)? bytes in %s blocks are .* in loss record %s of %s$" % (regex_pid, regex_num, regex_indirect, regex_num, regex_num, regex_num))
    regex_backtrace_name = re.compile(r"^%s    (?:at|by) (0x[0-9A-F]+): (.+) \(([^:]+):([0-9]+)\)$" % regex_pid)
    regex_backtrace_name_in = re.compile(r"^%s    (?:at|by) (0x[0-9A-F]+): ([^ ]+) \(in ([^)]+)\)$" % regex_pid)
    regex_backtrace_within = re.compile(r"^%s    (?:at|by) (0x[0-9A-F]+): \((?:with)?in (.*)\)$" % regex_pid)
    regex_backtrace_unknown = re.compile(r"^%s    (?:at|by) (0x[0-9A-F]+): (\?\?\?)$" % regex_pid)
    regex_anyleak = re.compile(r'lost')
    regex_anyuninit = re.compile(r'uninitialized')
    regex_anyparam = re.compile(r'Syscall param')
    use_filters = True

    def __init__(self, input, use_filters=True):
        """
        Constructor: argument input is a file object
        """
        self.errors = []
        self.leaks = []
        self.unhandled = {}
        self.toomany = 0
        self.skipped_errors = 0
        self.skipped_leaks = 0
        self.use_filters = use_filters
        if not isinstance(input,list) and not isinstance(input,tuple):
            inputlist = [input]
        else:
            inputlist = input
        for input in inputlist:
            if isinstance(input, file):
                self.filename = "--input--"
                infile = input
            else: # assume filename
                self.filename = input
                infile = open(self.filename, "r")
            TextParser.__init__(self, infile, self.searchLeakHeader)
            if not isinstance(input, file):
                infile.close()            

    def searchLeakHeader(self, line):
        """
        Search first line of memory leak or any other type of error
        """
        match = self.regex_leak_header.match(line)
        if match:
#            print "found memleak:", line
            size = match.group(1).replace(",", "")
            self.error = MemoryLeak(self.filename, int(size))
            return self.parseBacktrace

        match = self.regex_uninit.match(line)
        if match:
            size = match.group(1).replace(",", "")
            self.error = UninitialisedValueError(self.filename, int(size))
            return self.parseBacktrace
        elif self.regex_anyuninit.search(line):
            print "line %s is uninit error but did not match regex_uninit" % line

        match = self.regex_param.match(line)
        if match:
            syscall = match.group(1)
            self.error = ParamError(self.filename, syscall)
            return self.parseBacktrace
        elif self.regex_anyparam.search(line):
            print "line %s is param error but did not match regex_param" % line

        match = self.regex_invalid_read.match(line)
        if match:
#            print "found invalid read:", line
            size = match.group(1).replace(",", "")
            self.error = InvalidReadError(self.filename, int(size))
            return self.parseBacktrace

        match = self.regex_cond.match(line)
        if match:
#            print "found cond:", line
            self.error = ConditionalError(self.filename)
            return self.parseBacktrace

        match = self.regex_terminating.match(line)
        if match:
#            print "found program error:", line
            self.error = ProgramError(self.filename, match.group(1))
            return self.parseProgramError

        match = self.regex_unhandled.match(line)
        if match:
#            print "found unhandled ioctl error:", line
            ioctl = match.group(1)
            val = self.unhandled.get(ioctl, 0) + 1
            self.unhandled[ioctl] = val
            return self.searchLeakHeader

        match = self.regex_spurious.match(line)
        if match:
            # ignore
            return self.searchLeakHeader

        match = self.regex_missing.match(line)
        if match:
            # ignore
            return self.searchLeakHeader

        match = self.regex_thread.match(line)
        if match:
            # ignore
            return self.searchLeakHeader

        match = self.regex_toomany.match(line)
        if match:
            self.toomany = self.toomany + 1
            return self.searchLeakHeader

        match = self.regex_toomany2.match(line)
        if match:
            # ignore
            return self.searchLeakHeader

        if self.regex_empty.match(line):
            # ignore empty
            return self.searchLeakHeader

        print 'searchLeakHeader: no match for line "%s"' % line

    def parseProgramError(self, line):
        """
        Parse second line of a program error
        """
        match = self.regex_program_reason.match(line)
        if not match:
            self.parserError("Unable to get program exit reason")
        self.error.reason = match.group(1)
        return self.parseBacktrace

    def parseBacktrace(self, line):
        """
        Parse a backtrace (list of functions)
        """
#        print "parseBacktrace: error %s line %s" % (self.error, line)
        # ==14694==    at 0x401C7AA: calloc (vg_replace_malloc.c:279)
        match = self.regex_backtrace_name.match(line)
        if match:
            addr, name, filename, linenb = match.groups()
            func = Function(name, addr, filename, int(linenb))
            if len(self.error.extra_backtrace) > 0:
                self.error.extra_backtrace.append(func)
            else:
                self.error.backtrace.append(func)
            return

        # ==14694==    at 0x401C7AA: calloc (in /lib/...)
        match = self.regex_backtrace_name_in.match(line)
        if match:
            addr, name, filename = match.groups()
            func = Function(name, addr, filename)
            if len(self.error.extra_backtrace) > 0:
                self.error.extra_backtrace.append(func)
            else:
                self.error.backtrace.append(func)
            return

        # ==14694==    by 0x4187E56: (within /lib/tls...)
        match = self.regex_backtrace_within.match(line)
        if match:
            addr, filename = match.groups()
            func = Function(None, addr, filename)
            if len(self.error.extra_backtrace) > 0:
                self.error.extra_backtrace.append(func)
            else:
                self.error.backtrace.append(func)
            return

        # ==14694==    by 0x402646A: ???
        match = self.regex_backtrace_unknown.match(line)
        if match:
            addr, name = match.groups()
            func = Function(name, addr)
            if len(self.error.extra_backtrace) > 0:
                self.error.extra_backtrace.append(func)
            else:
                self.error.backtrace.append(func)
            return

        match = self.regex_addr_alloc.match(line)
        if match:
#            print "found addr alloc error:", line
            self.error.extra_backtrace = [self.re_pid.sub("", line)]
            return

        match = self.regex_addr_none.match(line)
        if match:
#            print "found addr none error:", line
            self.error.extra_backtrace = [self.re_pid.sub("", line)]
            return

        match = self.regex_unhandled.match(line)
        if match:
            self.addError() # this terminates the current error
#            print "found unhandled ioctl error:", line
            ioctl = match.group(1)
            val = self.unhandled.get(ioctl, 0) + 1
            self.unhandled[ioctl] = val
            return self.searchLeakHeader

        match = self.regex_cond.match(line)
        if match:
            self.addError() # this terminates the current error
#            print "found cond:", line
            self.error = ConditionalError(self.filename)
            return self.parseBacktrace

        if not self.regex_empty.match(line):
            print >>sys.stderr, 'parseBacktrace: no match for "%s"' % line
        self.addError()
        return self.searchLeakHeader

    def stop(self):
        self.addError()

    def reset(self):
        self.error = None

    def filterError(self, error):
        if not self.use_filters:
            return True
        result = self.filterLeak(error)
        if result is not True:
            return result
        names = [func.name for func in self.error.backtrace]
        for name in names:
            if not name:
                return True
            if name.startswith("gcry_"):
                return name
        return True

    def filterLeak(self, leak):
        if not self.use_filters:
            return True
        names = [func.name for func in self.error.backtrace]
        if "PyObject_Realloc" in names:
            return "PyObject_Realloc"
        if "PyObject_Free" in names:
            return "PyObject_Free"
        if "dlsym" in names:
            return "dlsym"
        if "dlopen" in names:
            return "dlopen"
        if "_dl_open" in names:
            return "_dl_open"
        if "gcry_check_version" in names:
            return "gcry_check_version"
        for name in names:
            if not name:
                return True
            if name.startswith("pthread_create"):
                return name
            if name.startswith("g_thread_init"):
                return name
            if "sasl_" in name:
                return name
            if name.endswith("dlopen_mode"):
                return "dlopen_mode"
            if "sasldb_" in name:
                return name
            if name.startswith("gnutls_"):
                return name
            if name.startswith("gcry_"):
                return name
            if name.startswith("g_iconv"):
                return name
        for func in self.error.backtrace:
            if func.file and "libdl" in func.file:
                return func.file
        return True

    def addError(self):
        if self.error:
            if isinstance(self.error,MemoryLeak):
                result = self.filterLeak(self.error)
                if result is True:
                    self.leaks.append(self.error)
                else:
                    print >>sys.stderr, "Skip memory leak %s at line %s" % (result, self.line_number)
                    self.skipped_leaks += 1
            else:
                result = self.filterError(self.error)
                if result is True:
                    self.errors.append(self.error)
                else:
                    print >>sys.stderr, "Skip error %s at line %s" % (result, self.line_number)
                    self.skipped_errors += 1
        self.reset()

def usage():
    print """usage: %s logfilename [logfilename] ... [logfilename]

Valgrind memory leak parser. To get good logs, run valgrind with options:
   --leak-check=full: see all informations about memory leaks
   --show-reachable=yes: also display reachable memory leaks
   --run-libc-freeres=yes: avoid some libc memory leaks
   --verbose: gives more informations

Other useful options:
    --log-file-exactly=yourname.log

If you use glib, also set environment variable G_SLICE to find memory leaks:
export G_SLICE=always-malloc""" % sys.argv[0]

def displayErrors(errors, max_error=None, reverse=True, assupp=False):
    """
    Function to display a list of errors.
    """
    if max_error and max_error < len(errors):
        print >>sys.stderr, "Only display top %s memory errors" % max_error
        errors = errors[-max_error:]
    else:
        errors = errors
    if reverse:
        errors = errors[::-1]
    displayed = dict()
    for error in errors:
        key = hash(error)
        checkdup = displayed.get(key, None)
        if checkdup:
            checkdup.founddup(error)
#            print >>sys.stderr, "Skip duplicate"
            continue
        displayed[key] = error

    # create a table that maps to our desired comparison ordering
    # of classes - the order is given in the list errclasses
    errclasses = [ProgramError, InvalidReadError, ParamError,
                 UninitialisedValueError, ConditionalError, MemoryLeak]
    # We basically want to say something like
    # cmpval = classhash[class1][class2]
    # and have cmpval be -1, 0, or 1
    classhash = {}
    for ii in xrange(len(errclasses)):
        clzz1 = errclasses[ii]
        classhash[clzz1] = {}
        # classes before us (lower ii) sort before us
        for clzz2 in errclasses[:ii]:
            classhash[clzz1][clzz2] = 1
        # our class returns 0
        classhash[clzz1][clzz1] = 0
        # classes after us (higher ii) sort after us
        for clzz2 in errclasses[(ii+1):]:
            classhash[clzz1][clzz2] = -1
        
    def customsort(obj1, obj2):
        """sort first by type, then by number of duplicates, then by number of bytes"""
        retval = classhash[obj1.__class__][obj2.__class__]
        if retval == 0:
            retval =  obj2.duplicates - obj1.duplicates
        if retval == 0:
            retval = obj2.bytes - obj1.bytes
        return retval

    bydups = displayed.values()
    bydups.sort(customsort)

    for error in bydups:
        # Display error
        if assupp:
            print "{"
            diff = len(error.backtrace) - ValgrindParser.VG_MAX_SUPP_CALLERS
            if diff > 0:
                print "   Stack size too big by", diff, error, "duplicates: ", error.duplicates
            else:
                print "  ", error
            print "   Memcheck:%s" % error.supptype()
            suppmore = error.suppmore()
            if suppmore:
                print "  ", suppmore
        else:
            print error, "duplicates: ", error.duplicates

        # Display backtrace
        backtrace = [ func for func in error.backtrace ]
        for func in backtrace:
            if assupp:
                print "  ", func.assupp()
            else:
                print "   > %s" % func
        if assupp:
            print "}"
        if not assupp and len(error.extra_backtrace) > 0:
            print error.extra_backtrace[0]
            for line in error.extra_backtrace[1:]:
                print "   >", line
                

    # Display memory errors count
    print "Total: %s (%s)" % (len(displayed), len(errors))
    print

def main():
    # Read log filename
    if len(sys.argv) < 2:
        usage()
        sys.exit(1)
    assupp = False
    if sys.argv[1] == '-s':
        assupp = True
        sys.argv.pop(1)

    # Parse input log
    parser = ValgrindParser(sys.argv[1:], False)

    for (ioctl, count) in parser.unhandled.iteritems():
        print "Found %d cases of unhandled ioctl %s" % (count, ioctl)

    if parser.toomany:
        print "Found %d programs with too many errors: fix them or suppress them to get full output" % parser.toomany

    # Display all errors
    displayErrors(parser.errors, None, False, assupp)

    # Display memory leaks in reverse order (bigest to smallest leak)
    # Only display top 10 leaks
#    displayErrors(parser.leaks, 10, True)

    # Display all leaks as suppressions
    displayErrors(parser.leaks, None, False, assupp)

    if parser.skipped_errors:
        print "Skipped errors: %s" % parser.skipped_errors

    if parser.skipped_leaks:
        print "Skipped memory leaks: %s" % parser.skipped_leaks

if __name__ == "__main__":
    main()

