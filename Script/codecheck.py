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
code_sample_python r'''
# My first Python program
def main():
    x = 10
    y = x + 3
    print("Hello, World !!")
    # test1
    # test2
    return 0
"""
docstring test1
docstring test2
"""
'''

#----------------------------------------------------------------------
# testing suit
#----------------------------------------------------------------------
if __name__ == '__main__':
    def test1():
        for line, comment in extract_cpp_comments(code_sample_cpp):
            print('Line %d: %s' % (line, comment))
        return 0
    test1()


