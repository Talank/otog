#usage: python summarize_for_greedy.py
# This script summarizes the data for the greedy algorithm.
import json
import os
import hashlib

# json_file_reduced_basepath = "/scratch/tbaral/runtime_prediction_wo_ml/1_hr_runs/1_hr_worth_data_reduced_last_two_orders"
module_ids_we_are_considering = [1, 12, 14, 25, 27, 28, 29, 30, 31, 37]

def get_class_name(test_name):
    """Extract the class name from a test name."""
    return test_name.split("#")[0]

def get_md5_ordering(ordering):
    """Return the MD5 hash of the class ordering."""
    return hashlib.md5(" ".join(ordering).encode()).hexdigest()

def get_class_ordering(test_ordering):
    """Return the class ordering from the test ordering."""
    class_ordering = []
    for test in test_ordering:
        class_name = get_class_name(test)
        if class_name not in class_ordering:
            class_ordering.append(class_name)
    return class_ordering



# json_files = os.listdir(json_file_reduced_basepath)
os.makedirs("summarized_data", exist_ok=True)

for id in module_ids_we_are_considering:
    json_file = f"../results_backup_vn25/{id}/dataset/summary_result/{id}.json"
    best_order_id = ""
    least_average_runtime = float('inf')

# for json_file in json_files:
    class_hash_set = set()
    output_json = {}
    with open(json_file, "r") as f:
        json_data = json.load(f)
        for key in json_data:
            test_ordering = json_data[key]["test_order"]
            test_order_runtimes = json_data[key]["module_times"]
            order_id = json_data[key]["order_id"]
            test_order_runtime = sum(test_order_runtimes) / len(test_order_runtimes)
            class_ordering = get_class_ordering(test_ordering)
            class_hash = get_md5_ordering(class_ordering)

            if test_order_runtime < least_average_runtime:
                best_order_id = order_id
                least_average_runtime = test_order_runtime
            
            if class_hash not in class_hash_set:
                output_json[class_hash] = {
                    "class_order": class_ordering,
                    "module_times": [test_order_runtime],
                    "count": 1
                }
                class_hash_set.add(class_hash)
            
            else:
                output_json[class_hash]["module_times"].append(test_order_runtime)
                output_json[class_hash]["count"] += 1
    
    with open(f"summarized_data/{id}.json", "w") as f:
        json.dump(output_json, f, indent=4)
        


    # I can work here to get the naive apporach. getting the best order, and put that in optimal_order_reduced_dataset/id.txt inside the greedy dir
