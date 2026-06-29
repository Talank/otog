# usage: python get_test_list.py <output_dir>

import os, sys, re
import xml.etree.ElementTree as ET

def remove_brackets_and_parentheses(s):
    # Remove text inside square brackets
    s = re.sub(r'\[.*?\]', '', s)
    # Remove text inside parentheses
    s = re.sub(r'\(.*?\)', '', s)
    return s

def get_test_methods(xml_file):
    tree = ET.parse(xml_file)
    root = tree.getroot()
    test_methods = []

    for testcase in root.findall('testcase'):
        class_name = testcase.attrib['classname']
        method_name = testcase.attrib['name']
        method_name = remove_brackets_and_parentheses(method_name)
        test_method = f"{class_name}#{method_name}"
        if test_method not in test_methods:  # Ensure uniqueness
            test_methods.append(test_method)

    return test_methods

def get_test_methods_from_surefire_reports(surefire_reports_dir):
    test_methods = []
    for filename in sorted(os.listdir(surefire_reports_dir)):
        if filename.endswith('.xml'):
            xml_file = os.path.join(surefire_reports_dir, filename)
            test_methods.extend(get_test_methods(xml_file))
    return test_methods

def write_order_to_file(order, output_path):
    # if the dir for the output file does not exist, create it
    output_dir = os.path.dirname(output_path)
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
        
    with open(output_path, 'w') as file:
        file.writelines([item + '\n' for item in order])


surefire_reports_dir = sys.argv[1]
out_file = sys.argv[2]

print(f"Reading test methods from {surefire_reports_dir}")

test_methods = get_test_methods_from_surefire_reports(surefire_reports_dir)
write_order_to_file(test_methods, out_file)
