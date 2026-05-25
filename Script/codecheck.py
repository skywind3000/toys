#! /usr/bin/env python3
# -*- coding: utf-8 -*-
#======================================================================
#
# codecheck.py - 
#
# Created by skywind on 2026/05/23
# Last Modified: 2026/05/23 20:54:47
#
#======================================================================
import sys
import os
import time
import re
import shutil
import subprocess
import shlex


#----------------------------------------------------------------------
# version
#----------------------------------------------------------------------
VERSION = '0.1.0'


#----------------------------------------------------------------------
# tokenize
#----------------------------------------------------------------------
def tokenize(code, specs, eof = None):
    patterns = []
    definition = {}
    extended = {}
    if not specs:
        return None
    for index in range(len(specs)):
        spec = specs[index]
        name, pattern = spec[:2]
        pn = 'PATTERN%d'%index
        definition[pn] = name
        if len(spec) >= 3:
            extended[pn] = spec[2]
        patterns.append((pn, pattern))
    tok_regex = '|'.join('(?P<%s>%s)' % pair for pair in patterns)
    line_starts = []
    pos = 0
    index = 0
    while 1:
        line_starts.append(pos)
        pos = code.find('\n', pos)
        if pos < 0:
            break
        pos += 1
    line_num = 0
    for mo in re.finditer(tok_regex, code):
        kind = mo.lastgroup
        value = mo.group()
        start = mo.start()
        while line_num < len(line_starts) - 1:
            if line_starts[line_num + 1] > start:
                break
            line_num += 1
        line_start = line_starts[line_num]
        name = definition[kind]
        if name is None:
            continue
        if callable(name):
            if kind not in extended:
                obj = name(value)
            else:
                obj = name(value, extended[kind])
            name = None
            if isinstance(obj, list) or isinstance(obj, tuple):
                if len(obj) > 0: 
                    name = obj[0]
                if len(obj) > 1:
                    value = obj[1]
            else:
                name = obj
        yield (name, value, line_num + 1, start - line_start + 1)
    if eof is not None:
        line_start = line_starts[-1]
        endpos = len(code)
        yield (eof, '', len(line_starts), endpos - line_start + 1)
    return 0


#----------------------------------------------------------------------
# patterns
#----------------------------------------------------------------------
PATTERN_WHITESPACE = r'[ \t\r\n]+'
PATTERN_COMMENT1 = r'\/\/.*'
PATTERN_COMMENT2 = r'\/\*([^*]|[\r\n]|(\*+([^*/]|[\r\n])))*\*+\/'
PATTERN_NAME = r'\w+'
PATTERN_STRING1 = r"'(?:\\.|[^'\\])*'"
PATTERN_STRING2 = r'"(?:\\.|[^"\\])*"'
PATTERN_NUMBER = r'\d+(\.\d*)?'
PATTERN_CINTEGER = r'(0x)?\d+[uUlLbB]*'
PATTERN_MISMATCH = r'.'
PATTERN_PY_COMMENT = r'\#.*'
PATTERN_PY_STRING3D = r'"""(?:[^"\\]|\\.|"(?!""))*"""'
PATTERN_PY_STRING3S = r"'''(?:[^'\\]|\\.|'(?!''))*'''"
PATTERN_PY_PSTR3D = r'[bBfFrR]{1,2}"""(?:[^"\\]|\\.|"(?!""))*"""'
PATTERN_PY_PSTR3S = r"[bBfFrR]{1,2}'''(?:[^'\\]|\\.|'(?!''))*'''"
PATTERN_PY_PSTR1 = r"[bBfFrR]{1,2}'(?:\\.|[^'\\\r\n])*'"
PATTERN_PY_PSTR2 = r'[bBfFrR]{1,2}"(?:\\.|[^"\\\r\n])*"'
PATTERN_PY_STR1 = r"'(?:\\.|[^'\\\r\n])*'"
PATTERN_PY_STR2 = r'"(?:\\.|[^"\\\r\n])*"'
PATTERN_PY_MISMATCH = r'.'


