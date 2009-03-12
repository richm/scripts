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

class ConditionalError:
    """
    "Conditional jump or move depends on uninitialised value(s)" error

    Attributes: backtrace (list of functions)

    Methods:
    - hash(err): use it to compare errors and find duplicates
    - str(err): Create one line of text to describe the error
    """
    def __init__(self):
        self.backtrace = []

    def __hash__(self):
        data = [hash(func) for func in self.backtrace]
        return hash(tuple(data))

    def __nonzero__(self):
        return len(self.backtrace) > 0

    def __str__(self):
        return "Conditional jump or move depends on uninitialised value(s)"

    def supptype(self):
        """What type of suppression to generate e.g. Cond, Value4, etc."""
        return "Cond"

class UninitialisedValueError:
    """
    "Use of uninitialised value of size (...)" error.

    Attributes: backtrace (list of functions) and bytes (size of uninitialized
    value).

    Methods:
    - hash(err): use it to compare errors and find duplicates
    - str(err): Create one line of text to describe the error
    """
    def __init__(self, bytes):
        self.backtrace = []
        self.bytes = bytes

    def __hash__(self):
        data = [hash(func) for func in self.backtrace] + [hash(self.bytes)]
        return hash(tuple(data))

    def __nonzero__(self):
        return self.bytes != None

    def __str__(self):
        return "Uninitialised value error: %s bytes" % self.bytes

    def supptype(self):
        """What type of suppression to generate e.g. Cond, Value4, etc."""
        return "Value4"

class InvalidReadError(UninitialisedValueError):
    """
    "Invalid read of size (...)" error.
    """
    def __str__(self):
        return "Invalid read: %s bytes" % self.bytes

    def supptype(self):
        """What type of suppression to generate e.g. Cond, Value4, etc."""
        return "Valud4"

class ProgramError(UninitialisedValueError):
    """
    "Process terminating with (...)" error.
    """
    def __init__(self, exit_code):
        UninitialisedValueError.__init__(self, 0)
        self.exit_code = exit_code
        self.reason = None

    def __str__(self):
        return "Program terminating: %s (%s)" % (self.exit_code, self.reason)

class MemoryLeak(UninitialisedValueError):
    """
    Memory leak error, message like: "10 bytes in (...) loss record 2 of 9"
    """
    def __str__(self):
        return "Memory leak: %s bytes" % self.bytes

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
    regex_num = r'[0-9,]+' # matches numbers with commas in the usual US format
    regex_empty = re.compile(r"^%s$" % regex_pid)
    regex_indirect = r' \(%s direct, %s indirect\)' % (regex_num, regex_num)

    regex_terminating = re.compile("%s Process terminating with (.*)$" % regex_pid)
    regex_program_reason = re.compile("%s  (.*)$" % regex_pid)
    regex_cond = re.compile(r"^%s Conditional jump or move depends on uninitialised value\(s\)$" % regex_pid)
    regex_uninit = re.compile(r"^%s Use of uninitialised value of size (%s)$" % (regex_pid, regex_num))
    regex_invalid_read = re.compile(r"^%s Invalid read of size (%s)$" % (regex_pid, regex_num))

    # ==6471== 24 bytes in 1 blocks are definitely lost in loss record 271 of 1,254 
    regex_leak_header = re.compile(r"^%s (%s)(?:%s)? bytes in %s blocks are .* in loss record %s of %s$" % (regex_pid, regex_num, regex_indirect, regex_num, regex_num, regex_num))
    regex_backtrace_name = re.compile(r"^%s    (?:at|by) (0x[0-9A-F]+): (.+) \(([^:]+):([0-9]+)\)$" % regex_pid)
    regex_backtrace_name_in = re.compile(r"^%s    (?:at|by) (0x[0-9A-F]+): ([^ ]+) \(in ([^)]+)\)$" % regex_pid)
    regex_backtrace_within = re.compile(r"^%s    (?:at|by) (0x[0-9A-F]+): \((?:with)?in (.*)\)$" % regex_pid)
    regex_backtrace_unknown = re.compile(r"^%s    (?:at|by) (0x[0-9A-F]+): (\?\?\?)$" % regex_pid)
    regex_anyleak = re.compile(r'lost')
    regex_anyuninit = re.compile(r'uninitialized')
    use_filters = True

    def __init__(self, input, use_filters=True):
        """
        Constructor: argument input is a file object
        """
        self.errors = []
        self.leaks = []
        self.skipped_errors = 0
        self.skipped_leaks = 0
        self.use_filters = use_filters
        TextParser.__init__(self, input, self.searchLeakHeader)

    def searchLeakHeader(self, line):
        """
        Search first line of memory leak or any other type of error
        """
        match = self.regex_leak_header.match(line)
        if match:
