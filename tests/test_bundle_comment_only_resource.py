"""Test for Comment-only FTL resources to achieve 100% branch coverage.

This test specifically targets the Comment case branch (941->909) that
continues the loop iteration in _register_resource.
"""


from ftllexengine.runtime import FluentBundle


class TestCommentOnlyResource:
    """Test resources containing only Comment entries."""

    def test_resource_with_only_comments_no_messages(self) -> None:
        """Resource with only comments processes without errors.

        This test ensures the Comment case in _register_resource properly
        continues the loop when there are no other entry types, which helps
        achieve the branch coverage for line 941->909.
        """
        bundle = FluentBundle("en_US")

        # FTL resource with ONLY comment entries (no messages/terms/junk)
        ftl_source = """### Main Section Header
## Subsection comment
# Regular comment line
# Another comment
### Another section
# Final comment"""

        junk = bundle.add_resource(ftl_source)

        # Should process successfully with no junk
        assert len(junk) == 0
        # Should have no messages (comments don't create messages)
        assert len(bundle.get_message_ids()) == 0

    def test_message_followed_by_single_comment(self) -> None:
        """Message entry followed by Comment entry (Comment is last).

        Ensures Comment case as final loop iteration is covered.
        """
        bundle = FluentBundle("en_US")

        ftl_source = """msg = Hello
# Trailing comment"""

        junk = bundle.add_resource(ftl_source)

        assert len(junk) == 0
        assert bundle.has_message("msg")

    def test_interleaved_comments_and_messages(self) -> None:
        """Comments interleaved with messages process correctly.

        Ensures the Comment case properly continues iteration in a mixed
        entry sequence.
        """
        bundle = FluentBundle("en_US")

        ftl_source = """
### Header
msg1 = First
# Comment between messages
msg2 = Second
## Another comment
msg3 = Third
# Trailing comment
"""

        junk = bundle.add_resource(ftl_source)

        assert len(junk) == 0
        assert len(bundle.get_message_ids()) == 3
        assert bundle.has_message("msg1")
        assert bundle.has_message("msg2")
        assert bundle.has_message("msg3")

    def test_comments_before_and_after_all_entry_types(self) -> None:
        """Comments before and after Message, Term, and Junk entries.

        Comprehensive test ensuring Comment case handles all loop positions.
        """
        bundle = FluentBundle("en_US")

        ftl_source = """
### Top comment

# Comment before message
msg = Hello

# Comment before term
-term = Brand

# This will create Junk (invalid syntax)
invalid syntax here

# Comment after junk
final-msg = Goodbye
"""

        junk = bundle.add_resource(ftl_source)

        # Should have junk from invalid syntax
        assert len(junk) > 0
        # Should have messages
        assert bundle.has_message("msg")
        assert bundle.has_message("final-msg")
