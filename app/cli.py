"""Command Line Interface for Social Media Monitoring prototype."""

import asyncio
import sys
import argparse
from typing import Optional

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text
from rich import box

from app.collectors.x_collector import XCollector
from app.collectors.base import CollectorError, NoAccountError, AuthError, RateLimitError
from app.database.db import Database
from app.models.post import NormalizedPost

# Force UTF-8 encoding for stdout/stderr on Windows
if sys.platform.startswith("win"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except AttributeError:
        pass

console = Console()


def display_post_panel(post: NormalizedPost, index: int = 1) -> None:
    """Render a clean Rich panel for a single post."""
    date_str = post.created_at.strftime("%b %d, %Y • %H:%M:%S UTC")
    views_text = f" | [magenta]Views:[/magenta] {post.views:,}" if post.views is not None else ""

    content = (
        f"[bold white]{post.text}[/bold white]\n\n"
        f"[green]Likes:[/green] {post.likes:,} | "
        f"[cyan]Replies:[/cyan] {post.replies:,} | "
        f"[yellow]Reposts:[/yellow] {post.reposts:,}"
        f"{views_text}\n\n"
        f"[dim]Post ID: {post.id}[/dim]\n"
        f"[blue underline]{post.url}[/blue underline]"
    )

    title = f"#{index} [bold cyan]@{post.author_username}[/bold cyan] ({post.author_name}) • [dim]{date_str}[/dim]"
    console.print(Panel(content, title=title, border_style="blue", box=box.ROUNDED))


async def cmd_search(query: str, limit: int = 20, product: str = "Latest", save: bool = True, db_path: str = "data/monitoring.db") -> None:
    """Search X by keyword and display results."""
    collector = XCollector()
    db = Database(db_path)

    console.print(f"\n[bold]Searching X for:[/bold] [yellow]\"{query}\"[/yellow] (limit: {limit}, tab: {product})...")

    try:
        posts = await collector.search(query=query, limit=limit, product=product)

        if not posts:
            console.print(f"\n[yellow]No posts found matching '{query}'.[/yellow]")
            if save:
                db.log_search(query, results_count=0)
            return

        console.print(f"\n[bold green]Found {len(posts)} posts matching \"{query}\":[/bold green]\n")

        for idx, post in enumerate(posts, start=1):
            display_post_panel(post, index=idx)

        if save:
            saved = db.save_posts(posts, searched_query=query)
            console.print(f"\n[green]Saved {saved} posts to local database ({db_path}).[/green]")

    except NoAccountError as e:
        console.print(Panel(
            f"[bold red]Account Setup Required[/bold red]\n\n{str(e)}",
            title="Authentication Error",
            border_style="red",
        ))
    except (AuthError, RateLimitError, CollectorError) as e:
        console.print(f"\n[bold red]Error during search:[/bold red] {e}")
    except Exception as e:
        console.print(f"\n[bold red]Unexpected error:[/bold red] {e}")


async def cmd_status() -> None:
    """Display current collector account pool status."""
    collector = XCollector()
    status = await collector.check_status()

    table = Table(title="X Account Pool Status", box=box.ROUNDED)
    table.add_column("Property", style="cyan", no_wrap=True)
    table.add_column("Value", style="magenta")

    table.add_row("Total Accounts", str(status.get("total_accounts", 0)))
    table.add_row("Active Accounts", str(status.get("active_accounts", 0)))
    table.add_row("Inactive Accounts", str(status.get("inactive_accounts", 0)))
    table.add_row("Database Path", status.get("db_path", ""))
    table.add_row("Ready for Search", "[green]YES[/green]" if status.get("ready") else "[red]NO (Requires Cookies/Account)[/red]")

    console.print("\n", table)

    accounts = status.get("accounts", [])
    if accounts:
        acc_table = Table(title="Configured Accounts", box=box.SIMPLE)
        acc_table.add_column("Username / ID", style="bold")
        acc_table.add_column("Logged In", style="green")
        acc_table.add_column("Active", style="cyan")
        acc_table.add_column("Total Requests")
        acc_table.add_column("Error Message", style="red")

        for acc in accounts:
            acc_table.add_row(
                str(acc.get("username", "")),
                str(acc.get("logged_in", "")),
                str(acc.get("active", "")),
                str(acc.get("total_req", 0)),
                str(acc.get("error_msg") or "None"),
            )
        console.print(acc_table)
    else:
        console.print(
            "\n[dim yellow]No accounts currently configured. "
            "Use 'python run_cli.py add-cookie <account_name> <cookies>' to add an account session.[/dim yellow]\n"
        )


async def cmd_add_cookie(name: str, cookies: str) -> None:
    """Add account cookies."""
    collector = XCollector()
    try:
        await collector.add_account_cookies(name, cookies)
        console.print(f"[bold green]Successfully added cookie session for '{name}'![/bold green]")
        console.print("[dim]You can now run searches using 'python run_cli.py search <query>'[/dim]")
    except Exception as e:
        console.print(f"[bold red]Failed to add cookies:[/bold red] {e}")


async def cmd_history(limit: int = 15, db_path: str = "data/monitoring.db") -> None:
    """Show past search history."""
    db = Database(db_path)
    history = db.get_search_history(limit=limit)

    if not history:
        console.print("[yellow]No search history found yet.[/yellow]")
        return

    table = Table(title="Recent Search History", box=box.ROUNDED)
    table.add_column("ID", style="dim", width=4)
    table.add_column("Query", style="bold cyan")
    table.add_column("Platform", style="magenta")
    table.add_column("Results", style="green")
    table.add_column("Searched At (UTC)", style="dim")

    for item in history:
        table.add_row(
            str(item.get("id")),
            item.get("query", ""),
            item.get("platform", "x"),
            str(item.get("results_count", 0)),
            item.get("searched_at", ""),
        )

    console.print("\n", table)


async def cmd_list_posts(limit: int = 15, db_path: str = "data/monitoring.db") -> None:
    """Display saved posts from SQLite."""
    db = Database(db_path)
    posts = db.get_posts(limit=limit)

    if not posts:
        console.print("[yellow]No posts found in database.[/yellow]")
        return

    console.print(f"\n[bold green]Showing last {len(posts)} saved posts:[/bold green]\n")
    for idx, post in enumerate(posts, start=1):
        display_post_panel(post, index=idx)


async def interactive_loop() -> None:
    """Interactive CLI menu loop."""
    console.print(Panel(
        "[bold cyan]Social Media Monitoring - X Search CLI[/bold cyan]\n"
        "[dim]Enter a search keyword (e.g. IIUI, COMSATS, NUST) or special commands:[/dim]\n"
        "  • [yellow]:status[/yellow]    - Check account pool status\n"
        "  • [yellow]:cookie[/yellow]    - Add account cookies\n"
        "  • [yellow]:history[/yellow]   - View search history\n"
        "  • [yellow]:posts[/yellow]     - View stored posts\n"
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
                name = console.input("Account name (label): ").strip()
                cookies = console.input("Cookies (auth_token=...; ct0=...): ").strip()
                if name and cookies:
                    await cmd_add_cookie(name, cookies)
                else:
                    console.print("[red]Account name and cookies cannot be empty.[/red]")
            else:
                # Treat as keyword search
                await cmd_search(query=prompt, limit=20)
        except (KeyboardInterrupt, EOFError):
            console.print("\n[yellow]Exiting...[/yellow]")
            break
        except Exception as e:
            console.print(f"[bold red]Error:[/bold red] {e}")


def main() -> None:
    """CLI argument parser entry point."""
    parser = argparse.ArgumentParser(description="Social Media Monitoring - X Search Tool")
    subparsers = parser.add_subparsers(dest="command", help="Available subcommands")

    # search command
    p_search = subparsers.add_parser("search", help="Search X posts by keyword")
    p_search.add_argument("query", type=str, help="Search query (e.g. 'IIUI', 'COMSATS')")
    p_search.add_argument("--limit", type=int, default=20, help="Max results to fetch (default: 20)")
    p_search.add_argument("--product", type=str, default="Latest", choices=["Latest", "Top"], help="Tab (Latest or Top)")
    p_search.add_argument("--no-save", action="store_true", help="Do not save results to SQLite")

    # status command
    subparsers.add_parser("status", help="Check X account pool readiness")

    # add-cookie command
    p_cookie = subparsers.add_parser("add-cookie", help="Add or update session cookies for an account")
    p_cookie.add_argument("name", type=str, help="Account label/name")
    p_cookie.add_argument("cookies", type=str, help="Cookie string containing auth_token and ct0")

    # history command
    p_hist = subparsers.add_parser("history", help="View recent search queries")
    p_hist.add_argument("--limit", type=int, default=15, help="Number of records to show")

    # posts command
    p_posts = subparsers.add_parser("posts", help="View saved posts in SQLite")
    p_posts.add_argument("--limit", type=int, default=15, help="Number of posts to show")

    # interactive command
    subparsers.add_parser("interactive", help="Start interactive search prompt")

    args = parser.parse_args()

    if args.command == "search":
        asyncio.run(cmd_search(query=args.query, limit=args.limit, product=args.product, save=not args.no_save))
    elif args.command == "status":
        asyncio.run(cmd_status())
    elif args.command == "add-cookie":
        asyncio.run(cmd_add_cookie(args.name, args.cookies))
    elif args.command == "history":
        asyncio.run(cmd_history(limit=args.limit))
    elif args.command == "posts":
        asyncio.run(cmd_list_posts(limit=args.limit))
    elif args.command == "interactive" or args.command is None:
        asyncio.run(interactive_loop())


if __name__ == "__main__":
    main()
