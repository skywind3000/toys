#! /usr/bin/env python
# -*- coding: utf-8 -*-
#======================================================================
#
# quickrun_test.py - test suite for quickrun.py comment extractors
#
# Covers every language extractor registered in EXTRACTORS:
#   C-style (c/cpp/cs/java/js/ts/go...), Rust, Pascal, PHP, Perl,
#   Bash, Lua, Haskell, Erlang, PowerShell, Python.
#
# For each language the suite checks:
#   - line-comment extraction (marker stripped, content intact)
#   - block-comment extraction (multi-line, delimiters stripped)
#   - comment markers inside string literals are NOT extracted
#   - line-number attribution for line and block comments
#   - multiple comments on the same source line are merged
#   - @command directives parse end-to-end via configure/load
#   - platform-conditional commands override unconditional ones
#   - triple-quoted Python strings are not scanned for @command
#   - missing file / unknown extension -> graceful failure, no raise
#   - $(VAR) substitution and exit-code propagation at run time
#
# Run:  python quickrun_test.py
#
# Created by skywind on 2026/06/26
# Last Modified: 2026/06/26 14:38:46
#
#======================================================================
import os
import sys
import shutil
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import quickrun as qr


#----------------------------------------------------------------------
# mini assert helpers (no third-party deps)
#----------------------------------------------------------------------
_stats = [0, 0]   # [passed, failed]

def check (name, cond):
    if cond:
        _stats[0] += 1
    else:
        _stats[1] += 1
        print('  FAIL: %s' % name)

def eq (name, got, want):
    if got == want:
        _stats[0] += 1
    else:
        _stats[1] += 1
        print('  FAIL: %s' % name)
        print('    got : %r' % (got,))
        print('    want: %r' % (want,))

def texts (comments):
    # extract just the comment text, drop line numbers
    return [t for lnum, t in comments]

def has (name, lst, sub):
    check(name, any(sub in t for t in lst))

def none (name, lst, sub):
    check(name, not any(sub in t for t in lst))


#----------------------------------------------------------------------
# C-style: // line, /* */ block  (c/cpp/cs/java/js/ts/as/go)
#----------------------------------------------------------------------
def test_cpp ():
    code = r'''
int main() {
    const char *a = "// not comment";
    const char *b = "/* not block */";
    // cpp line
    /* cpp block
       cpp block line two */
    /// cpp doc line
    // @command(build): g++ $(FILENAME)
}
'''
    lst = texts(qr.extract_cpp_comments(code))
    has('cpp:line', lst, 'cpp line')
    has('cpp:block1', lst, 'cpp block')
    has('cpp:block2', lst, 'cpp block line two')
    has('cpp:doc', lst, 'cpp doc line')
    has('cpp:command', lst, '@command(build): g++ $(FILENAME)')
    none('cpp:str not comment', lst, 'not comment')
    none('cpp:str not block', lst, 'not block')


#----------------------------------------------------------------------
# Python: # line (triple-quoted strings are skipped, not comments)
#----------------------------------------------------------------------
def test_python ():
    code = r'''
s = "# not comment"
t = "// not comment"
u = r"raw # not comment"
# python line
# @command(run): python $(FILENAME)
"""
docstring: not a comment
@command(bad): should not appear
"""
'''
    lst = texts(qr.extract_python_comments(code))
    has('py:line', lst, 'python line')
    has('py:command', lst, '@command(run): python $(FILENAME)')
    none('py:str hash', lst, 'not comment')
    none('py:docstring', lst, 'should not appear')


#----------------------------------------------------------------------
# Pascal: { } block, (* *) block, // line
#----------------------------------------------------------------------
def test_pascal ():
    code = r'''
program t;
var s: string;
begin
  s := 'a { not block } // not line (* not star *)';
  { pascal brace block
    brace line two }
  (* pascal star block
     star line two *)
  // pascal slash line
  { @command(build): fpc $(FILENAME) }
  (* @command(run): ./$(FILENOEXT) *)
end.
'''
    lst = texts(qr.extract_pascal_comments(code))
    has('pas:brace1', lst, 'pascal brace block')
    has('pas:brace2', lst, 'brace line two')
    has('pas:star1', lst, 'pascal star block')
    has('pas:star2', lst, 'star line two')
    has('pas:slash', lst, 'pascal slash line')
    has('pas:cmd build', lst, '@command(build): fpc $(FILENAME)')
    has('pas:cmd run', lst, '@command(run): ./$(FILENOEXT)')
    none('pas:str not block', lst, 'not block')
    none('pas:str not line', lst, 'not line')
    none('pas:str not star', lst, 'not star')


