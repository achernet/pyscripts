

def assign_binary_data(variable_name, initial_indent, maximum_width, data_string):
    """
    Assign :attr:`data_string` to :attr:`variable_name` using parentheses to wrap multiple lines as needed.

    :param str variable_name: The name of the variable being defined
    :param int initial_indent: The initial indentation, which should be a multiple of 4
    :param int maximum_width: The maximum width for each line (often between 80 and 160)
    :param str data_string: The binary data
    :return str: The text of the entire variable definition
    """
    variable_name = variable_name.strip()
    data_buffer = StringIO()
    data_buffer.write(" " * initial_indent)  # start with initial indent
    data_buffer.write(variable_name)  # declare the variable
    data_buffer.write(" = (")  # opening parenthesis

    line_indent = data_buffer.tell()
    max_string_length = maximum_width - line_indent - 2

    chars = [chr(i) for i in xrange(0, 256)]
    reprs = [repr(ch).strip("\'") for ch in chars]
    reprs[ord("\'")] = "\\\'"
    lengths = [len(r) for r in reprs]

    total = 0
    data_buffer.write("\'")  # start the first string
    for i, ch in enumerate(compressedData):
        next_total = total + lengths[ord(ch)]
        if next_total > max_string_length:
            data_buffer.write("\'\n")  # end quote for current line, plus line separator
            data_buffer.write(" " * line_indent)
            data_buffer.write("\'")
            total = 0
        data_buffer.write(reprs[ord(ch)])
        total += lengths[ord(ch)]
    data_buffer.write("\')\n")
    return data_buffer
