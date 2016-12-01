"""
"perf timeit" microbenchmark command based on the Python timeit module.
"""
from __future__ import division, print_function, absolute_import

import sys
import timeit

import perf
from perf._cli import display_title, format_checks
from perf._utils import get_python_names, abs_executable
from perf._runner import Runner
from perf._timeit import timeit_sample_func


DEFAULT_NAME = 'timeit'


def add_cmdline_args(cmd, args):
    cmd.extend(('--name', args.name))
    if args.inner_loops:
        cmd.extend(('--inner-loops', str(args.inner_loops)))
    for setup in args.setup:
        cmd.extend(("--setup", setup))
    if args.duplicate:
        cmd.extend(('--duplicate', str(args.duplicate)))
    cmd.extend(args.stmt)


class TimeitRunner(Runner):
    def __init__(self, *args, **kw):
        if 'program_args' not in kw:
            kw['program_args'] = ('-m', 'perf', 'timeit')
        kw['add_cmdline_args'] = add_cmdline_args
        Runner.__init__(self, *args, **kw)

        def parse_name(name):
            return name.strip()

        cmd = self.argparser
        cmd.add_argument('--name', type=parse_name,
                         help='Benchmark name (default: %r)' % DEFAULT_NAME)
        cmd.add_argument('-s', '--setup', action='append', default=[],
                         help='setup statements')
        cmd.add_argument('--inner-loops',
                         type=int,
                         help='Number of inner loops per sample. For example, '
                              'the number of times that the code is copied '
                              'manually multiple times to reduce the overhead '
                              'of the outer loop.')
        cmd.add_argument("--compare-to", metavar="REF_PYTHON",
                         help='Run benchmark on the Python executable REF_PYTHON, '
                              'run benchmark on Python executable PYTHON, '
                              'and then compare REF_PYTHON result to PYTHON result')
        cmd.add_argument('--duplicate', type=int,
                         help='duplicate statements to reduce the overhead of '
                              'the outer loop and multiply inner_loops '
                              'by DUPLICATE')
        cmd.add_argument('stmt', nargs='+', help='executed statements')

    def _process_args(self):
        Runner._process_args(self)
        args = self.args
        if args.compare_to:
            args.compare_to = abs_executable(args.compare_to)

        self._show_name = bool(args.name)
        if not args.name:
            args.name = DEFAULT_NAME

    def bench_compare(self, python, loops):
        args = self.args
        # FIXME: it's no more needed to manually save/restore loops
        args.loops = loops
        args.python = python
        args.compare = None
        return self._spawn_workers(newline=False)


def _format_stmt(statements):
    result = []
    for stmt in statements:
        stmt = stmt.rstrip()
        if stmt:
            result.append(stmt)
    if not result:
        result.append('pass')
    return result


def _stmt_metadata(statements):
    return ' '.join(repr(stmt) for stmt in statements)


def create_timer(stmt, setup):
    # Include the current directory, so that local imports work (sys.path
    # contains the directory of this script, rather than the current
    # directory)
    import os
    sys.path.insert(0, os.curdir)

    stmt = "\n".join(stmt)
    setup = "\n".join(setup)

    return timeit.Timer(stmt, setup, timer=perf.perf_counter)


def cmd_compare(runner):
    from perf._compare import timeit_compare_benchs

    args = runner.args
    for option in ('output', 'append', 'worker'):
        if getattr(args, option):
            print("ERROR: --%s option is not supported in compare mode"
                  % option)
            sys.exit(1)

    # need a local copy, because bench_compare() modifies args
    loops = args.loops
    python1 = args.compare_to
    python2 = args.python
    name1, name2 = get_python_names(python1, python2)

    multiline = runner._multiline_output()

    benchs = []
    for python, name in ((python1, name1), (python2, name2)):
        if multiline:
            display_title('Benchmark %s' % name)
        elif not args.quiet:
            print(name, end=': ')

        bench = runner.bench_compare(python, loops)
        benchs.append(bench)
        if multiline:
            runner._display_result(bench)
        elif not args.quiet:
            print(' %s' % bench.format())

        if multiline:
            print()
        elif not args.quiet:
            warnings = format_checks(bench)
            for line in warnings:
                print(line)

    bench1, bench2 = benchs
    if multiline:
        display_title('Compare')
    elif not args.quiet:
        print()
    timeit_compare_benchs(name1, bench1, name2, bench2, args)


def main(runner):
    args = runner.args

    args.setup = _format_stmt(args.setup)
    args.stmt = _format_stmt(args.stmt)

    # args must not be modified, it's passed to the worker process,
    # so use local variables.
    stmt = args.stmt
    inner_loops = args.inner_loops
    if args.duplicate and args.duplicate > 1:
        stmt = stmt * args.duplicate
        if inner_loops:
            inner_loops *= args.duplicate
        else:
            inner_loops = args.duplicate
        runner.metadata['timeit_duplicate'] = args.duplicate

    runner.metadata['timeit_setup'] = _stmt_metadata(args.setup)
    runner.metadata['timeit_stmt'] = _stmt_metadata(args.stmt)

    if args.compare_to:
        cmd_compare(runner)
    else:
        timer = create_timer(stmt, runner.args.setup)

        kwargs = {}
        if inner_loops:
            kwargs['inner_loops'] = inner_loops

        try:
            runner.bench_sample_func(args.name, timeit_sample_func,
                                     timer, **kwargs)
        except SystemExit:
            raise
        except:
            timer.print_exc()
            sys.exit(1)
