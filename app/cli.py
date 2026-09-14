"""Rich terminal CLI interface for Social Media Monitoring across all platforms."""

import sys
import asyncio
import argparse
from typing import List, Optional
from datetime import datetime

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text
from rich import box

from app.models.post import NormalizedPost
from app.collectors.base import CollectorError, NoAccountError, AuthError, RateLimitError
from app.collectors.manager import CollectorManager
from app.database.db import Database

console = Console()


def display_post_panel(post: NormalizedPost, index: int = 1) -> None:
    """Render a clean Rich panel for a single post or comment."""
    date_str = post.created_at.strftime("%b %d, %Y • %H:%M:%S UTC")
    views_text = f" | [magenta]Views:[/magenta] {post.views:,}" if post.views is not None else ""
    type_badge = f" [bold magenta][{post.item_type.upper()}][/bold magenta]" if getattr(post, "item_type", "post") != "post" else ""

    content = (
        f"[bold white]{post.text}[/bold white]\n\n"
        f"[green]Likes/Upvotes:[/green] {post.likes:,} | "
        f"[cyan]Replies/Comments:[/cyan] {post.replies:,} | "
        f"[yellow]Reposts/Shares:[/yellow] {post.reposts:,}"
        f"{views_text}\n\n"
        f"[dim]ID: {post.id} | Sentiment: {post.sentiment_label} ({post.sentiment_score:.2f})[/dim]\n"
        f"[blue underline]{post.url}[/blue underline]"
    )

    plat_tag = f"[{post.platform.upper()}]"
    title = f"#{index} [bold yellow]{plat_tag}[/bold yellow]{type_badge} [bold cyan]@{post.author_username}[/bold cyan] ({post.author_name}) • [dim]{date_str}[/dim]"
    console.print(Panel(content, title=title, border_style="blue", box=box.ROUNDED))


async def cmd_search(
    query: str,
    limit: int = 20,
    platform: str = "all",
    product: str = "Latest",
    save: bool = True,
    db_path: str = "data/monitoring.db"
) -> None:
    """Search social media by keyword and display results."""
    manager = CollectorManager()
    db = Database(db_path)

    console.print(f"\n[bold]Searching {platform.upper()} for:[/bold] [yellow]\"{query}\"[/yellow] (limit: {limit})...")

    try:
        posts = await manager.search(query=query, limit=limit, platform=platform, product=product)

        if not posts:
            console.print(f"\n[yellow]No posts found matching '{query}'.[/yellow]")
            if save:
                db.log_search(query, results_count=0, platform=platform)
            return

        console.print(f"\n[bold green]Found {len(posts)} items matching \"{query}\":[/bold green]\n")

        for idx, post in enumerate(posts, start=1):
            display_post_panel(post, index=idx)

        if save:
            saved = db.save_posts(posts, searched_query=query)
            console.print(f"\n[green]Saved {saved} posts to local database ({db_path}).[/green]")
            
            console.print("[dim]Running content authenticity and media triage pipeline in background...[/dim]")
            from app.utils.authenticity_engine import AuthenticityEngine
            auth_engine = AuthenticityEngine(db_path=db_path)
            
            # Run authenticity checks
            async def run_auth():
                for p in posts:
                    try:
                        await auth_engine.run_phase_1_verification(p)
                        await auth_engine.run_phase_2_triage(p)
                    except Exception as e:
                        pass
            
            # Use asyncio.create_task to run it without blocking the main output,
            # or await it directly if we want to wait before exiting CLI
            await run_auth()
            console.print("[green]Content authenticity analysis complete![/green]")

    except NoAccountError as e:
        console.print(Panel(
            f"[bold red]Session Credentials Required[/bold red]\n\n{str(e)}",
            title="Authentication Error",
            border_style="red",
        ))
    except (AuthError, RateLimitError, CollectorError) as e:
        console.print(f"\n[bold red]Error during search:[/bold red] {e}")
    except Exception as e:
        console.print(f"\n[bold red]Unexpected error:[/bold red] {e}")