#----------------------------------------------------------------------
# returns a list of (line, comment) pairs for python
#----------------------------------------------------------------------
def extract_python_comments(code):
    specs = [
        ('WHITESPACE', PATTERN_WHITESPACE),
        ('PY_COMMENT', PATTERN_PY_COMMENT),
        ('PY_STRING3D', PATTERN_PY_STRING3D),
        ('PY_STRING3S', PATTERN_PY_STRING3S),
        ('PY_PSTR3D', PATTERN_PY_PSTR3D),
        ('PY_PSTR3S', PATTERN_PY_PSTR3S),
        ('PY_PSTR1', PATTERN_PY_PSTR1),
        ('PY_PSTR2', PATTERN_PY_PSTR2),
        ('PY_STR1', PATTERN_PY_STR1),
        ('PY_STR2', PATTERN_PY_STR2),
        ('NAME', PATTERN_NAME),
        ('NUMBER', PATTERN_NUMBER),
        ('PY_MISMATCH', PATTERN_PY_MISMATCH)
    ]
    comments = {}
    for name, value, lnum, column in tokenize(code, specs):
        if name == 'PY_COMMENT':
            comment = value.strip('\r\n\t ')
            if comment.startswith('#'):
                comment = comment[1:].strip()
            if comment:
                if lnum not in comments:
                    comments[lnum] = []
                comments[lnum].append(comment)
        elif name in ('PY_STRING3D', 'PY_STRING3S'):
            text = value[3:-3].strip('\r\n\t ')
            line = lnum
            for part in text.split('\n'):
                part = part.strip('\r\n\t ')
                if part:
                    if line not in comments:
                        comments[line] = []
                    comments[line].append(part)
                line += 1
        elif name in ('PY_PSTR3D', 'PY_PSTR3S'):
            # prefix triple-quoted: strip prefix + quotes
            idx = value.index('"') if '"' in value[:4] else value.index("'")
            text = value[idx + 3:-3].strip('\r\n\t ')
            line = lnum
            for part in text.split('\n'):
                part = part.strip('\r\n\t ')
                if part:
                    if line not in comments:
                        comments[line] = []
                    comments[line].append(part)
                line += 1
    output = []
    lines = list(comments.keys())
    lines.sort()
    for lnum in lines:
        comment = comments[lnum]
        text = ' '.join(comment)
        text = text.strip('\r\n\t ')
        if not text:
            continue
        output.append((lnum, text))
    return output


#----------------------------------------------------------------------
# returns a list of (line, comment) pairs
#----------------------------------------------------------------------
def extract_cpp_comments(code):
    specs = [
        ('WHITESPACE', PATTERN_WHITESPACE),
        ('COMMENT1', PATTERN_COMMENT1),
        ('COMMENT2', PATTERN_COMMENT2),
        ('NAME', PATTERN_NAME),
        ('STRING', PATTERN_STRING1),
        ('STRING', PATTERN_STRING2),
        ('NUMBER', PATTERN_NUMBER),
        ('CINTEGER', PATTERN_CINTEGER),
        ('MISMATCH', PATTERN_MISMATCH)
    ]
    comments = {}
    for name, value, lnum, column in tokenize(code, specs):
        if name == 'COMMENT1':
            comment = value.strip('\r\n\t ')
            if comment.startswith('//'):
                comment = comment[2:].strip()
            if comment:
                if lnum not in comments:
                    comments[lnum] = []
                comments[lnum].append(comment)
        elif name == 'COMMENT2':
            comment = value.strip('\r\n\t ')
            if comment.startswith('/*'):
                comment = comment[2:]
            if comment.endswith('*/'):
                comment = comment[:-2]
            comment = comment.strip('\r\n\t ')
            line = lnum
            for text in comment.split('\n'):
                text = text.strip('\r\n\t ')
                if text:
                    if line not in comments:
                        comments[line] = []
                    comments[line].append(text)
                line += 1
    output = []
    lines = list(comments.keys())
    lines.sort()
    for lnum in lines:
        comment = comments[lnum]
        text = ' '.join(comment)
        text = text.strip('\r\n\t ')
        if not text:
            continue
        output.append((lnum, text))
    return output


