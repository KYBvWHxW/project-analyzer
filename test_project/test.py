def hello_world():
    """A simple function that prints hello world"""
    print("Hello, World!")

def add_numbers(a: int, b: int) -> int:
    """Add two numbers and return the result"""
    return a + b

if __name__ == "__main__":
    hello_world()
    result = add_numbers(5, 3)
    print(f"5 + 3 = {result}")
