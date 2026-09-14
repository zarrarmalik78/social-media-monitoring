"""Query builder and validator for advanced X (Twitter) search queries."""

import re
from datetime import datetime
from typing import Optional, List, Dict, Any, Union
from pydantic import BaseModel, Field


class SearchQueryFilter(BaseModel):
    """Structured search filters for compiling advanced X search queries."""
    
    # Word matching
    all_words: Optional[str] = Field(None, description="All of these words must appear (space-separated)")
    exact_phrase: Optional[str] = Field(None, description="Exact phrase that must match verbatim")
    any_words: Optional[str] = Field(None, description="Any of these words may appear (will be OR-joined)")
    none_words: Optional[str] = Field(None, description="None of these words must appear (will be negated with -)")
    
    # Account filters
    from_accounts: Optional[str] = Field(None, description="Sent from these accounts (comma or space-separated handles)")
    to_accounts: Optional[str] = Field(None, description="Sent as replies to these accounts (comma or space-separated)")
    mentioned_accounts: Optional[str] = Field(None, description="Mentioning these accounts (comma or space-separated)")
    
    # Language and Dates
    language: Optional[str] = Field(None, description="Two-letter language code (e.g. en, ur, ar)")
    since_date: Optional[str] = Field(None, description="Beginning date in YYYY-MM-DD format")
    until_date: Optional[str] = Field(None, description="Ending date in YYYY-MM-DD format")
    
    # Engagement thresholds
    min_likes: Optional[int] = Field(None, ge=0, description="Minimum number of likes (min_faves:)")
    min_reposts: Optional[int] = Field(None, ge=0, description="Minimum number of reposts/retweets (min_retweets:)")
    min_replies: Optional[int] = Field(None, ge=0, description="Minimum number of replies (min_replies:)")
    
    # Content & Filter flags
    has_links: Optional[bool] = Field(None, description="Include only posts containing links (filter:links)")
    has_media: Optional[bool] = Field(None, description="Include only posts containing media (filter:media)")
    exclude_replies: Optional[bool] = Field(None, description="Exclude reply posts (-filter:replies)")
    exclude_retweets: Optional[bool] = Field(None, description="Exclude retweets (-filter:nativeretweets)")