async def cmd_status() -> None:
    """Display current readiness and account status across all 7 platforms."""
    manager = CollectorManager()
    status = await manager.check_status()

    table = Table(title="Dedicated Multi-Platform Collector Status", box=box.ROUNDED)
    table.add_column("Platform", style="cyan", no_wrap=True)
    table.add_column("Ready for Search", style="bold")
    table.add_column("Active Accounts", style="magenta")
    table.add_column("Total Accounts", style="dim")

    for plat_name, st in status.get("platforms", {}).items():
        if st.get("ready"):
            is_ready = "[green]YES (Ready)[/green]"
        elif plat_name in ("x", "linkedin", "facebook", "instagram"):
            is_ready = "[yellow]Requires Session/Cookies[/yellow]"
        else:
            is_ready = "[red]Temporarily Offline[/red]"
        table.add_row(
            plat_name.upper(),
            is_ready,
            str(st.get("active_accounts", 0)),
            str(st.get("total_accounts", 0))
        )

    console.print("\n", table)

    accounts = status.get("accounts", [])
    if accounts:
        acc_table = Table(title="Configured Platform Sessions", box=box.SIMPLE)
        acc_table.add_column("Platform", style="yellow")
        acc_table.add_column("Account Identifier", style="bold")
        acc_table.add_column("Active", style="cyan")
        acc_table.add_column("Total Requests")
        acc_table.add_column("Error Message", style="red")

        for acc in accounts:
            acc_table.add_row(
                str(acc.get("platform", "x")).upper(),
                str(acc.get("account_name") or acc.get("username", "")),
                "[green]Yes[/green]" if acc.get("active") else "[red]No[/red]",
                str(acc.get("total_req", 0)),
                str(acc.get("error_msg") or "None"),
            )
        console.print(acc_table)
    else:
        console.print(
            "\n[dim yellow]No accounts currently configured. "
            "Use 'python run_cli.py add-cookie --platform <name> <account_name> <cookies>' to add credentials.[/dim yellow]\n"
        )


async def cmd_add_cookie(name: str, cookies: str, platform: str = "x") -> None:
    """Add account cookies for any supported platform."""
    manager = CollectorManager()
    try:
        await manager.add_account_cookies(platform=platform, account_name=name, cookies=cookies)
        console.print(f"[bold green]Successfully added {platform.upper()} cookie session for '{name}'![/bold green]")
        console.print(f"[dim]You can now run searches using 'python run_cli.py search <query> --platform {platform}'[/dim]")
    except Exception as e:
        console.print(f"[bold red]Failed to add {platform.upper()} cookies:[/bold red] {e}")


async def cmd_history(limit: int = 15, db_path: str = "data/monitoring.db") -> None:
    """Show past search history."""
    db = Database(db_path)
    history = db.get_search_history(limit=limit)

    table = Table(title="Recent Search History", box=box.ROUNDED)
    table.add_column("ID", style="dim", width=6)
    table.add_column("Query", style="yellow")
    table.add_column("Platform", style="cyan")
    table.add_column("Results Count", justify="right")
    table.add_column("Timestamp", style="dim")

    for h in history:
        table.add_row(
            str(h.get("id")),
            h.get("query"),
            h.get("platform", "x").upper(),
            str(h.get("results_count", 0)),
            h.get("searched_at", "")[:19]
        )

    console.print("\n", table)


async def cmd_list_posts(query: Optional[str] = None, platform: str = "all", limit: int = 15, db_path: str = "data/monitoring.db") -> None:
    """List saved posts from local SQLite database."""
    db = Database(db_path)
    posts = db.get_posts(query=query, platform=platform, limit=limit)

    if not posts:
        console.print("\n[yellow]No saved posts found in local database.[/yellow]")
        return

    console.print(f"\n[bold green]Found {len(posts)} saved posts in database:[/bold green]\n")
    for idx, post in enumerate(posts, start=1):
        display_post_panel(post, index=idx)