#----------------------------------------------------------------------
# Rust: // line, /* */ block  (reuses the C-style extractor)
#----------------------------------------------------------------------
def test_rust ():
    code = r'''
fn main() {
    let _ = "// not comment /* not block */";
    // rust line
    /* rust block
       rust block two */
    /// rust doc line
    // @command(build): rustc $(FILENAME)
}
'''
    lst = texts(qr.extract_cpp_comments(code))
    has('rs:line', lst, 'rust line')
    has('rs:block1', lst, 'rust block')
    has('rs:block2', lst, 'rust block two')
    has('rs:doc', lst, 'rust doc line')
    has('rs:command', lst, '@command(build): rustc $(FILENAME)')
    none('rs:str not comment', lst, 'not comment')
    none('rs:str not block', lst, 'not block')


#----------------------------------------------------------------------
# PHP: // and # line, /* */ block
#----------------------------------------------------------------------
def test_php ():
    code = r'''
<?php
$s = "// not comment # not hash /* not block */";
// php slash line
# php hash line
/* php block
   php block two */
// @command(run): php $(FILENAME)
?>
'''
    lst = texts(qr.extract_php_comments(code))
    has('php:slash', lst, 'php slash line')
    has('php:hash', lst, 'php hash line')
    has('php:block1', lst, 'php block')
    has('php:block2', lst, 'php block two')
    has('php:command', lst, '@command(run): php $(FILENAME)')
    none('php:str not comment', lst, 'not comment')
    none('php:str not hash', lst, 'not hash')
    none('php:str not block', lst, 'not block')


#----------------------------------------------------------------------
# Perl: # line (POD blocks are not extracted)
#----------------------------------------------------------------------
def test_perl ():
    code = r'''
my $s = "a # not comment";
my $t = 'b # not comment';
# perl line
# @command(run): perl $(FILENAME)
'''
    lst = texts(qr.extract_perl_comments(code))
    has('pl:line', lst, 'perl line')
    has('pl:command', lst, '@command(run): perl $(FILENAME)')
    none('pl:str1', lst, 'not comment')
    none('pl:str2', lst, 'not comment')


#----------------------------------------------------------------------
# Bash/shell: # line
#----------------------------------------------------------------------
def test_bash ():
    code = '''#!/bin/bash
s="a # not comment"
echo "b # not comment"
# bash line
# @command(run): bash $(FILENAME)
'''
    lst = texts(qr.extract_bash_comments(code))
    has('sh:shebang', lst, '!/bin/bash')
    has('sh:line', lst, 'bash line')
    has('sh:command', lst, '@command(run): bash $(FILENAME)')
    none('sh:str1', lst, 'not comment')
    none('sh:str2', lst, 'not comment')


#----------------------------------------------------------------------
# Lua: -- line, --[[ ]] block  ([[ ]] long strings are skipped)
#----------------------------------------------------------------------
def test_lua ():
    code = r'''
local s = "a -- not comment"
local t = [[ multi
  -- not comment in long string
]]
-- lua line
--[[ lua block
  lua block two ]]
-- @command(run): lua $(FILENAME)
'''
    lst = texts(qr.extract_lua_comments(code))
    has('lua:line', lst, 'lua line')
    has('lua:block1', lst, 'lua block')
    has('lua:block2', lst, 'lua block two')
    has('lua:command', lst, '@command(run): lua $(FILENAME)')
    none('lua:str', lst, 'not comment')
    none('lua:longstr', lst, 'not comment in long string')