#            print "found memleak:", line
            size = match.group(1).replace(",", "")
            self.error = MemoryLeak(int(size))
            return self.parseBacktrace

        match = self.regex_uninit.match(line)
        if match:
            print "found uninit:", line
            size = match.group(1).replace(",", "")
            self.error = UninitialisedValueError(int(size))
            return self.parseBacktrace
        elif self.regex_anyuninit.search(line):
            print "line %s is a leak but did not match regex_uninit"

        match = self.regex_invalid_read.match(line)
        if match:
            print "found invalid read:", line
            size = match.group(1).replace(",", "")
            self.error = InvalidReadError(int(size))
            return self.parseBacktrace

        match = self.regex_cond.match(line)
        if match:
#            print "found cond:", line
            self.error = ConditionalError()
            return self.parseBacktrace

        match = self.regex_terminating.match(line)
        if match:
            print "found program error:", line
            self.error = ProgramError(match.group(1))
            return self.parseProgramError

#        print "searchLeakHeader: no match for line", line

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
            self.error.backtrace.append(func)
            return

        # ==14694==    at 0x401C7AA: calloc (in /lib/...)
        match = self.regex_backtrace_name_in.match(line)
        if match:
            addr, name, filename = match.groups()
            func = Function(name, addr, filename)
            self.error.backtrace.append(func)
            return

        # ==14694==    by 0x4187E56: (within /lib/tls...)
        match = self.regex_backtrace_within.match(line)
        if match:
            addr, filename = match.groups()
            func = Function(None, addr, filename)
            self.error.backtrace.append(func)
            return

        # ==14694==    by 0x402646A: ???
        match = self.regex_backtrace_unknown.match(line)
        if match:
            addr, name = match.groups()
            func = Function(name, addr)
            self.error.backtrace.append(func)
            return

        if not self.regex_empty.match(line):
            print >>sys.stderr, 'Unknown: "%s"' % line
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
    print """usage: %s logfilename

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
    displayed = set()
    for error in errors:
        key = hash(error)
        if key in displayed:
            print >>sys.stderr, "Skip duplicate"
            continue
        displayed.add(key)
        # Display memory error
        if assupp:
            print "{"
            diff = len(error.backtrace) - ValgrindParser.VG_MAX_SUPP_CALLERS
            if diff > 0:
                print "   Stack size too big by", diff, error
            else:
                print "  ", error
            print "   Memcheck:%s" % error.supptype()
        else:
            print error

        # Display backtrace
        #backtrace = [ func for func in error.backtrace if func.name != "-unknown-" ]
        backtrace = [ func for func in error.backtrace ]
        for func in backtrace:
            if assupp:
                print "  ", func.assupp()
            else:
                print "   > %s" % func
        if assupp:
            print "}"

    # Display memory errors count
    print "Total: %s (%s)" % (len(displayed), len(errors))
    print

def main():
    # Read log filename
    if len(sys.argv) != 2:
        usage()
        sys.exit(1)
    filename = sys.argv[1]

    # Parse input log
    parser = ValgrindParser( open(filename, "r"), False )

    # Display all errors
    displayErrors(parser.errors, None, False, True)

    # Display memory leaks in reverse order (bigest to smallest leak)
    # Only display top 10 leaks
#    displayErrors(parser.leaks, 10, True)

    # Display all leaks as suppressions
    displayErrors(parser.leaks, None, False, True)

    if parser.skipped_errors:
        print "Skipped errors: %s" % parser.skipped_errors

    if parser.skipped_leaks:
        print "Skipped memory leaks: %s" % parser.skipped_leaks

if __name__ == "__main__":
    main()

