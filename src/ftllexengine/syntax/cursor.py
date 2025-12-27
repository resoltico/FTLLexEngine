"""Immutable cursor infrastructure for type-safe parsing.

Implements the immutable cursor pattern for zero-`None` parsing.
Python 3.13+. Zero external dependencies.

Design Philosophy:
    - Cursor is immutable (frozen dataclass)
    - No `str | None` anywhere - type safety by design
    - EOF is a state (is_eof), not a return value
    - Every advance() returns NEW cursor (prevents infinite loops)
    - Line:column computed on-demand (O(n) only for errors)

Line Ending Support:
    - LF (Unix, \\n): Fully supported
    - CRLF (Windows, \\r\\n): Supported (\\n is the line delimiter)
    - CR-only (Classic Mac, \\r): NOT supported

    Both Cursor.compute_line_col() and LineOffsetCache use \\n as the line
    delimiter. CRLF files work correctly because the \\n is still present.
    Files using CR-only line endings (pre-OSX Mac format) will produce
    incorrect line numbers.

Pattern Reference:
    - Rust nom parser combinator library
    - Haskell Parsec
    - F# FParsec
"""

from dataclasses import dataclass, field

from ftllexengine.diagnostics import ErrorTemplate

__all__ = ["Cursor", "LineOffsetCache", "ParseError", "ParseResult"]


