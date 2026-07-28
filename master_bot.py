import asyncio
import os
import json
import sys
import argparse
import time
import random
from datetime import datetime
from collections import defaultdict
import pytz

# Telethon imports
from telethon import TelegramClient
from telethon.errors import (
    FloodWaitError,
    RPCError,
    SessionPasswordNeededError,
    UserBannedInChannelError,
    ChatWriteForbiddenError
)

# Rich UI imports
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.progress import (
    Progress,
    SpinnerColumn,
    TextColumn,
    BarColumn,
    TaskProgressColumn,
    TimeElapsedColumn
)
from rich.style import Style

# ==========================================
# 🤖 TELEGRAM BOT MASTER EXECUTION ENGINE
# ==========================================

console = Console()

# Pull credentials securely from the environment
API_ID = os.environ.get("TELEGRAM_API_ID", "")
API_HASH = os.environ.get("TELEGRAM_API_HASH", "")

if not API_HASH or not API_ID:
    console.print(Panel("[bold red]CRITICAL ERROR:[/bold red] API credentials are missing from environment variables!", title="Error", border_style="red"))
    sys.exit(1)

try:
    API_ID = int(API_ID)
except ValueError:
    console.print(Panel("[bold red]CRITICAL ERROR:[/bold red] TELEGRAM_API_ID must be an integer!", title="Error", border_style="red"))
    sys.exit(1)

# Global stats tracker
class BotStats:
    def __init__(self):
        self.total_sent = 0
        self.total_failed = 0
        self.account_stats = defaultdict(lambda: {"sent": 0, "failed": 0})
        self.start_time = time.time()
    
    def add_success(self, account_name):
        self.total_sent += 1
        self.account_stats[account_name]["sent"] += 1
    
    def add_failure(self, account_name):
        self.total_failed += 1
        self.account_stats[account_name]["failed"] += 1
    
    def get_elapsed_time(self):
        return time.time() - self.start_time
    
    def print_stats(self, progress_context=None, milestone=None):
        elapsed = self.get_elapsed_time()
        avg_per_sec = self.total_sent / elapsed if elapsed > 0 else 0
        success_rate = (self.total_sent / (self.total_sent + self.total_failed) * 100) if (self.total_sent + self.total_failed) > 0 else 0
        
        # Build Stats Table
        table = Table(show_header=True, header_style="bold magenta", expand=True)
        table.add_column("Account Name", style="cyan")
        table.add_column("✅ Sent", justify="right", style="green")
        table.add_column("❌ Failed", justify="right", style="red")
        table.add_column("📊 Success Rate", justify="right", style="blue")
        
        for account, stats in self.account_stats.items():
            total = stats["sent"] + stats["failed"]
            acc_rate = (stats["sent"] / total * 100) if total > 0 else 0
            table.add_row(
                account, 
                str(stats['sent']), 
                str(stats['failed']), 
                f"{acc_rate:.1f}%"
            )

        title = f"[bold green]📊 MILESTONE REACHED: {milestone} ✓[/bold green]" if milestone else "[bold blue]📊 FINAL STATISTICS[/bold blue]"
        
        summary = (
            f"⏱️  [bold]Elapsed Time:[/bold] {elapsed:.1f}s\n"
            f"✅ [bold]Total Sent:[/bold] {self.total_sent}\n"
            f"❌ [bold]Total Failed:[/bold] {self.total_failed}\n"
            f"📈 [bold]Average Rate:[/bold] {avg_per_sec:.2f} msg/sec\n"
            f"📋 [bold]Global Success Rate:[/bold] {success_rate:.1f}%"
        )

        panel = Panel(
            table,
            title=title,
            subtitle=summary,
            border_style="green" if milestone else "blue",
            expand=False
        )
        
        if progress_context:
            progress_context.print(panel)
        else:
            console.print(panel)

stats = BotStats()

async def send_with_retry(client, chat_id, message, account_name, progress_context, max_retries=5):
    """Sends a message with robust error handling, exponential backoff, and recovery logic."""
    for attempt in range(1, max_retries + 1):
        try:
            await client.send_message(chat_id, message)
            return True
            
        except FloodWaitError as e:
            progress_context.print(f"[yellow]⚠️ [{account_name}] Rate limited! Sleeping for {e.seconds} seconds...[/yellow]")
            await asyncio.sleep(e.seconds)
            
        except (ConnectionError, TimeoutError, OSError) as e:
            progress_context.print(f"[red]🔌 [{account_name}] Network failure ({e.__class__.__name__}). Reconnecting (Attempt {attempt}/{max_retries})...[/red]")
            try:
                await client.disconnect()
                await client.connect()
            except Exception as conn_e:
                progress_context.print(f"[bold red]❌ [{account_name}] Reconnection failed: {str(conn_e)}[/bold red]")
            await asyncio.sleep(2 ** attempt)
            
        except (UserBannedInChannelError, ChatWriteForbiddenError) as e:
            progress_context.print(f"[red]🚫 [{account_name}] Permission denied in group {chat_id}: {str(e)}[/red]")
            return False # Unrecoverable for this specific group
            
        except RPCError as e:
            progress_context.print(f"[bold red]❌ [{account_name}] Telegram RPC Error: {str(e)}[/bold red]")
            await asyncio.sleep(2 ** attempt)
            
        except Exception as e:
            progress_context.print(f"[bold red]❌ [{account_name}] Unknown error: {str(e)}[/bold red]")
            await asyncio.sleep(2 ** attempt)
            
    return False