#----------------------------------------------------------------------
# code sample
#----------------------------------------------------------------------
code_sample_cpp = r'''
// My first C program
int main(void)
{
    int x = 10;
    int y = x+++3;
    printf("Hello, World !!\n");
    /* test1 */ .. /* test2 */
    return 0;
}
/* haha
test1
*/
'''


#----------------------------------------------------------------------
# sample code in python
#----------------------------------------------------------------------
code_sample_python = r'''
# My first Python program
def main():
    x = 10
    y = x + 3
    print("Hello, World !!")
    # test1
    # test2
    s = r"# not a comment"
    t = r"raw string with \""
    u = f"formatted {x}"
    return 0
"""
docstring test1
docstring test2
"""
'''

code_sample_python2 = r'''
# header comment
import os  # inline comment
r = 5  # r as variable, not raw prefix
path = r"C:\Users\test"  # raw string, \ not escape
msg = r"he said \"hello\""  # raw string with escaped quote
regex = r"\d+\.\d*"  # regex pattern
label = f"name: {name}"  # f-string
data = b"bytes here"  # byte string
doc = r"""
raw docstring line1
raw docstring line2
"""
def foo():
    """normal docstring"""
    pass
'''


#----------------------------------------------------------------------
# getopt: returns (options, args)
#----------------------------------------------------------------------
def getopt (argv, shortopts = ''):
    args = []
    options = {}
    if argv is None:
        argv = sys.argv[1:]
    index = 0
    count = len(argv)
    while index < count:
        arg = argv[index]
        if arg != '':
            head = arg[:1]
            if head != '-':
                break
            if arg in ('-', '--'):
                index += 1
                break
            if (not arg.startswith('--')) and (len(arg) == 2):
                name = arg[1]
                if (name in shortopts) and (index + 1 < count):
                    nextarg = argv[index + 1]
                    options[name] = nextarg
                    index += 2
                    continue
            name = arg.lstrip('-')
            key, _, val = name.partition('=')
            options[key.strip()] = val.strip()
        index += 1
    while index < count:
        args.append(argv[index])
        index += 1
    return options, args


