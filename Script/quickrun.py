#! /usr/bin/env python3
# -*- coding: utf-8 -*-
#======================================================================
#
# quickrun.py - 
#
# Created by skywind on 2026/06/26
# Last Modified: 2026/06/26 14:38:46
#
#======================================================================
import sys
import os
import re
import subprocess
import pprint


#----------------------------------------------------------------------
# version
#----------------------------------------------------------------------
VERSION = '0.0.1'


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
            if lnum not in comments:
                comments[lnum] = []
            comments[lnum].append(comment)
        elif name in ('PY_STRING3D', 'PY_STRING3S'):
            text = value[3:-3].strip('\r\n\t ')
            line = lnum
            for part in text.split('\n'):
                part = part.strip('\r\n\t ')
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
# source extractors
#----------------------------------------------------------------------
EXTRACTORS = {
    '.c': extract_cpp_comments,
    '.cc': extract_cpp_comments,
    '.cxx': extract_cpp_comments,
    '.cpp': extract_cpp_comments,
    '.h': extract_cpp_comments,
    '.hpp': extract_cpp_comments,
    '.hh': extract_cpp_comments,
    '.cs': extract_cpp_comments,
    '.java': extract_cpp_comments,
    '.js': extract_cpp_comments,
    '.ts': extract_cpp_comments,
    '.as': extract_cpp_comments,
    '.go': extract_cpp_comments,
    '.py': extract_python_comments,
}


#----------------------------------------------------------------------
# default target
#----------------------------------------------------------------------
TARGET = sys.platform


#----------------------------------------------------------------------
# configure
#----------------------------------------------------------------------
class configure (object):

    def __init__ (self, srcname):
        self.srcname = os.path.abspath(srcname and srcname or __file__)
        self.dirname = os.path.dirname(self.srcname)
        self.extname = os.path.splitext(self.srcname)[1].lower()
        self.basename = os.path.basename(self.srcname)
        self.target = TARGET
        self.commands = {}
        self.environ = {}
        self.environ['FILENAME'] = self.basename
        self.environ['FILEPATH'] = self.srcname
        self.environ['FILEDIR'] = self.dirname
        self.environ['FILEEXT'] = os.path.splitext(self.basename)[1].lower()
        self.environ['FILENOEXT'] = os.path.splitext(self.basename)[0]
        self.environ['PATHNOEXT'] = os.path.splitext(self.srcname)[0]
        markers = ('.git', '.svn', '.hg', '.project', '.root')
        if 'QUICKRUN_MARKERS' in os.environ:
            text = os.environ['QUICKRUN_MARKERS'].strip()
            mm = []
            for name in text.split(','):
                name = name.strip()
                if name:
                    mm.append(name)
            markers = tuple(mm)
        self.root = self.find_root(self.dirname, markers, True)
        self.environ['ROOT'] = self.root
        self.environ['DIRNAME'] = os.path.basename(self.dirname)
        self.environ['PRONAME'] = os.path.basename(self.root)
        if 'QUICKRUN_TARGET' in os.environ:
            self.target = os.environ['QUICKRUN_TARGET'].strip()
        self.environ['TARGET'] = self.target

    def find_root (self, path, markers = None, fallback = False):
        if markers is None:
            markers = ('.git', '.svn', '.hg', '.project', '.root')
        if path is None:
            path = os.getcwd()
        path = os.path.abspath(path)
        base = path
        while True:
            parent = os.path.normpath(os.path.join(base, '..'))
            for marker in markers:
                if not marker:
                    continue
                test = os.path.join(base, marker)
                if ('*' in test) or ('?' in test) or ('[' in test):
                    import glob
                    if glob.glob(test):
                        return base
                if os.path.exists(test):
                    return base
            if os.path.normcase(parent) == os.path.normcase(base):
                break
            base = parent
        if fallback:
            return path
        return None

    # execute command without capture, returns exit code
    def execute (self, args, cwd = None, env = None, timeout = None, stdin = None):
        if env:
            envcopy = os.environ.copy()
            envcopy.update(env)
            env = envcopy
        if stdin:
            if isinstance(stdin, str):
                stdin = stdin.encode('utf-8', 'ignore')
        result = subprocess.run(args, cwd = cwd, env = env,
                                shell = True,
                                input = stdin,
                                timeout = timeout)
        return result.returncode

    def system (self, cmd, cwd = None, env = None):
        return self.execute(cmd, cwd, env)

    def print (self):
        import pprint
        pprint.pprint(self.environ)
        return 0

    # load content
    def load_file_content (self, filename, mode = 'r'):
        if hasattr(filename, 'read'):
            try: content = filename.read()
            except Exception: content = None
            return content
        try:
            if '~' in filename:
                filename = os.path.expanduser(filename)
            fp = open(filename, mode)
            content = fp.read()
            fp.close()
        except Exception:
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
            except Exception:
                pass
            visit = {}
            for name in guess + ['gbk', 'ascii', 'latin1']:
                if name in visit:
                    continue
                visit[name] = 1
                try:
                    text = content.decode(name)
                    break
                except (UnicodeDecodeError, LookupError):
                    pass
            if text is None:
                text = content.decode('utf-8', 'ignore')
        return text

    def extract_comments (self, filename):
        if not os.path.exists(filename):
            sys.stderr.write('error: file not found: %s\n' % self.srcname)
            raise FileNotFoundError(filename)
        extname = os.path.splitext(filename)[1].lower()
        if extname not in EXTRACTORS:
            sys.stderr.write('error: no extractor for file type %s\n' % self.extname)
            raise ValueError('no extractor for file type %s' % self.extname)
        extractor = EXTRACTORS[extname]
        content = self.load_file_text(filename)
        comments = extractor(content)
        return comments

    def load (self):
        comments = self.extract_comments(self.srcname)
        self.commands = {}
        for lnum, text in comments:
            text = text.strip('\r\n\t ')
            if not text:
                continue
            if not text.startswith('@'):
                continue
            text = text[1:].strip('\r\n\t ')
            if not text.startswith('command'):
                continue
            text = text[len('command'):].strip('\r\n\t ')
            if not ':' in text:
                continue
            key, _, val = text.partition(':')
            key = key.strip('\r\n\t ')
            val = val.strip('\r\n\t ')
            if not key:
                continue
            if not key.startswith('('):
                continue
            if not key.endswith(')'):
                continue
            key = key[1:-1].strip('\r\n\t ')
            name, _, condition = key.partition('/')
            name = name.strip('\r\n\t ')
            condition = condition.strip('\r\n\t ')
            print(f'name: {name}, condition: {condition}, val: {val}')
            if condition and condition != self.target:
                continue
            self.commands[name] = val
        return 0



#----------------------------------------------------------------------
# test comments
#----------------------------------------------------------------------
# @command(build): gcc -o $(FILENOEXT) (FILENAME)
# @command(run-win32/win32): echo running on windows
# @command(run-linux/linux): echo running on linux


#----------------------------------------------------------------------
# testing suit
#----------------------------------------------------------------------
if __name__ == '__main__':
    def test1():
        print('extracting comments from C/C++ code sample:')
        comments = extract_cpp_comments(code_sample_cpp)
        for lnum, text in comments:
            print('line %d: %s' % (lnum, text))
        print('\nextracting comments from Python code sample:')
        comments = extract_python_comments(code_sample_python)
        for lnum, text in comments:
            print('line %d: %s' % (lnum, text))
        return 0
    def test2():
        c = configure(None)
        c.print()
        c.load()
        pprint.pprint(c.commands)
        return 0

    test2()