class QueryBuilder:
    """Utility class to compile structured filters into X search strings and validate raw queries."""

    @staticmethod
    def build(filters: Union[SearchQueryFilter, Dict[str, Any]]) -> str:
        """Compile structured filter object into an X search query string."""
        if isinstance(filters, dict):
            filters = SearchQueryFilter(**filters)

        tokens: List[str] = []

        # 1. All words (AND by default)
        if filters.all_words and filters.all_words.strip():
            tokens.append(filters.all_words.strip())

        # 2. Exact phrase (wrapped in quotes)
        if filters.exact_phrase and filters.exact_phrase.strip():
            clean_phrase = filters.exact_phrase.strip().strip('"')
            tokens.append(f'"{clean_phrase}"')

        # 3. Any words (OR grouping)
        if filters.any_words and filters.any_words.strip():
            raw_any = filters.any_words.strip()
            # Split by OR or whitespace
            words = [w.strip() for w in re.split(r'\s+OR\s+|\s+', raw_any) if w.strip()]
            if len(words) == 1:
                tokens.append(words[0])
            elif len(words) > 1:
                tokens.append(f"({' OR '.join(words)})")

        # 4. None words (exclusion with -)
        if filters.none_words and filters.none_words.strip():
            neg_words = [w.strip().lstrip('-') for w in filters.none_words.strip().split() if w.strip()]
            for nw in neg_words:
                tokens.append(f"-{nw}")

        # 5. Accounts: from:
        if filters.from_accounts and filters.from_accounts.strip():
            accounts = [a.strip().lstrip('@') for a in re.split(r'[, ]+', filters.from_accounts.strip()) if a.strip()]
            if len(accounts) == 1:
                tokens.append(f"from:{accounts[0]}")
            elif len(accounts) > 1:
                tokens.append(f"({' OR '.join(f'from:{acc}' for acc in accounts)})")

        # 6. Accounts: to:
        if filters.to_accounts and filters.to_accounts.strip():
            to_accs = [a.strip().lstrip('@') for a in re.split(r'[, ]+', filters.to_accounts.strip()) if a.strip()]
            if len(to_accs) == 1:
                tokens.append(f"to:{to_accs[0]}")
            elif len(to_accs) > 1:
                tokens.append(f"({' OR '.join(f'to:{acc}' for acc in to_accs)})")

        # 7. Mentioned accounts
        if filters.mentioned_accounts and filters.mentioned_accounts.strip():
            mentions = [a.strip().lstrip('@') for a in re.split(r'[, ]+', filters.mentioned_accounts.strip()) if a.strip()]
            for m in mentions:
                tokens.append(f"@{m}")

        # 8. Language
        if filters.language and filters.language.strip():
            clean_lang = filters.language.strip().lower()
            tokens.append(f"lang:{clean_lang}")

        # 9. Dates
        if filters.since_date and filters.since_date.strip():
            tokens.append(f"since:{filters.since_date.strip()}")
        if filters.until_date and filters.until_date.strip():
            tokens.append(f"until:{filters.until_date.strip()}")

        # 10. Engagement thresholds
        if filters.min_likes is not None and filters.min_likes > 0:
            tokens.append(f"min_faves:{filters.min_likes}")
        if filters.min_reposts is not None and filters.min_reposts > 0:
            tokens.append(f"min_retweets:{filters.min_reposts}")
        if filters.min_replies is not None and filters.min_replies > 0:
            tokens.append(f"min_replies:{filters.min_replies}")

        # 11. Content filters
        if filters.has_links is True:
            tokens.append("filter:links")
        elif filters.has_links is False:
            tokens.append("-filter:links")

        if filters.has_media is True:
            tokens.append("filter:media")
        elif filters.has_media is False:
            tokens.append("-filter:media")

        if filters.exclude_replies is True:
            tokens.append("-filter:replies")

        if filters.exclude_retweets is True:
            tokens.append("-filter:nativeretweets")

        return " ".join(tokens)

    @staticmethod
    def validate(query: str) -> Dict[str, Any]:
        """Validate an X search query string and return diagnostic feedback."""
        clean_q = query.strip()
        errors: List[str] = []
        warnings: List[str] = []
        parsed_operators: Dict[str, Any] = {}

        if not clean_q:
            return {
                "valid": False,
                "errors": ["Search query cannot be empty."],
                "warnings": [],
                "operators": {},
            }

        # Check unbalanced double quotes
        quote_count = clean_q.count('"')
        if quote_count % 2 != 0:
            errors.append("Unbalanced quotation marks in query.")

        # Check unbalanced parentheses
        if clean_q.count("(") != clean_q.count(")"):
            errors.append("Unbalanced parentheses in query.")

        # Detect operators
        for match in re.finditer(r'([a-zA-Z_]+):([^\s\(\)]+)', clean_q):
            op, val = match.group(1).lower(), match.group(2)
            parsed_operators[op] = val

            # Validate date formats
            if op in ("since", "until"):
                try:
                    datetime.strptime(val, "%Y-%m-%d")
                except ValueError:
                    errors.append(f"Invalid date format for '{op}:{val}'. Expected YYYY-MM-DD.")

            # Validate integer metrics
            elif op in ("min_faves", "min_retweets", "min_replies"):
                if not val.isdigit() or int(val) < 0:
                    errors.append(f"Invalid metric value for '{op}:{val}'. Must be a positive integer.")

            # Check unknown operators
            elif op not in ("lang", "from", "to", "filter", "list", "url", "geocode"):
                warnings.append(f"Uncommon or non-standard search operator: '{op}:{val}'.")

        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings,
            "operators": parsed_operators,
            "query": clean_q,
        }
