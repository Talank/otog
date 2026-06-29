import xml.etree.ElementTree as ET
import os
import re
import sys
import hashlib
import json

def get_test_suite_runtime(xml_file):
    tree = ET.parse(xml_file)
    root = tree.getroot()
    testsuite_time = float(root.get('time').replace(',',''))
    return testsuite_time

def get_module_time(surefire_reports_dir):
    overall_testsuite_time = 0.0
    for file in os.listdir(surefire_reports_dir):
        if file.endswith('.xml'):
            xml_file = os.path.join(surefire_reports_dir, file)
            overall_testsuite_time += get_test_suite_runtime(xml_file)         
    return round(overall_testsuite_time, 3)

def remove_brackets_and_parentheses(s):
    s = re.sub(r'\[.*?\]', '', s)
    s = re.sub(r'(?<!runApplication)\(.*?\)', '', s)
    return s

def get_test_order_from_file(order_file):
    with open(order_file, 'r') as file:
        order = file.read().strip().splitlines()
    return order

module_id = sys.argv[1]
order_id = sys.argv[2]
script_dir = sys.argv[3]

runs_base_dir = f"{script_dir}/../runs_n25/random_runs/{module_id}/{order_id}"
order_file = f"{script_dir}/../random_test_orders_n25/{module_id}/{order_id}.txt"

test_order_lst = get_test_order_from_file(order_file)
test_order_hash = hashlib.md5(' '.join(test_order_lst).encode()).hexdigest()

# there are 3 runs for each module, get the runtime of each run
runtimes = []
for i in range(1, 4):
    surefire_reports_dir = os.path.join(runs_base_dir, f"{i}")
    runtime = get_module_time(surefire_reports_dir)
    runtimes.append(runtime)

# mkdirs if not exist
os.makedirs(f"{script_dir}/../dataset/summary_result", exist_ok=True)

json_summary_result_basepath = f"{script_dir}/../dataset/summary_result/{module_id}.json"

# if the file doesn't exist, create it. Otherwise, update it.
if not os.path.exists(json_summary_result_basepath):
    data = {}
    data[test_order_hash]={}
    data[test_order_hash]["order_id"] = order_id
    data[test_order_hash]["module_times"] = runtimes
    data[test_order_hash]["test_order"] = test_order_lst
        
    with open(json_summary_result_basepath, 'w') as f:
        json.dump(data, f)

else:
    with open(json_summary_result_basepath, 'r') as f:
        data = json.load(f)
        if test_order_hash not in data:
            data[test_order_hash]={}
            data[test_order_hash]["order_id"] = order_id
            data[test_order_hash]["module_times"] = runtimes
            data[test_order_hash]["test_order"] = test_order_lst
        else:
            data[test_order_hash]["module_times"].append(runtimes)
        
    with open(json_summary_result_basepath, 'w') as f:
        json.dump(data, f)

# return runtimes
print(runtimes)

# python get_runtime.py $module_id $order_file_name $script_dir