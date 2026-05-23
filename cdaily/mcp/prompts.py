"""MCP prompts — reusable workflow templates agents can invoke by name."""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP


def register_prompts(mcp: FastMCP) -> None:
    @mcp.prompt()
    def morning_triage() -> str:
        """Morning briefing: digest the unread feed and propose top-3 to read."""
        return (
            "You are my feed assistant. Follow these steps in order:\n"
            "1. Call feed_digest(top_n=5, group_by='category') to see the landscape.\n"
            "2. Identify the 3 most relevant articles given my dominant categories.\n"
            "3. For each: a 1-line justification (why it stands out).\n"
            "4. Suggest which to mark read via feed_clear_apply or article_mark_apply.\n"
            "5. If any deserves an AI summary, propose article_summarize_apply.\n"
            "Be concise. Output a numbered list."
        )

    @mcp.prompt()
    def weekly_digest() -> str:
        """Weekly digest: dominant themes from this week's reads + recommendations."""
        return (
            "Build a weekly digest:\n"
            "1. Call feed_read(filter='all', limit=200, verbose=true).\n"
            "2. Filter starred and rated 4+ — those are the important ones.\n"
            "3. Identify 3 dominant themes, each with 2-3 article-evidence.\n"
            "4. For each theme: a 1-paragraph synthesis.\n"
            "5. Close with: which blog/category deserves more attention this week?"
        )