async def send_from_account(account_name, session_path, message, group_ids, repeat_count, hz_config, infinite_loop, progress, main_task_id):
    client = None
    try:
        # Initialize client with robust connection parameters
        client = TelegramClient(
            session_path, 
            API_ID, 
            API_HASH,
            connection_retries=None, # Infinite socket retries
            request_retries=10,
            auto_reconnect=True
        )
        
        await client.connect()
        
        if not await client.is_user_authorized():
            progress.print(f"[bold red]❌ [{account_name}] Session invalid or unauthorized. Please re-login.[/bold red]")
            return
            
        loop_mode_text = "INFINITE loops" if infinite_loop else f"{repeat_count} loops"
        progress.print(f"[cyan]🔄 [{account_name}] Connected. Starting {loop_mode_text} across {len(group_ids)} group(s).[/cyan]")
        
        if not group_ids:
            progress.print(f"[yellow]⚠️  [{account_name}] No Group IDs defined![/yellow]")
            return

        total_iterations = repeat_count * len(group_ids)
        current_loop = 0
        
        # Create a specific progress bar for this account
        acc_task_id = progress.add_task(f"[bold green]{account_name}", total=total_iterations if not infinite_loop else None)

        while True:
            for chat_id in group_ids:
                success = await send_with_retry(client, chat_id, message, account_name, progress)
                
                if success:
                    stats.add_success(account_name)
                    # Check for 50-message milestone globally
                    if stats.total_sent % 50 == 0 and stats.total_sent > 0:
                        stats.print_stats(progress_context=progress, milestone=stats.total_sent)
                    
                    # --- HUMANIZATION: MICRO-BREAKS ---
                    # Uses per-account sent stats to calculate when to break
                    acc_sent = stats.account_stats[account_name]["sent"]
                    if hz_config["break_after_count"] > 0 and acc_sent % hz_config["break_after_count"] == 0:
                        break_time = random.uniform(hz_config["break_duration_min"], hz_config["break_duration_max"])
                        progress.print(f"[bold yellow]☕ [{account_name}] Anti-Ban: Taking a human micro-break for {int(break_time)}s...[/bold yellow]")
                        await asyncio.sleep(break_time)
                else:
                    stats.add_failure(account_name)
                    
                if not infinite_loop:
                    progress.advance(acc_task_id)
                    progress.advance(main_task_id)
            
            current_loop += 1
            
            # Break condition for finite loops
            if not infinite_loop and current_loop >= repeat_count:
                break
                
            # --- HUMANIZATION: JITTER (RANDOM INTERVAL) ---
            remaining_loops = "∞" if infinite_loop else (repeat_count - current_loop)
            round_gap = random.uniform(hz_config["round_interval_min"], hz_config["round_interval_max"])
            progress.print(f"[dim]⏳ [{account_name}] Cycle complete. Waiting {int(round_gap)}s... ({remaining_loops} loop(s) remaining)[/dim]")
            await asyncio.sleep(round_gap)
            
        progress.print(f"[bold green]✅ [{account_name}] Execution Completed![/bold green]")
        progress.update(acc_task_id, completed=total_iterations)

    except Exception as e:
        progress.print(f"[bold red]❌ [{account_name}] Fatal Error: {str(e)}[/bold red]")
    finally:
        if client:
            await client.disconnect()
            progress.print(f"[dim]🔌 [{account_name}] Client disconnected safely.[/dim]")