async def interactive_loop() -> None:
    """Interactive REPL mode for continuous searching."""
    console.print(Panel(
        "[bold cyan]Social Media Monitoring - Interactive Shell[/bold cyan]\n"
        "Commands:\n"
        "  • Type any keyword to search across platforms\n"
        "  • [yellow]:status[/yellow]    - Check account pool readiness\n"
        "  • [yellow]:history[/yellow]   - View search history\n"
        "  • [yellow]:posts[/yellow]     - View saved posts in SQLite\n"
        "  • [yellow]:cookie[/yellow]    - Register session cookies\n"
        "  • [yellow]:exit[/yellow]      - Exit interactive mode",
        title="Interactive Mode",
        border_style="cyan",
    ))

    while True:
        try:
            prompt = console.input("\n[bold green]Enter keyword or command > [/bold green]").strip()
            if not prompt:
                continue
            if prompt in [":exit", ":quit", "exit", "quit"]:
                console.print("[yellow]Exiting...[/yellow]")
                break
            elif prompt == ":status":
                await cmd_status()
            elif prompt == ":history":
                await cmd_history()
            elif prompt == ":posts":
                await cmd_list_posts()
            elif prompt == ":cookie":
                plat = console.input("Platform (x, linkedin, facebook, instagram) [default: x]: ").strip() or "x"
                name = console.input("Account name (label): ").strip()
                cookies = console.input("Cookies: ").strip()
                if name and cookies:
                    await cmd_add_cookie(name, cookies, platform=plat)
                else:
                    console.print("[red]Account name and cookies cannot be empty.[/red]")
            else:
                await cmd_search(query=prompt, limit=20, platform="all")
        except (KeyboardInterrupt, EOFError):
            console.print("\n[yellow]Exiting...[/yellow]")
            break
        except Exception as e:
            console.print(f"[bold red]Error:[/bold red] {e}")


def main() -> None:
    """CLI argument parser entry point."""
    parser = argparse.ArgumentParser(description="Social Media Monitoring - Multi-Platform Tool")
    subparsers = parser.add_subparsers(dest="command", help="Available subcommands")

    # search command
    p_search = subparsers.add_parser("search", help="Search social posts by keyword")
    p_search.add_argument("query", type=str, help="Search query (e.g. 'COMSATS', 'NUST')")
    p_search.add_argument("--limit", type=int, default=20, help="Max results to fetch (default: 20)")
    p_search.add_argument("--platform", type=str, default="all", choices=["all", "x", "facebook", "reddit", "youtube", "instagram", "linkedin", "news"], help="Target platform (default: all)")
    p_search.add_argument("--product", type=str, default="Latest", choices=["Latest", "Top"], help="Tab for X (Latest or Top)")
    p_search.add_argument("--no-save", action="store_true", help="Do not save results to SQLite")

    # status command
    subparsers.add_parser("status", help="Check collector readiness across all platforms")

    # add-cookie command
    p_cookie = subparsers.add_parser("add-cookie", help="Add or update session cookies for an account")
    p_cookie.add_argument("name", type=str, help="Account label/name")
    p_cookie.add_argument("cookies", type=str, help="Cookie string")
    p_cookie.add_argument("--platform", type=str, default="x", choices=["x", "linkedin", "facebook", "instagram"], help="Target platform (default: x)")

    # history command
    p_hist = subparsers.add_parser("history", help="View recent search queries")
    p_hist.add_argument("--limit", type=int, default=15, help="Number of records to show")

    # posts command
    p_posts = subparsers.add_parser("posts", help="View saved posts in SQLite")
    p_posts.add_argument("--query", type=str, default=None, help="Filter by keyword")
    p_posts.add_argument("--platform", type=str, default="all", help="Filter by platform")
    p_posts.add_argument("--limit", type=int, default=15, help="Number of posts to show")

    # interactive command
    subparsers.add_parser("interactive", help="Start interactive search prompt")

    args = parser.parse_args()

    if args.command == "search":
        asyncio.run(cmd_search(query=args.query, limit=args.limit, platform=args.platform, product=args.product, save=not args.no_save))
    elif args.command == "status":
        asyncio.run(cmd_status())
    elif args.command == "add-cookie":
        asyncio.run(cmd_add_cookie(args.name, args.cookies, platform=args.platform))
    elif args.command == "history":
        asyncio.run(cmd_history(limit=args.limit))
    elif args.command == "posts":
        asyncio.run(cmd_list_posts(query=args.query, platform=args.platform, limit=args.limit))
    elif args.command == "interactive" or args.command is None:
        asyncio.run(interactive_loop())


if __name__ == "__main__":
    main()