#----------------------------------------------------------------------
# configure
#----------------------------------------------------------------------
class configure (object):

    def __init__ (self, ininame = None):
        t = time.time()
        self._config = {}
        self._binary = {}
        if not ininame:
            ininame = os.path.expanduser('~/.config/codecheck.ini')
        if os.path.isfile(ininame):
            self._ininame = os.path.abspath(ininame)
            self._inibase = os.path.dirname(self._ininame)
            self._config = self.load_ini(self._ininame)
        if 'default' not in self._config:
            self._config['default'] = {}
        self.win32 = (sys.platform[:3] == 'win') and True or False
        self.PATH = os.environ.get('PATH', '')
        self._locate_binary()

    # load content
    def load_file_content (self, filename, mode = 'r'):
        if hasattr(filename, 'read'):
            try: content = filename.read()
            except: content = None
            return content
        try:
            if '~' in filename:
                filename = os.path.expanduser(filename)
            fp = open(filename, mode)
            content = fp.read()
            fp.close()
        except:
            content = None
        return content

    # load file and guess encoding
    def load_file_text (self, filename, encoding = None):
        content = self.load_file_content(filename, 'rb')
        if content is None:
            return None
        if content[:3] == b'\xef\xbb\xbf':
            text = content[3:].decode('utf-8')
        elif encoding is not None:
            text = content.decode(encoding, 'ignore')
        else:
            text = None
            guess = [sys.getdefaultencoding(), 'utf-8']
            if sys.stdout and sys.stdout.encoding:
                guess.append(sys.stdout.encoding)
            try:
                import locale
                guess.append(locale.getpreferredencoding())
            except:
                pass
            visit = {}
            for name in guess + ['gbk', 'ascii', 'latin1']:
                if name in visit:
                    continue
                visit[name] = 1
                try:
                    text = content.decode(name)
                    break
                except:
                    pass
            if text is None:
                text = content.decode('utf-8', 'ignore')
        return text

    # load ini without ConfigParser
    def load_ini (self, filename, encoding = None):
        text = self.load_file_text(filename, encoding)
        config = {}
        sect = 'default'
        if text is None:
            return None
        for line in text.split('\n'):
            line = line.strip('\r\n\t ')
            # pylint: disable-next=no-else-continue
            if not line:   # noqa
                continue
            elif line[:1] in ('#', ';'):
                continue
            elif line.startswith('['):
                if line.endswith(']'):
                    sect = line[1:-1].strip('\r\n\t ')
                    if sect not in config:
                        config[sect] = {}
            else:
                pos = line.find('=')
                if pos >= 0:
                    key = line[:pos].rstrip('\r\n\t ')
                    val = line[pos + 1:].lstrip('\r\n\t ')
                    if sect not in config:
                        config[sect] = {}
                    config[sect][key] = val
        return config

    def _locate_binary (self):
        self._locate_cc()
        self._locate_python()
        return 0

    def _locate_cc (self):
        cc = ''
        if 'cc' in self._config['default']:
            cc = self._config['default']['cc']
            cc = cc.strip('\r\n\t ')
            if '~' in cc:
                cc = os.path.expanduser(cc)
            if os.path.isabs(cc):
                if not os.path.isfile(cc) or not os.access(cc, os.X_OK):
                    cc = ''
            else:
                PATH = os.environ.get('PATH', '')
                PATH = self._inibase + os.pathsep + PATH
                cc = shutil.which(cc, path = PATH)
        if not cc:
            for name in ('gcc', 'clang', 'cc'):
                cc = shutil.which(name)
                if cc:
                    break
        if cc:
            self._binary['cc'] = os.path.abspath(cc)
        return 0

    def _locate_python (self):
        py = ''
        if 'python' in self._config['default']:
            py = self._config['default']['python']
            py = py.strip('\r\n\t ')
            if '~' in py:
                py = os.path.expanduser(py)
            if os.path.isabs(py):
                if not os.path.isfile(py) or not os.access(py, os.X_OK):
                    py = ''
            else:
                PATH = os.environ.get('PATH', '')
                PATH = self._inibase + os.pathsep + PATH
                py = shutil.which(py, path = PATH)
        if not py:
            py = sys.executable
        if py:
            self._binary['python'] = os.path.abspath(py)
        return 0

    # execute command without capture, returns exit code
    def execute (self, args, cwd = None, env = None, timeout = None):
        if env:
            envcopy = os.environ.copy()
            envcopy.update(env)
            env = envcopy
        try:
            result = subprocess.run(args, cwd = cwd, env = env, 
                                    shell = False,
                                    timeout = timeout)
            return result.returncode
        except Exception as e:
            print('Error executing command: %s' % str(e))
        return -1

    # execute command and capture output, returns (exit code, stdout, stderr)
    def call (self, args, cwd = None, env = None, timeout = None, stdin = None):
        if env:
            envcopy = os.environ.copy()
            envcopy.update(env)
            env = envcopy
        if stdin:
            if isinstance(stdin, str):
                stdin = stdin.encode('utf-8', 'ignore')
        try:
            print('Executing command: %s' % ' '.join(args))
            result = subprocess.run(args, cwd = cwd, env = env,
                                    timeout = timeout,
                                    shell = False,
                                    input = stdin,
                                    stdout = subprocess.PIPE,
                                    stderr = subprocess.PIPE)
            stdout = result.stdout.decode('utf-8', 'ignore')
            stderr = result.stderr.decode('utf-8', 'ignore')
            return (result.returncode, stdout, stderr)
        except Exception as e:
            print('Error executing command: %s' % str(e))
        return (-1, '', '')

    # check source file type by extension
    def check_source_type (self, filename):
        extname = os.path.splitext(filename)[-1].lower()
        if extname in ('.c',):
            return 'c'
        elif extname in ('.cpp', '.cc', '.cxx', '.c++'):
            return 'cpp'
        elif extname in ('.py', '.pyw'):
            return 'python'
        return ''

    # extract comments from source file, 
    # returns a list of (line, comment) pairs
    def extract_comments (self, filename):
        source_type = self.check_source_type(filename)
        if not source_type:
            return None
        content = self.load_file_text(filename)
        if content is None:
            return None
        if source_type in ('c', 'cpp'):
            return extract_cpp_comments(content)
        elif source_type == 'python':
            return extract_python_comments(content)
        return None

    def gcc (self, args, cwd = None, timeout = None):
        if 'cc' not in self._binary:
            sys.stderr.write('C/C++ compiler not found\n')
            sys.exit(1)
        cc = self._binary['cc']
        dirname = os.path.dirname(os.path.abspath(cc))
        cmd = [self._binary['cc']] + args
        env = {}
        env['PATH'] = dirname + os.pathsep + os.environ.get('PATH', '')
        return self.execute(cmd, cwd = cwd, env = env, timeout = timeout)

    # set terminal color
    def console (self, color):
        if sys.platform[:3] != 'win':
            if color >= 0:
                foreground = color & 7
                background = (color >> 4) & 7
                bold = color & 8
                if background != 0:
                    sys.stdout.write("\033[%s3%d;4%dm"%(bold and "01;" or "", foreground, background))
                else:
                    sys.stdout.write("\033[%s3%dm"%(bold and "01;" or "", foreground))
                sys.stdout.flush()
            else:
                sys.stdout.write("\033[0m")
                sys.stdout.flush()
            return 0
        if '_console_handle' not in self.__dict__:
            import ctypes
            self.kernel32 = ctypes.windll.LoadLibrary('kernel32.dll')
            GetStdHandle = self.kernel32.GetStdHandle
            SetConsoleTextAttribute = self.kernel32.SetConsoleTextAttribute
            GetStdHandle.argtypes = [ ctypes.c_uint32 ]
            GetStdHandle.restype = ctypes.c_size_t
            SetConsoleTextAttribute.argtypes = [ ctypes.c_size_t, ctypes.c_uint16 ]
            SetConsoleTextAttribute.restype = ctypes.c_long
            self._console_handle = GetStdHandle(0xfffffff5)
            self.SetConsoleTextAttribute = SetConsoleTextAttribute
        if color < 0: color = 7
        result = 0
        if (color & 1): result |= 4
        if (color & 2): result |= 2
        if (color & 4): result |= 1
        if (color & 8): result |= 8
        if (color & 16): result |= 64
        if (color & 32): result |= 32
        if (color & 64): result |= 16
        if (color & 128): result |= 128
        self.SetConsoleTextAttribute(self._console_handle, result)
        return 0

    def echo (self, color, text):
        self.console(color)
        print(text)
        self.console(-1)
        return 0


