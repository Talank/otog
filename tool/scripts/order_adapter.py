#!/usr/bin/env python3
#
# usage: python3 scripts/order_adapter.py <order_file> <target_test_list_file> <output_order_file>
# e.g.   python3 scripts/order_adapter.py orders/1685/0/5.txt runs/1685/10/test_list.txt orders/1685/10/5.txt
#
# Adapts one v0 order to another version: drop the tests that version no longer
# has, append the ones it gained, keep every other test's relative position.
# This is how "the same order" follows a module along the version axis.

import os
import sys


def get_class_name(fq_name):
    return fq_name.split("#")[0]


def get_method_name(fq_name):
    return fq_name.split("#")[1]


def get_classes_methods(order):
    # The order's classes, in first-seen order, and each one's own methods.
    classes = []
    tests_in_classes = {}
    for test in order:
        class_name = get_class_name(test)
        method = get_method_name(test)
        if class_name not in tests_in_classes:
            classes.append(class_name)
            tests_in_classes[class_name] = []
        if method not in tests_in_classes[class_name]:
            tests_in_classes[class_name].append(method)
    return classes, tests_in_classes

def compute_added_deleted_tests(order_tests, target_tests):
    # What the target version gained, and what it no longer has.
    set_order = set(order_tests)
    set_target = set(target_tests)
    added = sorted(set_target - set_order)
    deleted = sorted(set_order - set_target)
    return added, deleted

def remove_deleted_tests(order, deleted_tests):
    return [test for test in order if test not in deleted_tests]

def add_added_tests(order, added_tests):
    # A new method joins its class's block; a wholly new class goes to the end.
    classes, tests_in_classes = get_classes_methods(order)
    for test in added_tests:
        class_name = get_class_name(test)
        method = get_method_name(test)
        if class_name not in tests_in_classes:
            classes.append(class_name)
            tests_in_classes[class_name] = []
        if method not in tests_in_classes[class_name]:
            tests_in_classes[class_name].append(method)
    new_order = []
    for cls in classes:
        for method in tests_in_classes[cls]:
            new_order.append("%s#%s" % (cls, method))
    return new_order

def adapt_order(order_file, target_test_list_file, output_order_file):
    # Read the order and the target list, adapt, write the new order.
    with open(order_file) as f:
        order_tests = f.read().splitlines()
    with open(target_test_list_file) as f:
        target_tests = f.read().splitlines()

    added_tests, deleted_tests = compute_added_deleted_tests(order_tests, target_tests)

    updated_order = remove_deleted_tests(order_tests, deleted_tests)
    updated_order = add_added_tests(updated_order, added_tests)

    os.makedirs(os.path.dirname(output_order_file), exist_ok=True)
    with open(output_order_file, "w") as f:
        f.write("\n".join(updated_order))
        if updated_order:
            f.write("\n")

    print("added tests: %d" % len(added_tests))
    print("deleted tests: %d" % len(deleted_tests))

if __name__ == "__main__":
    if len(sys.argv) != 4:
        print("usage: %s <order_file> <target_test_list_file> <output_order_file>" % sys.argv[0])
        sys.exit(2)

    order_file = sys.argv[1]
    target_test_list_file = sys.argv[2]
    output_order_file = sys.argv[3]

    adapt_order(order_file, target_test_list_file, output_order_file)
