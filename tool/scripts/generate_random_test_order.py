import os
import random
import hashlib
import sys

def get_method_name_from_fully_qualified_name(fully_qualified_name):
    """
    Extracts the test method name from a fully qualified name.
    E.g., 'com.example.MyTest#testMethod' -> 'testMethod'
    """
    return fully_qualified_name.split('#')[-1]

def get_class_name_from_fully_qualified_name(fully_qualified_name):
    # the class name is everything before the # in the fully qualified name
    return fully_qualified_name.split('#')[0]

def get_classes_methods(order):
    '''
    Returns `classes` and `tests_in_classes` from the order of tests.
    '''
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


def save_n_test_orders_no_interleaving(classes, tests_in_classes, n, output_dir):
    """
    Generates n unique random test orders (classes shuffled, and each class's
    own methods shuffled, but one class's methods always stay contiguous --
    "no interleaving") and writes each to <output_dir>/<order_id>.txt, one
    pkg.Class#method per line, order_id starting at 1.
    """
    os.makedirs(output_dir, exist_ok=True)

    unique_hashes = set()
    order_count = 0

    while order_count < n:
        shuffled_classes = list(classes)
        random.shuffle(shuffled_classes)

        current_order = []
        for class_name in shuffled_classes:
            methods = tests_in_classes[class_name][:]
            random.shuffle(methods)
            current_order.extend(f"{class_name}#{method}" for method in methods)

        order_hash = hashlib.md5(' '.join(current_order).encode()).hexdigest()
        if order_hash in unique_hashes:
            continue  # duplicate order, regenerate

        unique_hashes.add(order_hash)
        order_count += 1

        order_file_path = os.path.join(output_dir, f"{order_count}.txt")
        with open(order_file_path, 'w') as order_file:
            order_file.write('\n'.join(current_order) + '\n')

    return order_count


def main():
    if len(sys.argv) != 4:
        print(f"usage: {sys.argv[0]} <number_of_orders> <test_list_file> <output_dir>")
        print(f"  e.g. {sys.argv[0]} 100 runs/1685/0/test_list.txt orders/1685/0")
        sys.exit(2)

    number_of_orders = int(sys.argv[1])
    test_list_file = sys.argv[2]
    output_dir = sys.argv[3]

    if not os.path.exists(test_list_file):
        print(f"Test list not found: {test_list_file}")
        sys.exit(1)

    with open(test_list_file, 'r') as f:
        order = [line.strip() for line in f if line.strip()]

    classes, tests_in_classes = get_classes_methods(order)
    count = save_n_test_orders_no_interleaving(classes, tests_in_classes, number_of_orders, output_dir)
    print(f"Generated {count} unique orders from {len(order)} tests -> {output_dir}")


if __name__ == "__main__":
    main()
