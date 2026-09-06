#!/usr/bin/env python3
# OUTDATED: We have replaced the logic to get the test list using the java refection instead.
"""Extract the executed test list (pkg.Class#method, in execution order) from a
surefire-reports directory. Port of user_defined_scripts_for_reference/get_test_list.py
(same cleaning/dedupe rules) with explicit args instead of cwd assumptions.

Usage: get_test_list.py <surefire_reports_dir> <out_file>
"""
import os, sys, re
import xml.etree.ElementTree as ET


def remove_brackets_and_parentheses(s):
    s = re.sub(r'\[.*?\]', '', s)
    s = re.sub(r'\(.*?\)', '', s)
    return s


def get_test_methods(xml_file):
    root = ET.parse(xml_file).getroot()
    test_methods = []
    for testcase in root.findall('testcase'):
        class_name = testcase.attrib['classname']
        method_name = remove_brackets_and_parentheses(testcase.attrib['name'])
        test_method = f"{class_name}#{method_name}"
        if test_method not in test_methods:
            test_methods.append(test_method)
    return test_methods


def main():
    surefire_dir, out_file = sys.argv[1], sys.argv[2]
    test_methods = []
    for filename in sorted(os.listdir(surefire_dir)):
        if filename.endswith('.xml'):
            test_methods.extend(get_test_methods(os.path.join(surefire_dir, filename)))
    with open(out_file, 'w') as f:
        f.writelines(item + '\n' for item in test_methods)
    print(f"{len(test_methods)} tests -> {out_file}")


if __name__ == '__main__':
    main()
