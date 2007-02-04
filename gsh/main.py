# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Library General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 59 Temple Place - Suite 330, Boston, MA 02111-1307, USA.
#
# See the COPYING file for license information.
#
# Copyright (c) 2006, 2007 Guillaume Chazarain <guichaz@yahoo.fr>

# Requires python 2.4

import asyncore
import atexit
import locale
import optparse
import os
import signal
import sys

if sys.hexversion < 0x02040000:
        print >> sys.stderr, 'Your python version is too old (%s)' % \
                                                        (sys.version.split()[0])
        print >> sys.stderr, 'You need at least Python 2.4'
        sys.exit(1)

from gsh import remote_dispatcher
from gsh.console import show_status, watch_window_size
from gsh import control_shell
from gsh.stdin import the_stdin_thread, restore_streams_flags_at_exit
from gsh.host_syntax import expand_syntax

def kill_all():
    """When gsh quits, we kill all the remote shells we started"""
    for i in remote_dispatcher.all_instances():
        os.kill(i.pid, signal.SIGKILL)

def parse_cmdline():
    usage = '%s [OPTIONS] HOSTS...' % (sys.argv[0])
    parser = optparse.OptionParser(usage)
    try:
        parser.add_option('--log-dir', type='str', dest='log_dir',
                          help='directory to log each machine conversation' +
                                                                      ' [none]')
    except optparse.OptionError:
        # Starting with python-2.4 'str' is recognized as an alias to 'string',
        # so we use this to check the python version
        print >> sys.stderr, 'Your python version is too old (%s)' % \
                                                        (sys.version.split()[0])
        print >> sys.stderr, 'You need at least Python 2.4'
        sys.exit(1)
    parser.add_option('--command', type='str', dest='command', default=None,
                      help='command to execute on the remote shells',
                      metavar='CMD')
    parser.add_option('--ssh', type='str', dest='ssh', default='ssh',
                      help='ssh command to use [ssh]', metavar='SSH')
    parser.add_option('--shell-expand-ssh', action='store_true',
                      dest='shell_expand_ssh',
                      help='shell expand the command used to launch ssh')
    parser.add_option('--quick-sh', action='store_true', dest='quick_sh',
                      help='Do not launch a full ssh session',)
    parser.add_option('--print-first', action='store_true', dest='print_first',
                      help='print first line [by default all lines]')
    parser.add_option('--abort-errors', action='store_true', dest='abort_error',
                      help='abort if hosts are failing [by default ignore]')
    parser.add_option('--debug', action='store_true', dest='debug',
                      help='fill the logs with debug informations')
    parser.add_option('--profile', action='store_true', dest='profile',
                      default=False, help=optparse.SUPPRESS_HELP)

    options, args = parser.parse_args()
    if not args:
        parser.error('no hosts given')

    if options.quick_sh and options.ssh != 'ssh':
        parser.error('--ssh and --quick-sh are mutually exclusive')

    return options, args

def main_loop():
    while True:
        try:
            while True:
                completed, total = remote_dispatcher.count_completed_processes()
                if completed == total:
                    # Time to use raw_input() in the stdin thread
                    the_stdin_thread.ready_event.set()
                if not the_stdin_thread.ready_event.isSet():
                    # Otherwise, just print the status
                    show_status(completed, total)
                if remote_dispatcher.all_terminated():
                    raise asyncore.ExitNow
                asyncore.loop(count=1, timeout=None)
                remote_dispatcher.handle_unfinished_lines()
        except KeyboardInterrupt:
            control_shell.launch()
        except asyncore.ExitNow:
            sys.exit(0)

def _profile(continuation):
    prof_file = 'gsh.prof'
    try:
        import cProfile
        import pstats
        print 'Profiling using cProfile'
        cProfile.runctx('continuation()', globals(), locals(), prof_file)
        stats = pstats.Stats(prof_file)
    except ImportError:
        import hotshot
        import hotshot.stats
        prof = hotshot.Profile(prof_file, lineevents=1)
        print 'Profiling using hotshot'
        prof.runcall(continuation)
        prof.close()
        stats = hotshot.stats.load(prof_file)
    stats.strip_dirs()
    stats.sort_stats('time', 'calls')
    stats.print_stats(50)
    stats.print_callees(50)
    os.remove(prof_file)

def main():
    """Launch gsh"""
    locale.setlocale(locale.LC_ALL, '')
    options, args = parse_cmdline()
    control_shell.make_singleton(options)

    if options.log_dir:
        try:
            os.mkdir(options.log_dir)
        except OSError:
            pass # The dir already exists

    atexit.register(kill_all)
    for arg in args:
        for host in expand_syntax(arg):
            remote_dispatcher.remote_dispatcher(options, host)

    watch_window_size()

    restore_streams_flags_at_exit()
    the_stdin_thread.activate(not options.command)

    if options.profile:
        def safe_main_loop():
            try:
                main_loop()
            except:
                pass
        _profile(safe_main_loop)
    else:
        main_loop()