#----------------------------------------------------------------------
# Haskell: -- line, {- -} block
#----------------------------------------------------------------------
def test_haskell ():
    code = r'''
main = putStrLn "a -- not comment"
-- haskell line
{- haskell block
   haskell block two -}
-- @command(run): runhaskell $(FILENAME)
'''
    lst = texts(qr.extract_haskell_comments(code))
    has('hs:line', lst, 'haskell line')
    has('hs:block1', lst, 'haskell block')
    has('hs:block2', lst, 'haskell block two')
    has('hs:command', lst, '@command(run): runhaskell $(FILENAME)')
    none('hs:str', lst, 'not comment')


#----------------------------------------------------------------------
# Erlang: % line
#----------------------------------------------------------------------
def test_erlang ():
    code = r'''
-module(t).
f() -> S = "a % not comment", ok.
% erlang line
% @command(compile): erlc $(FILENAME)
'''
    lst = texts(qr.extract_erlang_comments(code))
    has('erl:line', lst, 'erlang line')
    has('erl:command', lst, '@command(compile): erlc $(FILENAME)')
    none('erl:str', lst, 'not comment')


#----------------------------------------------------------------------
# PowerShell: # line, <# #> block
#----------------------------------------------------------------------
def test_powershell ():
    code = r'''
$s = "a # not comment"
# powershell line
<# powershell block
   powershell block two #>
# @command(run): pwsh $(FILENAME)
'''
    lst = texts(qr.extract_powershell_comments(code))
    has('ps:line', lst, 'powershell line')
    has('ps:block1', lst, 'powershell block')
    has('ps:block2', lst, 'powershell block two')
    has('ps:command', lst, '@command(run): pwsh $(FILENAME)')
    none('ps:str', lst, 'not comment')


#----------------------------------------------------------------------
# line-number attribution
#----------------------------------------------------------------------
def test_line_numbers ():
    lines = [
        'x = 1  // first',     # 1
        'y = 2',               # 2
        '/* block start',      # 3
        ' block cont',         # 4
        ' block end */',       # 5
        'z = 3  // sixth',     # 6
    ]
    code = '\n'.join(lines) + '\n'
    expected = [
        (1, 'first'),
        (3, 'block start'),
        (4, 'block cont'),
        (5, 'block end'),
        (6, 'sixth'),
    ]
    eq('ln:cpp block', qr.extract_cpp_comments(code), expected)

    lines = [
        'x = 1  # first',      # 1
        'y = 2',               # 2
        '# third',             # 3
        'z = 3  # fourth',     # 4
    ]
    code = '\n'.join(lines) + '\n'
    expected = [
        (1, 'first'),
        (3, 'third'),
        (4, 'fourth'),
    ]
    eq('ln:python', qr.extract_python_comments(code), expected)


#----------------------------------------------------------------------
# multiple comments on the same source line are merged with a space
#----------------------------------------------------------------------
def test_same_line_join ():
    code = '/* a */ /* b */ // c\n'
    eq('join:cpp', texts(qr.extract_cpp_comments(code)), ['a b c'])


#----------------------------------------------------------------------
# EXTRACTORS registry: every supported extension maps correctly
#----------------------------------------------------------------------
def test_registry ():
    cases = [
        ('.c', qr.extract_cpp_comments),
        ('.cc', qr.extract_cpp_comments),
        ('.cxx', qr.extract_cpp_comments),
        ('.cpp', qr.extract_cpp_comments),
        ('.h', qr.extract_cpp_comments),
        ('.hpp', qr.extract_cpp_comments),
        ('.hh', qr.extract_cpp_comments),
        ('.cs', qr.extract_cpp_comments),
        ('.java', qr.extract_cpp_comments),
        ('.js', qr.extract_cpp_comments),
        ('.ts', qr.extract_cpp_comments),
        ('.as', qr.extract_cpp_comments),
        ('.go', qr.extract_cpp_comments),
        ('.rs', qr.extract_cpp_comments),
        ('.pas', qr.extract_pascal_comments),
        ('.pp', qr.extract_pascal_comments),
        ('.dpr', qr.extract_pascal_comments),
        ('.lpr', qr.extract_pascal_comments),
        ('.php', qr.extract_php_comments),
        ('.phtml', qr.extract_php_comments),
        ('.pl', qr.extract_perl_comments),
        ('.pm', qr.extract_perl_comments),
        ('.sh', qr.extract_bash_comments),
        ('.bash', qr.extract_bash_comments),
        ('.lua', qr.extract_lua_comments),
        ('.hs', qr.extract_haskell_comments),
        ('.erl', qr.extract_erlang_comments),
        ('.hrl', qr.extract_erlang_comments),
        ('.ps1', qr.extract_powershell_comments),
        ('.psm1', qr.extract_powershell_comments),
        ('.py', qr.extract_python_comments),
    ]
    for ext, fn in cases:
        eq('reg:%s' % ext, qr.EXTRACTORS.get(ext), fn)
    check('reg:unsupported absent', '.rb' not in qr.EXTRACTORS)