@dataclass(frozen=True, slots=True)
class Cursor:
    """Immutable source position tracker.

    Key Design Decisions:
        1. Frozen dataclass - Immutability enforced by Python
        2. Slots - Memory efficiency (important for large files)
        3. Simple position - Just an integer offset
        4. EOF is a property - Not a return value
        5. current raises - No None handling needed!

    Example:
        >>> cursor = Cursor("hello", 0)
        >>> cursor.current  # Type: str (not str | None!)
        'h'
        >>> new_cursor = cursor.advance()
        >>> new_cursor.current
        'e'
        >>> cursor.current  # Original unchanged (immutability)
        'h'
        >>> cursor.is_eof
        False
        >>> eof_cursor = Cursor("hi", 2)
        >>> eof_cursor.is_eof
        True
        >>> eof_cursor.current  # Raises EOFError
        Traceback (most recent call last):
        ...
        EOFError: Unexpected EOF at position 2
    """

    source: str
    pos: int

    @property
    def is_eof(self) -> bool:
        """Check if at end of input.

        Returns:
            True if position >= source length

        Note: This is the preferred way to check for EOF.
              Use this in while loops: `while not cursor.is_eof:`
        """
        return self.pos >= len(self.source)

    @property
    def current(self) -> str:
        """Get current character.

        Returns:
            Current character at position

        Raises:
            EOFError: If at end of input

        Design Note:
            This is the KEY difference from old parser!

            Old parser:
                _peek() -> str | None
                # Every call site needs None check:
                if self._peek() and self._peek() in "abc":  # Verbose!

            New parser:
                cursor.current -> str
                # No None checks needed:
                if cursor.current in "abc":  # Clean!
                # EOF is handled via is_eof property

            Type safety: mypy knows current is ALWAYS str, never None.
        """
        if self.is_eof:
            diagnostic = ErrorTemplate.unexpected_eof(self.pos)
            raise EOFError(diagnostic.message)
        return self.source[self.pos]

    def peek(self, offset: int = 0) -> str | None:
        """Peek at character with offset without advancing.

        Args:
            offset: Offset from current position (0 = current, 1 = next)

        Returns:
            Character at position + offset, or None if beyond EOF

        Note:
            Returns None ONLY when peeking beyond EOF.
            Use for lookahead: `if cursor.peek(1) == '=':`

            Unlike old parser's _peek(), this is used for lookahead only.
            For normal character access, use .current property.
        """
        target_pos = self.pos + offset
        if target_pos >= len(self.source):
            return None
        return self.source[target_pos]

    def advance(self, count: int = 1) -> "Cursor":
        """Return new cursor advanced by count positions.

        Args:
            count: Number of positions to advance (default: 1)

        Returns:
            New Cursor instance at new position (original unchanged)

        Design Note:
            Immutability prevents infinite loops!

            Old parser (mutable):
                while condition:
                    # If we forget self._advance(), infinite loop!
                    pass

            New parser (immutable):
                while not cursor.is_eof:
                    cursor = cursor.advance()  # Must reassign!
                    # If we forget reassignment, loop exits (cursor unchanged)

            The compiler enforces progress!

        Example:
            >>> cursor = Cursor("hello", 0)
            >>> cursor2 = cursor.advance()
            >>> cursor.pos  # Original unchanged
            0
            >>> cursor2.pos  # New cursor advanced
            1
        """
        new_pos = min(self.pos + count, len(self.source))
        return Cursor(self.source, new_pos)

    def slice_to(self, end_pos: int) -> str:
        """Extract source slice from current position to end_pos.

        Args:
            end_pos: End position (exclusive)

        Returns:
            Source substring from current position to end_pos

        Usage:
            Useful for extracting matched text after parsing:

            >>> cursor = Cursor("hello world", 0)
            >>> # Parse "hello"
            >>> start = cursor.pos
            >>> while not cursor.is_eof and cursor.current != ' ':
            ...     cursor = cursor.advance()
            >>> text = cursor.slice_to(cursor.pos)
            >>> # Wait, that won't work because we need original cursor!

            Better pattern:
            >>> cursor = Cursor("hello world", 0)
            >>> start_pos = cursor.pos
            >>> while not cursor.is_eof and cursor.current != ' ':
            ...     cursor = cursor.advance()
            >>> text = Cursor("hello world", start_pos).slice_to(cursor.pos)

            Or store start cursor:
            >>> cursor = Cursor("hello world", 0)
            >>> start_cursor = cursor
            >>> while not cursor.is_eof and cursor.current != ' ':
            ...     cursor = cursor.advance()
            >>> text = start_cursor.slice_to(cursor.pos)
        """
        return self.source[self.pos : end_pos]

    def skip_spaces(self) -> "Cursor":
        """Skip space characters (U+0020 only).

        Returns:
            New cursor advanced past all consecutive space characters

        Note:
            Only skips ASCII space (U+0020), not tabs or newlines.
            This matches Fluent parser specification for inline whitespace.

        Example:
            >>> cursor = Cursor("   hello", 0)
            >>> new_cursor = cursor.skip_spaces()
            >>> new_cursor.pos
            3
            >>> new_cursor.current
            'h'

            >>> cursor = Cursor("hello", 0)
            >>> new_cursor = cursor.skip_spaces()
            >>> new_cursor.pos  # No spaces to skip
            0
        """
        c = self
        while not c.is_eof and c.current == " ":
            c = c.advance()
        return c

    def skip_whitespace(self) -> "Cursor":
        """Skip whitespace characters (space, newline, carriage return).

        Returns:
            New cursor advanced past all consecutive whitespace characters

        Note:
            Skips space (U+0020), newline (U+000A), and carriage return (U+000D).
            This matches Fluent parser specification for general whitespace.

        Example:
            >>> cursor = Cursor("  \\n\\r  hello", 0)
            >>> new_cursor = cursor.skip_whitespace()
            >>> new_cursor.pos
            6
            >>> new_cursor.current
            'h'

            >>> cursor = Cursor("hello", 0)
            >>> new_cursor = cursor.skip_whitespace()
            >>> new_cursor.pos  # No whitespace to skip
            0
        """
        c = self
        while not c.is_eof and c.current in (" ", "\n", "\r"):
            c = c.advance()
        return c

    def expect(self, char: str) -> "Cursor | None":
        """Consume character if it matches expected, return None otherwise.

        Args:
            char: Expected character (single character string)

        Returns:
            New cursor advanced by 1 if current character matches,
            None if no match or at EOF

        Note:
            This is useful for optional character consumption.
            For required characters, use current property with explicit check.

        Example:
            >>> cursor = Cursor("hello", 0)
            >>> new_cursor = cursor.expect('h')
            >>> new_cursor.pos if new_cursor else None
            1

            >>> cursor = Cursor("hello", 0)
            >>> cursor.expect('x')  # No match
            None

            >>> eof_cursor = Cursor("hi", 2)
            >>> eof_cursor.expect('h')  # At EOF
            None
        """
        if not self.is_eof and self.current == char:
            return self.advance()
        return None

    def slice_ahead(self, n: int) -> str:
        """Get next n characters without advancing cursor.

        Args:
            n: Number of characters to get

        Returns:
            String of up to n characters starting at current position.
            May return fewer characters if near EOF.

        Note:
            Use for efficient lookahead or batch character extraction.
            Does not advance the cursor position.

        Example:
            >>> cursor = Cursor("hello", 0)
            >>> cursor.slice_ahead(3)
            'hel'
            >>> cursor.pos  # Unchanged
            0
            >>> cursor.slice_ahead(10)  # More than available
            'hello'
        """
        return self.source[self.pos : self.pos + n]

    def skip_line_end(self) -> "Cursor":
        """Skip LF, CR, or CRLF line ending.

        Returns:
            New cursor advanced past the line ending, or unchanged if not at line end.

        Handles:
            - LF (Unix, \\n): Skip 1 character
            - CRLF (Windows, \\r\\n): Skip 2 characters
            - CR (Mac, \\r): Skip 1 character

        Example:
            >>> cursor = Cursor("hello\\nworld", 5)  # At \\n
            >>> new_cursor = cursor.skip_line_end()
            >>> new_cursor.pos
            6
            >>> cursor = Cursor("hello\\r\\nworld", 5)  # At \\r in \\r\\n
            >>> new_cursor = cursor.skip_line_end()
            >>> new_cursor.pos
            7
        """
        if self.is_eof:
            return self
        if self.current == "\r":
            cursor = self.advance()
            # Handle CRLF
            if not cursor.is_eof and cursor.current == "\n":
                return cursor.advance()
            return cursor
        if self.current == "\n":
            return self.advance()
        return self

    def skip_to_line_end(self) -> "Cursor":
        """Advance to the next line ending character.

        Returns:
            New cursor positioned at \\n or \\r (does not consume line ending).

        Note:
            Stops AT the line ending, does not skip past it.
            Use skip_line_end() after this to consume the line ending.

        Example:
            >>> cursor = Cursor("hello\\nworld", 0)
            >>> new_cursor = cursor.skip_to_line_end()
            >>> new_cursor.pos
            5
            >>> new_cursor.current
            '\\n'
        """
        cursor = self
        while not cursor.is_eof and cursor.current not in ("\n", "\r"):
            cursor = cursor.advance()
        return cursor

    def count_newlines_before(self) -> int:
        """Count newlines before current position without substring copy.

        Returns:
            Number of newline characters before current position.

        Performance:
            O(n) time, O(1) memory (no substring allocation).
            More efficient than source[:pos].count() for large files.

        Example:
            >>> cursor = Cursor("a\\nb\\nc", 4)  # At 'c'
            >>> cursor.count_newlines_before()
            2
        """
        return self.source.count("\n", 0, self.pos)

    def compute_line_col(self) -> tuple[int, int]:
        """Compute line and column for current position.

        Returns:
            (line, column) tuple (1-indexed, like text editors)

        Performance:
            O(n) where n = current position
            Only call for error reporting, not during normal parsing!

        Example:
            >>> source = "line1\\nline2\\nline3"
            >>> cursor = Cursor(source, 0)
            >>> cursor.compute_line_col()
            (1, 1)
            >>> cursor = Cursor(source, 6)  # Start of line2
            >>> cursor.compute_line_col()
            (2, 1)
            >>> cursor = Cursor(source, 8)  # Middle of line2
            >>> cursor.compute_line_col()
            (2, 3)
        """
        # Count newlines before current position (O(1) memory)
        lines_before = self.count_newlines_before()
        line = lines_before + 1

        # Find last newline before current position
        last_newline = self.source.rfind("\n", 0, self.pos)
        # Use ternary for simple conditional assignment (Pythonic style)
        col = self.pos - last_newline if last_newline >= 0 else self.pos + 1

        return (line, col)


