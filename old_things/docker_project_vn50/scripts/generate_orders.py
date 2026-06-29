import os
import random
import hashlib
import sys
import json

def get_method_name_from_fully_qualified_name(fully_qualified_names):
    """
    Extracts the test names from fully qualified names.
    E.g., 'com.example.MyTest#testMethod' -> 'testMethod'
    """
    class_test_split = fully_qualified_names.split('#')
    test_name = class_test_split[-1]
    return test_name

def get_class_name_from_fully_qualified_name(fully_qualified_name):
    return fully_qualified_name.split('#')[0]

def get_classes_methods(order):
    """
    Returns `classes` and `tests_in_classes` from the order of tests.
    """
    classes = set()
    classes_order = []
    for test in order:
        class_name = get_class_name_from_fully_qualified_name(test)
        if class_name not in classes:
            classes_order.append(class_name)
        classes.add(class_name)
    
    tests_in_classes = {class_name: [] for class_name in classes_order}
    for test in order:
        class_name = get_class_name_from_fully_qualified_name(test)
        test_name = get_method_name_from_fully_qualified_name(test)
        if test_name not in tests_in_classes[class_name]:
            tests_in_classes[class_name].append(test_name)
            
    return classes_order, tests_in_classes


def save_n_test_orders_no_interleaving(classes, tests_in_classes, n, output_base_dir, module_id):
    existing_hashes = set()
    order_count = 0
    orders = {}

    while order_count < n:
        shuffled_classes = list(classes)
        random.shuffle(shuffled_classes)
        current_order_fully_qualified_test_names = []

        for class_name in shuffled_classes:
            methods = tests_in_classes[class_name][:]
            random.shuffle(methods)
            fully_qualified_tests = [f"{class_name}#{method}" for method in methods]
            current_order_fully_qualified_test_names.extend(fully_qualified_tests)

        order_hash = hashlib.md5(' '.join(current_order_fully_qualified_test_names).encode()).hexdigest()

        if order_hash in existing_hashes:
            continue

        existing_hashes.add(order_hash)
        order_count += 1
        orders[order_count] = current_order_fully_qualified_test_names

    save_dir = f"{output_base_dir}/{module_id}"
    os.makedirs(save_dir, exist_ok=True)
    
    for order_id, order in orders.items():
        order_file_path = os.path.join(save_dir, f"{order_id}.txt")
        with open(order_file_path, 'w') as order_file:
            for test_name in order:
                order_file.write(test_name)

def main():
    test_list = sys.argv[1]
    output_base_dir = sys.argv[2]
    current_module_id = sys.argv[3]
    number_of_orders = int(sys.argv[4])

    with open(test_list, 'r') as f:
        order = f.readlines()
        current_module_classes, current_module_tests_in_classes = get_classes_methods(order)
        save_n_test_orders_no_interleaving(current_module_classes, current_module_tests_in_classes, number_of_orders, output_base_dir, current_module_id)


if __name__ == "__main__":
    main()