#----------------------------------------------------------------------
# end-to-end: @command directives parse into configure.commands
#----------------------------------------------------------------------
ENDTOEND = [
    ('.cpp',
     '// @command(build): g++ $(FILENAME)\n// @command(run): ./$(FILENOEXT)\n',
     {'build': 'g++ $(FILENAME)', 'run': './$(FILENOEXT)'}),
    ('.py',
     '# @command(run): python $(FILENAME)\n',
     {'run': 'python $(FILENAME)'}),
    ('.pas',
     '{ @command(build): fpc $(FILENAME) }\n(* @command(run): ./$(FILENOEXT) *)\n',
     {'build': 'fpc $(FILENAME)', 'run': './$(FILENOEXT)'}),
    ('.rs',
     '// @command(build): rustc $(FILENAME)\n/* @command(run): ./$(FILENOEXT) */\n',
     {'build': 'rustc $(FILENAME)', 'run': './$(FILENOEXT)'}),
    ('.php',
     '// @command(a): php $(FILENAME)\n# @command(b): echo hi\n/* @command(c): rm x */\n',
     {'a': 'php $(FILENAME)', 'b': 'echo hi', 'c': 'rm x'}),
    ('.pl',
     '# @command(run): perl $(FILENAME)\n',
     {'run': 'perl $(FILENAME)'}),
    ('.sh',
     '# @command(run): bash $(FILENAME)\n',
     {'run': 'bash $(FILENAME)'}),
    ('.lua',
     '-- @command(run): lua $(FILENAME)\n--[[ @command(clean): rm x ]]\n',
     {'run': 'lua $(FILENAME)', 'clean': 'rm x'}),
    ('.hs',
     '-- @command(run): runhaskell $(FILENAME)\n{- @command(clean): rm x -}\n',
     {'run': 'runhaskell $(FILENAME)', 'clean': 'rm x'}),
    ('.erl',
     '% @command(compile): erlc $(FILENAME)\n',
     {'compile': 'erlc $(FILENAME)'}),
    ('.ps1',
     '# @command(run): pwsh $(FILENAME)\n<# @command(clean): rm x #>\n',
     {'run': 'pwsh $(FILENAME)', 'clean': 'rm x'}),
]

def _write (ext, code):
    # write a temp source file and return a configure() bound to it
    d = tempfile.mkdtemp(prefix='qrtest_')
    path = os.path.join(d, 'sample' + ext)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(code)
    return qr.configure(path), d

def test_endtoend ():
    for ext, code, expected in ENDTOEND:
        cc, d = _write(ext, code)
        try:
            eq('e2e:%s load' % ext, cc.load(), 0)
            eq('e2e:%s commands' % ext, cc.commands, expected)
        finally:
            shutil.rmtree(d)