#----------------------------------------------------------------------
# TERMINAL COLOR CONSTANTS
#----------------------------------------------------------------------
COLOR_BLACK         = 0
COLOR_RED           = 1
COLOR_GREEN         = 2
COLOR_YELLOW        = 3
COLOR_BLUE          = 4
COLOR_MAGENTA       = 5
COLOR_CYAN          = 6
COLOR_WHITE         = 7
COLOR_BOLD          = 8
COLOR_BOLD_RED      = 9
COLOR_BOLD_GREEN    = 10
COLOR_BOLD_YELLO    = 11
COLOR_BOLD_BLUE     = 12
COLOR_BOLD_MAGENTA  = 13
COLOR_BOLD_CYAN     = 14
COLOR_BOLD_WHITE    = 15


'''
@input:
3 5
1 2 3 4 5
@output:
15
'''


#----------------------------------------------------------------------
# foundation class
#----------------------------------------------------------------------
class foundation (object):

    def __init__ (self, srcname):
        self.config = configure()
        self.win32 = self.config.win32
        if '~' in srcname:
            srcname = os.path.expanduser(srcname)
        self.srcname = os.path.abspath(srcname)
        self.exename = os.path.splitext(self.srcname)[0]
        if self.win32:
            self.exename += '.exe'
        self.srctype = self.config.check_source_type(srcname)
        if self.srctype not in ('c', 'cpp', 'python'):
            raise ValueError('Unsupported source type: %s' % self.srctype)
        self.comments = self.config.extract_comments(srcname)
        self._check_requirement()

    def _check_requirement (self):
        if self.srctype in ('c', 'cpp'):
            if 'cc' not in self.config._binary:
                raise ValueError('C/C++ compiler not found')
        elif self.srctype == 'python':
            if 'python' not in self.config._binary:
                raise ValueError('Python interpreter not found')
        return 0

    def compile (self):
        if 'cc' not in self.config._binary:
            raise ValueError('C/C++ compiler not found')
        if self.srctype not in ('c', 'cpp'):
            raise ValueError('Source type is not C/C++')
        args = [self.srcname, '-o', self.exename]
        if self.srctype == 'cpp':
            cc = self.config._binary['cc']
            if '++' not in cc:
                if 'gcc' in cc:
                    args.append('-lstdc++')
                elif 'clang' in cc:
                    args.append('-lc++')
        args.insert(0, '-D_CODECHECK=1')
        flags = []
        for name in ('flags', 'cflags', 'cxxflags', 'ldflags'):
            if name not in self.config._config['default']:
                continue
            value = self.config._config['default'].get(name, '')
            value = value.strip('\r\n\t ')
            if not value:
                continue
            if name in ('flags', 'ldflags'):
                flags.append(value)
            elif name == 'cflags' and self.srctype == 'c':
                flags.append(value)
            elif name == 'cxxflags' and self.srctype == 'cpp':
                flags.append(value)
        text = ' '.join(flags)
        text = text.strip('\r\n\t ')
        if text:
            import shlex
            args += shlex.split(text)
        else:
            args = ['-O2', '-g', '-Wall'] + args + ['-lm']
        cwd = os.path.dirname(self.srcname)
        retcode = self.config.gcc(args, cwd = cwd)
        if retcode != 0:
            raise RuntimeError('Compilation failed with code %d' % retcode)
        return True

    def ensure_executable (self):
        if self.srctype not in ('c', 'cpp'):
            return False
        if os.path.exists(self.exename):
            ftime = os.path.getmtime(self.exename)
            stime = os.path.getmtime(self.srcname)
            if ftime >= stime:
                return True
        return True


#----------------------------------------------------------------------
# testing suit
#----------------------------------------------------------------------
if __name__ == '__main__':
    def test1():
        for line, comment in extract_cpp_comments(code_sample_cpp):
            print('Line %d: %s' % (line, comment))
        return 0
    def test2():
        for line, comment in extract_python_comments(code_sample_python):
            print('Line %d: %s' % (line, comment))
        return 0
    def test3():
        for line, comment in extract_python_comments(code_sample_python2):
            print('Line %d: %s' % (line, comment))
        return 0
    def test4():
        test1()
        print('---')
        test2()
        print('---')
        test3()
        return 0
    def test5():
        cfg = configure()
        print(cfg._binary)
        print(cfg.call(['python', '-c', 'print("hello", input())'], stdin = 'world'))
        return 0
    def test6():
        f = foundation('e:/lab/workshop/scratch/cpp/noi01.c')
        print(f.exename)
        # f.config.gcc(['--version'])
        f.config.echo(2, 'Hello, World !!')
        f.config.echo(COLOR_BOLD_GREEN, 'Hello, World !!')
        f.compile()
    test6()


