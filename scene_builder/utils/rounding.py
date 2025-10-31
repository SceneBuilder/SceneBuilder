import math

def round_to_sigfigs(num, sig_figs):
    """Rounds a number to a specified number of significant figures."""
    if num == 0:
        return 0
    
    # Calculate the power of 10
    power = sig_figs - int(math.floor(math.log10(abs(num)))) - 1
    
    # Round the number
    return round(num, power)


def safe_round(num, ndigits):
    """Prevents truncation of small numbers by using sigfigs if < 1."""
    if abs(num) >= 1:
        return round(num, ndigits)
    else:
        return round_to_sigfigs(num, ndigits)


def safe_round_list(iterable, ndigits):
    """Applies safe_round to each numeric element in an iterable."""
    return [safe_round(num, ndigits) for num in iterable]


def safe_round_dict(d, ndigits):
    """Applies safe_round to each numeric value in a dictionary."""
    return {key: safe_round(value, ndigits) if isinstance(value, (int, float)) else value
            for key, value in d.items()}


if __name__ == "__main__":
    print("Testing rounding behavior for large numbers:")
    print("Input: 12345.0")
    print(f"  round(12345.0, 3): {round(12345.0, 3)}")
    print(f"  safe_round(12345.0, 3): {safe_round(12345.0, 3)}")
    print()

    print("Testing rounding behavior for small decimals:")
    print("Input: 0.12345")
    print(f"  round(0.12345, 3): {round(0.12345, 3)}")
    print(f"  safe_round(0.12345, 3): {safe_round(0.12345, 3)}")
    print()

    print("Testing rounding behavior for very small numbers:")
    print("Input: 0.00045678")
    print(f"  round(0.00045678, 3): {round(0.00045678, 3)}")
    print(f"  safe_round(0.00045678, 3): {safe_round(0.00045678, 3)}")
    print()

    print("Testing safe_round_dict:")
    test_dict = {"x": 12345.0, "y": 0.00045678, "z": "text", "count": 42}
    print(f"Input: {test_dict}")
    print(f"safe_round_dict(test_dict, 3): {safe_round_dict(test_dict, 3)}")