class LineOffsetCache:
    """Cached line offset computation for efficient position lookups.

    Precomputes line start offsets in O(n) single pass, then provides
    O(log n) lookups using binary search. Use this when you need to
    compute line:column for multiple positions in the same source.

    This is more efficient than calling Cursor.compute_line_col() for
    each position, which is O(n) per call.

    Example:
        >>> source = "line1\\nline2\\nline3"
        >>> cache = LineOffsetCache(source)
        >>> cache.get_line_col(0)   # Start of line 1
        (1, 1)
        >>> cache.get_line_col(6)   # Start of line 2
        (2, 1)
        >>> cache.get_line_col(8)   # Third char of line 2
        (2, 3)

    Thread Safety:
        Thread-safe. Internal state is only set during __init__.
    """

    __slots__ = ("_offsets", "_source_len")

    def __init__(self, source: str) -> None:
        """Build line offset cache from source.

        Args:
            source: Source text to index

        Complexity:
            O(n) where n = len(source)
        """
        # Line offsets: position where each line starts
        # Line 1 starts at offset 0
        offsets = [0]
        for i, char in enumerate(source):
            if char == "\n":
                # Next line starts after this newline
                offsets.append(i + 1)
        self._offsets: tuple[int, ...] = tuple(offsets)
        self._source_len = len(source)

    def get_line_col(self, pos: int) -> tuple[int, int]:
        """Get line and column for position using binary search.

        Args:
            pos: Character position in source (0-indexed)

        Returns:
            (line, column) tuple (1-indexed, like text editors)

        Complexity:
            O(log n) where n = number of lines

        Example:
            >>> cache = LineOffsetCache("abc\\ndef\\nghi")
            >>> cache.get_line_col(0)
            (1, 1)
            >>> cache.get_line_col(4)  # 'd' in "def"
            (2, 1)
        """
        # Clamp position to valid range
        if pos < 0:
            pos = 0
        elif pos > self._source_len:
            pos = self._source_len

        # Binary search: find the line containing this position
        # Line number = index of largest offset <= pos
        left, right = 0, len(self._offsets) - 1
        while left < right:
            mid = (left + right + 1) // 2
            if self._offsets[mid] <= pos:
                left = mid
            else:
                right = mid - 1

        # left is now the line index (0-based)
        line = left + 1  # Convert to 1-based
        col = pos - self._offsets[left] + 1  # 1-based column

        return (line, col)


