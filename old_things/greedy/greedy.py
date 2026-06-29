import sys
import json
import numpy as np
import time
import os

def get_class_name(test_name):
    """Extract the class name from a test name."""
    return test_name.split("#")[0]

def create_score_matrix(num_classes):
    """
    Initialize the score matrix for the given number of classes.
    """
    return np.zeros((num_classes, num_classes))

def update_scores(score_matrix, class_order, module_times, avg_runtime):
    """
    Update the score matrix based on the runtimes for consecutive classes.
    Increase the score if the runtime is lower than average, decrease otherwise.
    """
    avg_module_time = sum(module_times) / len(module_times)
    if avg_module_time < avg_runtime:
        update_value = 1
    else:
        update_value = -1
    
    for idx in range(len(class_order) - 1):
        class1_idx = class_order[idx]
        class2_idx = class_order[idx + 1]
        score_matrix[class1_idx][class2_idx] += update_value

def calculate_average_runtime(summarized_dataset):
    """
    Calculate the average runtime across all module times in the summarized dataset.
    """
    all_module_times = [time for data in summarized_dataset.values() for time in data["module_times"]]
    return sum(all_module_times) / len(all_module_times)

def find_initial_best_pair(score_matrix):
    """
    Find the pair with the highest score from the score matrix.
    """
    num_classes = len(score_matrix)
    best_pair = None
    best_score = float('-inf')

    for i in range(num_classes):
        for j in range(num_classes):
            if score_matrix[i][j] > best_score:
                best_score = score_matrix[i][j]
                best_pair = (i, j)

    return best_pair

def find_next_best_test(score_matrix, current_order):
    """
    Find the next best test to append to the current order by maximizing the score.
    The first test of the pair must match the last test in the current order.
    """
    last_test = current_order[-1]
    num_classes = score_matrix.shape[0]
    best_next_test = None
    best_score = float('-inf')

    for next_test in range(num_classes):
        if next_test not in current_order:  # Avoid duplicates
            if score_matrix[last_test][next_test] > best_score:
                best_score = score_matrix[last_test][next_test]
                best_next_test = next_test

    return best_next_test

def find_fastest_order(score_matrix, class_lst):
    """
    Start with the fastest pair, then iteratively select the next test that maximizes the score
    such that the first in the next pair is the last test in the current order.
    """
    num_classes = len(class_lst)
    
    # Start with the best initial pair
    best_pair = find_initial_best_pair(score_matrix)
    current_order = [best_pair[0], best_pair[1]]
    
    # Iteratively pick the next test
    while len(current_order) < num_classes:
        next_test = find_next_best_test(score_matrix, current_order)
        if next_test is not None:
            current_order.append(next_test)
        else:
            break  # No more valid tests to add

    # print(f"Optimal order: {current_order}")
    # compute the score of the optimal order
    score = 0
    for i in range(len(current_order) - 1):
        score += score_matrix[current_order[i]][current_order[i + 1]]
    # print(f"Score: {score}")
    # Convert index order back to class names
    optimal_order_names = [class_lst[idx] for idx in current_order]
    # print(optimal_order_names)

    
    return optimal_order_names

def load_fastest_order(fastest_order_file):
    """
    Load the fastest test order from the specified file.
    """
    with open(fastest_order_file, "r") as f:
        return f.read().strip().splitlines()

def create_suboptimal_fast_order(class_order, class_to_tests):
    """
    Replace class names in the class order with the tests from the fastest order.
    """
    return [test for class_name in class_order if class_name in class_to_tests for test in class_to_tests[class_name]]

def save_order(order, id):
    """
    Save the generated class order to a txt file.
    """
    output_dir = "generated_orders"
    os.makedirs(output_dir, exist_ok=True)

    with open(os.path.join(output_dir, f"{id}_greedy.txt"), "w") as f:
        f.write("\n".join(order))

def compute_suboptimal_test_order(class_order, id):
    """
    Generate and save the suboptimal fast test order based on the given class order.
    """

    fastest_order_file = f"optimal_order_reduced_dataset/{id}.txt"
    fastest_order = load_fastest_order(fastest_order_file)

    class_to_tests = {}
    for test in fastest_order:
        class_name = get_class_name(test)
        class_to_tests.setdefault(class_name, []).append(test)

    suboptimal_fast_order = create_suboptimal_fast_order(class_order, class_to_tests)
    # save_order(suboptimal_fast_order, id) #UNCOMMENT THIS LINE TO SAVE THE ORDER
    
def find_most_difference_paris(score_matrix):
    """
    Find the most significant pairs from the score matrix. Find the pairs i, j where there is the most difference in score between [i][j] and [j][i].
    """
    num_classes = len(score_matrix)
    best_pair = None
    best_score = float('-inf')

    for i in range(num_classes):
        for j in range(num_classes):
            if i != j:
                score_diff = score_matrix[i][j] - score_matrix[j][i]
                if score_diff > best_score:
                    best_score = score_diff
                    best_pair = (i, j)

    # print the score difference
    print(f"Score difference: {best_score}")

    return best_pair

def main():
    # Load dataset ID from command line
    id = sys.argv[1]
    
    # Load summarized dataset from JSON file
    with open(f"summarized_data/{id}.json", "r") as f:
        summarized_dataset = json.load(f)

    # Extract the first entry to determine class list and module times
    first_entry = next(iter(summarized_dataset.values()))
    class_lst = first_entry["class_order"]

    # Create a mapping of class names to their index (for the matrix)
    class_mapping = {class_name: idx for idx, class_name in enumerate(class_lst)}

    # Initialize the score matrix
    score_matrix = create_score_matrix(len(class_lst))

    # Calculate the average runtime
    avg_runtime = calculate_average_runtime(summarized_dataset)

    # Loop through each dataset entry to update scores
    for data in summarized_dataset.values():
        class_order_indices = [class_mapping[class_name] for class_name in data["class_order"]]
        update_scores(score_matrix, class_order_indices, data["module_times"], avg_runtime)
    
    most_diff_pairs = find_most_difference_paris(score_matrix)
    # print the name of classes with the most difference
    print(f"Most difference pair: {class_lst[most_diff_pairs[0]]}, {class_lst[most_diff_pairs[1]]}")
    
    # Get the fastest order
    optimal_order = find_fastest_order(score_matrix, class_lst)

    # Compute the suboptimal fast test order
    compute_suboptimal_test_order(optimal_order, id)

if __name__ == "__main__":
    start_time = time.time()
    main()
    print(f"id: {sys.argv[1]}, Time: {time.time() - start_time}")