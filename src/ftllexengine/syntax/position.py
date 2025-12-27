"""Position utilities for Fluent source code.

Per Fluent spec, provides helper functions for converting byte offsets
to line/column positions for error reporting and IDE integration.

References:
- Fluent spec errors.md: lineOffset and columnOffset helpers
"""


def line_offset(source: str, pos: int) -> int:
    """Get 0-based line number from byte offset.

    Per Fluent spec: Helper function for error reporting.

    Args:
        source: Complete FTL source text
        pos: Byte offset in source

    Returns:
        0-based line number

    Example:
        >>> source = "line1\\nline2\\nline3"
        >>> line_offset(source, 0)   # Start of file
        0
        >>> line_offset(source, 6)   # Start of line2
        1
        >>> line_offset(source, 12)  # Start of line3
        2

    Note:
        - Lines are 0-indexed per spec
        - Counts newline characters before position
        - Handles both LF (\\n) and CRLF (\\r\\n) line endings
    """
    if pos < 0:
        msg = f"Position must be >= 0, got {pos}"
        raise ValueError(msg)
    pos = min(pos, len(source))  # Clamp to source length

    # O(1) memory: count in range instead of creating substring
    return source.count("\n", 0, pos)


def column_offset(source: str, pos: int) -> int:
    """Get 0-based column number from byte offset.

    Per Fluent spec: Helper function for error reporting.

    Args:
        source: Complete FTL source text
        pos: Byte offset in source

    Returns:
        0-based column number (characters from line start)

    Example:
        >>> source = "hello\\nworld"
        >>> column_offset(source, 0)   # 'h' in "hello"
        0
        >>> column_offset(source, 2)   # 'l' in "hello"
        2
        >>> column_offset(source, 6)   # 'w' in "world"
        0
        >>> column_offset(source, 10)  # 'd' in "world"
        4

    Note:
        - Columns are 0-indexed per spec
        - Measured from most recent newline
        - Handles both LF (\\n) and CRLF (\\r\\n) line endings
    """
    if pos < 0:
        msg = f"Position must be >= 0, got {pos}"
        raise ValueError(msg)
    pos = min(pos, len(source))  # Clamp to source length

    # Find the most recent newline before pos
    line_start = source.rfind("\n", 0, pos)

    # If no newline found, column is from start of file
    if line_start == -1:
        return pos

    # Otherwise, column is characters since last newline
    return pos - line_start - 1


def format_position(source: str, pos: int, zero_based: bool = True) -> str:
    """Format position as human-readable line:column string.

    Args:
        source: Complete FTL source text
        pos: Byte offset in source
        zero_based: If True, use 0-based indexing; if False, use 1-based

    Returns:
        Position string like "line:col" (e.g., "2:5" or "3:6")

    Example:
        >>> source = "hello\\nworld\\ntest"
        >>> format_position(source, 6, zero_based=True)
        '1:0'
        >>> format_position(source, 6, zero_based=False)
        '2:1'
    """
    line = line_offset(source, pos)
    col = column_offset(source, pos)

    if not zero_based:
        line += 1
        col += 1

    return f"{line}:{col}"


def get_line_content(source: str, line_number: int, zero_based: bool = True) -> str:
    """Extract the content of a specific line.

    Useful for showing context around errors.

    Args:
        source: Complete FTL source text
        line_number: Line number to extract
        zero_based: If True, line_number is 0-based; if False, 1-based

    Returns:
        Content of the line (without trailing newline)

    Example:
        >>> source = "hello\\nworld\\ntest"
        >>> get_line_content(source, 0, zero_based=True)
        'hello'
        >>> get_line_content(source, 2, zero_based=False)
        'world'
    """
    if not zero_based:
        line_number -= 1

    if line_number < 0:
        msg = f"Line number must be >= 0, got {line_number}"
        raise ValueError(msg)

    lines = source.splitlines(keepends=False)

    if line_number >= len(lines):
        msg = f"Line {line_number} out of range (source has {len(lines)} lines)"
        raise ValueError(msg)

    return lines[line_number]


def get_error_context(source: str, pos: int, context_lines: int = 2, marker: str = "^") -> str:
    """Get formatted error context showing position in source.

    Creates a multi-line string showing the error location with
    surrounding context lines and a marker pointing to the error.

    Args:
        source: Complete FTL source text
        pos: Byte offset of error
        context_lines: Number of lines to show before/after error
        marker: Character to use for error marker

    Returns:
        Formatted error context string

    Example:
        >>> source = "line1\\nline2\\nerror here\\nline4\\nline5"
        >>> print(get_error_context(source, 12, context_lines=1))
        line2
        error here
        ^
        line4
    """
    line_num = line_offset(source, pos)
    col_num = column_offset(source, pos)

    lines = source.splitlines(keepends=False)

    # Calculate range of lines to show
    start_line = max(0, line_num - context_lines)
    end_line = min(len(lines), line_num + context_lines + 1)

    # Build context lines
    context = []
    for i in range(start_line, end_line):
        context.append(lines[i])
        # Add marker line after the error line
        if i == line_num:
            context.append(" " * col_num + marker)

    return "\n".join(context)