@dataclass(frozen=True, slots=True)
class ParseResult[T]:
    """Parser result containing parsed value and new cursor position.

    Type Parameters:
        T: The type of the parsed value

    Design:
        - Generic over result type T
        - Frozen for immutability
        - Contains BOTH parsed value AND new cursor
        - Parsers return Result[ParseResult[T], ParseError]

    Pattern:
        Every parser has signature:
            def parse_foo(cursor: Cursor) -> Result[ParseResult[Foo], ParseError]:
                ...
                return Success(ParseResult(parsed_value, new_cursor))

    Example:
        >>> cursor = Cursor("hello", 0)
        >>> # Parse single character
        >>> result = ParseResult('h', cursor.advance())
        >>> result.value
        'h'
        >>> result.cursor.pos
        1
        >>> result.cursor.current
        'e'
    """

    value: T
    cursor: Cursor


@dataclass(frozen=True, slots=True)
class ParseError:
    """Parse error with location and context.

    Design:
        - Stores cursor at error point (for line:column)
        - User-friendly message
        - Expected tokens tuple (immutable for better errors)
        - Immutable for error chaining

    Example:
        >>> cursor = Cursor("hello", 2)
        >>> error = ParseError("Expected '}'", cursor, expected=('}', ']'))
        >>> error.format_error()
        "1:3: Expected '}' (expected: '}', ']')"
    """

    message: str
    cursor: Cursor
    expected: tuple[str, ...] = field(default_factory=tuple)

    def format_error(self) -> str:
        """Format error with line:column.

        Returns:
            Formatted error string with location

        Example:
            >>> cursor = Cursor("hello\\nworld", 7)
            >>> error = ParseError("Expected ']'", cursor)
            >>> error.format_error()
            "2:2: Expected ']'"

            >>> error2 = ParseError("Unexpected", cursor, expected=[']', '}'])
            >>> error2.format_error()
            "2:2: Unexpected (expected: ']', '}')"
        """
        line, col = self.cursor.compute_line_col()
        error_msg = f"{line}:{col}: {self.message}"

        if self.expected:
            expected_str = ", ".join(f"'{e}'" for e in self.expected)
            error_msg += f" (expected: {expected_str})"

        return error_msg

    def format_with_context(self, context_lines: int = 2) -> str:
        """Format error with source context and pointer.

        Shows the problematic line and a caret pointing to the error location.

        Args:
            context_lines: Number of lines to show before/after error

        Returns:
            Multi-line formatted error with context

        Example:
            >>> source = "hello = Hi\\nworld = { $name\\nfoo = Bar"
            >>> cursor = Cursor(source, 26)  # After $name
            >>> error = ParseError("Expected '}'", cursor)
            >>> print(error.format_with_context())
            2:15: Expected '}'
            <BLANKLINE>
               1 | hello = Hi
               2 | world = { $name
                 |                ^
               3 | foo = Bar
        """
        line, col = self.cursor.compute_line_col()
        lines = self.cursor.source.split("\n")

        result_lines = [self.format_error(), ""]

        # Calculate line range to show
        start_line = max(1, line - context_lines)
        end_line = min(len(lines), line + context_lines)

        # Show context lines with line numbers
        for i in range(start_line, end_line + 1):
            line_num_str = f"{i:4} | "
            result_lines.append(line_num_str + lines[i - 1])

            # Add pointer on error line
            if i == line:
                pointer = " " * (len(line_num_str) + col - 1) + "^"
                result_lines.append(pointer)

        return "\n".join(result_lines)
