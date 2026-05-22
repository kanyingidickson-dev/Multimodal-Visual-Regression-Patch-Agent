def divide(a, b):
    # Bug: no zero division check
    return a / b

def get_item(items, index):
    # Bug: out of bounds access possible
    return items[index]

def process_data(data):
    # Bug: type error if data is not string
    return data.split(",")

def main():
    print(divide(10, 0))
    print(get_item([1, 2], 5))
    process_data(123)

if __name__ == '__main__':
    main()
