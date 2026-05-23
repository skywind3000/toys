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
# configure
#----------------------------------------------------------------------
class configure (object):

    def __init__ (self, ininame = None):
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
                cc = self.which(cc, PATH)
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
        try:
            result = subprocess.run(args, cwd = cwd, env = env, 
                                    timeout = timeout)
            return result.returncode
        except Exception as e:
            print('Error executing command: %s' % str(e))
        return -1

    # execute command and capture output, returns (exit code, stdout, stderr)
    def call (self, args, cwd = None, env = None, timeout = None, stdin = None):
        try:
            result = subprocess.run(args, cwd = cwd, env = env, 
                                    timeout = timeout, 
                                    stdin = stdin, 
                                    stdout = subprocess.PIPE, 
                                    stderr = subprocess.PIPE)
            return (result.returncode, result.stdout, result.stderr)
        except Exception as e:
            print('Error executing command: %s' % str(e))
        return (-1, b'', b'')


'''
@input:
3 5
1 2 3 4 5
@output:
15
'''


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
        print(cfg.call(['python', '--version']))
        return 0

    test4()