#----------------------------------------------------------------------
# platform-conditional commands override unconditional ones (both orders)
#----------------------------------------------------------------------
def test_precedence ():
    code1 = ('# @command(run): echo default\n'
             '# @command(run/win32): echo windows\n')
    cc, d = _write('.py', code1)
    try:
        eq('prec:load1', cc.load(), 0)
        want = 'echo windows' if cc.target == 'win32' else 'echo default'
        eq('prec:run1 on %s' % cc.target, cc.commands.get('run'), want)
    finally:
        shutil.rmtree(d)
    code2 = ('# @command(run/win32): echo windows\n'
             '# @command(run): echo default\n')
    cc, d = _write('.py', code2)
    try:
        eq('prec:load2', cc.load(), 0)
        want = 'echo windows' if cc.target == 'win32' else 'echo default'
        eq('prec:run2 on %s' % cc.target, cc.commands.get('run'), want)
    finally:
        shutil.rmtree(d)


#----------------------------------------------------------------------
# triple-quoted Python strings are not scanned for @command
#----------------------------------------------------------------------
def test_docstring ():
    code = '"""\n@command(bad): echo nope\n"""\n# @command(good): echo yes\n'
    cc, d = _write('.py', code)
    try:
        eq('doc:load', cc.load(), 0)
        check('doc:bad absent', 'bad' not in cc.commands)
        eq('doc:good', cc.commands.get('good'), 'echo yes')
    finally:
        shutil.rmtree(d)


#----------------------------------------------------------------------
# error handling: missing file / unknown extension -> no exception
#----------------------------------------------------------------------
def test_errors ():
    missing = os.path.join(tempfile.gettempdir(), 'qrtest_no_such_file.py')
    if os.path.exists(missing):
        missing = missing + '.missing'
    cc = qr.configure(missing)
    eq('err:missing extract', cc.extract_comments(missing), None)
    eq('err:missing load', cc.load(), -1)
    d = tempfile.mkdtemp(prefix='qrtest_')
    path = os.path.join(d, 'sample.rb')
    with open(path, 'w', encoding='utf-8') as f:
        f.write('x = 1\n')
    try:
        cc = qr.configure(path)
        eq('err:unsupported extract', cc.extract_comments(path), None)
        eq('err:unsupported load', cc.load(), -1)
    finally:
        shutil.rmtree(d)


#----------------------------------------------------------------------
# run time: $(VAR) substitution and exit-code propagation
#----------------------------------------------------------------------
def test_run ():
    # substitution: $(FILENOEXT) is replaced before the shell runs;
    # capture the echoed name via a redirect into a temp file
    code = '# @command(greet): echo "$(FILENOEXT)" > out.txt\n'
    cc, d = _write('.sh', code)
    try:
        eq('run:load', cc.load(), 0)
        eq('run:exit', cc.quickrun('greet'), 0)
        with open(os.path.join(d, 'out.txt'), encoding='utf-8') as f:
            content = f.read()
        check('run:subst', 'sample' in content)
    finally:
        shutil.rmtree(d)
    # exit-code propagation: command exit code becomes quickrun return
    code = '# @command(ok): exit 0\n# @command(bad): exit 3\n'
    cc, d = _write('.sh', code)
    try:
        eq('run:load2', cc.load(), 0)
        eq('run:exit ok', cc.quickrun('ok'), 0)
        eq('run:exit bad', cc.quickrun('bad'), 3)
    finally:
        shutil.rmtree(d)
    # undefined command -> exit 1
    code = '# @command(only): echo hi\n'
    cc, d = _write('.sh', code)
    try:
        eq('run:load3', cc.load(), 0)
        eq('run:unknown', cc.quickrun('nope'), 1)
    finally:
        shutil.rmtree(d)


#----------------------------------------------------------------------
# runner
#----------------------------------------------------------------------
def main ():
    tests = [
        test_cpp, test_python, test_pascal, test_rust, test_php,
        test_perl, test_bash, test_lua, test_haskell, test_erlang,
        test_powershell, test_line_numbers, test_same_line_join,
        test_registry, test_endtoend, test_precedence, test_docstring,
        test_errors, test_run,
    ]
    for t in tests:
        print('== %s ==' % t.__name__)
        t()
    print('')
    print('total: %d, passed: %d, failed: %d' % (
        _stats[0] + _stats[1], _stats[0], _stats[1]))
    return 1 if _stats[1] else 0


if __name__ == '__main__':
    sys.exit(main())
