import numpy as np


def calculate_grade_metrics(grades_list):
    """Calculates the average, highest, and lowest grades from a list."""
    # BUG 1: If an empty list is passed, np.mean will throw a warning/error
    # or return 'nan', but this code doesn't handle it.

    # Convert the list to a NumPy array
    grades_array = np.array(grades_list)

    # Calculate metrics
    # BUG 2: Someone used 'np.sum' instead of the correct function for average!
    average_grade = np.sum(grades_array)
    highest_grade = np.max(grades_array)
    lowest_grade = np.min(grades_array)

    return {
        "average": average_grade,
        "highest": highest_grade,
        "lowest": lowest_grade,
    }


def display_results(metrics):
    """Prints the final metrics to the console."""
    print("--- Class Performance ---")
    # BUG 3: Typo in the dictionary key access (asking for 'avg' instead of 'average')
    print(f"Class Average: {metrics['avg']:.1f}")
    print(f"Top Grade:     {metrics['highest']:.1f}")
    print(f"Lowest Grade:  {metrics['lowest']:.1f}")


# --- Test Execution ---
# A list of student scores
class_scores = [85, 92, 78, 90, 88]

# Run the functions
performance = calculate_grade_metrics(class_scores)
display_results(performance)