async def main():
    # Setup command line arguments
    parser = argparse.ArgumentParser(description="Run the Telegram Bot Fleet with Enhanced Stats")
    parser.add_argument("--time", type=str, required=True, help="Time slot (e.g., 4am, 8am, visitTejaBot)")
    args = parser.parse_args()
    
    time_slot = args.time
    data_file = f"{time_slot}.json"
    
    # Configure Timezones
    ist_timezone = pytz.timezone('Asia/Kolkata')
    start_time_server = datetime.now()
    start_time_ist = datetime.now(ist_timezone)
    
    # Beautiful Header
    header_panel = Panel(
        f"[bold cyan]⏰ Time Slot:[/bold cyan] {time_slot}\n"
        f"[bold cyan]🌐 Server Start Time:[/bold cyan] {start_time_server.strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"[bold green]🇮🇳 IST Start Time:[/bold green] {start_time_ist.strftime('%Y-%m-%d %H:%M:%S %Z')}",
        title="[bold yellow]🤖 TELEGRAM BOT MASTER EXECUTION ENGINE 🤖[/bold yellow]",
        border_style="yellow",
        expand=False
    )
    console.print(header_panel)
    
    if not os.path.exists(data_file):
        console.print(f"[bold red]❌ Error:[/bold red] {data_file} not found in current directory.")
        sys.exit(1) 

    with open(data_file, "r", encoding="utf-8") as f:
        try:
            data = json.load(f)
        except Exception as e:
            console.print(f"[bold red]❌ Error:[/bold red] Could not read {data_file}. Is it valid JSON? ({str(e)[:50]})")
            sys.exit(1) 
            
    # Extract configuration
    group_ids = data.get("group_ids", [])
    accounts_data = data.get("accounts", [])
    repeat_count = data.get("repeat_count", 1)  
    infinite_loop = data.get("infinite_loop", False)
    
    # Extract Humanization Config (with fallbacks if old JSON format is used)
    old_interval = data.get("interval_seconds", 16)
    hz_data = data.get("humanization_settings", {})
    hz_config = {
        "round_interval_min": hz_data.get("round_interval_min", old_interval),
        "round_interval_max": hz_data.get("round_interval_max", old_interval + 5),
        "break_after_count": hz_data.get("break_after_count", 60),
        "break_duration_min": hz_data.get("break_duration_min", 120),
        "break_duration_max": hz_data.get("break_duration_max", 240)
    }

    # Filter active accounts
    active_accounts = []
    inactive_accounts = []
    for acc in accounts_data:
        is_active = acc.get("active", acc.get("Active", True))
        if is_active:
            active_accounts.append(acc)
        else:
            inactive_accounts.append(acc)

    if not group_ids:
        console.print("[bold yellow]⚠️ No group IDs found in configuration![/bold yellow]")
    if not active_accounts:
        console.print("[bold yellow]⚠️ No active accounts found in data file.[/bold yellow]")
        sys.exit(1)
    
    if inactive_accounts:
        for acc in inactive_accounts:
            console.print(f"[dim]⏭️ Skipping [{acc['name']}] - Marked as inactive.[/dim]")
        console.print()
    
    # Config Summary Table
    cfg_table = Table(show_header=False, box=None)
    cfg_table.add_row("[bold]Active Accounts:[/bold]", str(len(active_accounts)))
    cfg_table.add_row("[bold]Groups:[/bold]", str(len(group_ids)))
    cfg_table.add_row("[bold]Execution Mode:[/bold]", "[bold green]INFINITE[/bold green]" if infinite_loop else f"{repeat_count} Loops")
    cfg_table.add_row("[bold]Interval Jitter:[/bold]", f"{hz_config['round_interval_min']}s to {hz_config['round_interval_max']}s")
    cfg_table.add_row("[bold]Anti-Ban Breaks:[/bold]", f"Every {hz_config['break_after_count']} msgs ({hz_config['break_duration_min']}s to {hz_config['break_duration_max']}s pause)")
    
    console.print(Panel(cfg_table, title="[bold blue]📊 Configuration Loaded[/bold blue]", border_style="blue", expand=False))
    console.print()

    # Calculate global totals for finite execution
    global_total_tasks = 0 if infinite_loop else (len(active_accounts) * len(group_ids) * repeat_count)
    
    # Use Rich Progress Context Manager to handle multiple progress bars safely
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        TimeElapsedColumn(),
        console=console,
        transient=False
    ) as progress:
        
        main_task = progress.add_task("[bold magenta]Global Progress", total=global_total_tasks if not infinite_loop else None)
        
        tasks = []
        for acc in active_accounts:
            session_path = os.path.join("Session", acc["session"])
            tasks.append(
                send_from_account(
                    acc["name"], 
                    session_path, 
                    acc["message"], 
                    group_ids, 
                    repeat_count, 
                    hz_config, 
                    infinite_loop, 
                    progress,
                    main_task
                )
            )

        if not tasks:
            progress.print("[bold yellow]⚠️ No tasks created.[/bold yellow]")
            sys.exit(1) 

        # Execute all tasks concurrently
        await asyncio.gather(*tasks)
    
    # Final cleanup and stats display
    console.print("\n")
    stats.print_stats()
    
    # Calculate End Times
    end_time_server = datetime.now()
    end_time_ist = datetime.now(ist_timezone)
    
    completion_panel = Panel(
        f"[bold green]✅ {time_slot} Operations Completed Successfully![/bold green]\n"
        f"[bold cyan]🌐 Server End Time:[/bold cyan] {end_time_server.strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"[bold green]🇮🇳 IST Start Time:[/bold green] {start_time_ist.strftime('%Y-%m-%d %H:%M:%S %Z')}\n"
        f"[bold green]🇮🇳 IST End Time:[/bold green] {end_time_ist.strftime('%Y-%m-%d %H:%M:%S %Z')}",
        border_style="green",
        expand=False
    )
    console.print(completion_panel)

if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        console.print("\n[bold red]⚠️ Process interrupted by user. Shutting down gracefully...[/bold red]")
        sys.exit(0)
