import asyncio
import json
from typing import Optional
import typer
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from sqlalchemy import select, update

from app.db.base import init_db, async_session_maker
from app.db.models import APIKey, SearchLog, CrawlerHealth, Restaurant
from app.core.security import generate_api_key, hash_api_key
from app.core.redis import get_redis_client, CacheManager
from app.core.credentials import (
    set_provider_token,
    add_provider_token,
    get_provider_token,
    rotate_provider_token,
    remove_provider_token,
    list_provider_tokens,
    revoke_provider_token,
)
from app.crawlers.registry import crawler_registry
from app.schemas.restaurant import RestaurantSearchQuery
import app.crawlers  # noqa: F401 - load and register all crawlers


app = typer.Typer(help="Safarchin Crawler Project Management CLI")
apikey_app = typer.Typer(help="Manage API Keys")
db_app = typer.Typer(help="Manage Database")
cache_app = typer.Typer(help="Manage Redis Cache")
crawlers_app = typer.Typer(help="Manage & Test Crawlers")
providers_app = typer.Typer(help="Manage Provider Credentials & Tokens")
token_app = typer.Typer(help="Manage Provider Access Tokens")
restaurants_app = typer.Typer(help="Manage & Sync Restaurants")

app.add_typer(apikey_app, name="apikey")
app.add_typer(db_app, name="db")
app.add_typer(cache_app, name="cache")
app.add_typer(crawlers_app, name="crawlers")
app.add_typer(providers_app, name="providers")
providers_app.add_typer(token_app, name="token")
app.add_typer(restaurants_app, name="restaurants")


console = Console()

def coro(f):
    import functools
    @functools.wraps(f)
    def wrapper(*args, **kwargs):
        return asyncio.run(f(*args, **kwargs))
    return wrapper

# Database commands
@db_app.command("init")
@coro
async def cli_db_init():
    """Initialize database tables."""
    console.print("[bold yellow]Initializing database schema...[/bold yellow]")
    try:
        await init_db()
        console.print("[bold green]✓ Database tables initialized successfully![/bold green]")
    except Exception as e:
        console.print(f"[bold red]✗ Database initialization failed:[/bold red] {e}")

# API Key commands
@apikey_app.command("create")
@coro
async def create_key(
    name: str = typer.Option(..., "--name", "-n", help="Client / application name"),
    tier: str = typer.Option("standard", "--tier", "-t", help="Tier: standard, pro, enterprise, internal"),
    rate_limit: int = typer.Option(60, "--rate-limit", "-r", help="Rate limit requests per minute"),
    quota: int = typer.Option(1000, "--quota", "-q", help="Daily quota count"),
):
    """Generate and store a new API Key."""
    plain_key, key_hash = generate_api_key()
    async with async_session_maker() as session:
        api_key = APIKey(
            key_hash=key_hash,
            client_name=name,
            tier=tier,
            rate_limit_per_min=rate_limit,
            daily_quota=quota,
            is_active=True,
        )
        session.add(api_key)
        await session.commit()
        await session.refresh(api_key)

    console.print(Panel(
        f"[bold green]API Key Generated Successfully![/bold green]\n\n"
        f"[bold cyan]Client Name:[/bold cyan] {name}\n"
        f"[bold cyan]Key ID:[/bold cyan] {api_key.id}\n"
        f"[bold cyan]Tier:[/bold cyan] {tier}\n"
        f"[bold cyan]Rate Limit:[/bold cyan] {rate_limit} req/min\n"
        f"[bold cyan]Daily Quota:[/bold cyan] {quota}\n\n"
        f"[bold yellow]Secret Key (save this now, it won't be shown again):[/bold yellow]\n"
        f"[bold white on red] {plain_key} [/bold white on red]",
        title="New API Key Created",
        border_style="green",
    ))

@apikey_app.command("list")
@coro
async def list_keys():
    """List all API keys."""
    async with async_session_maker() as session:
        result = await session.execute(select(APIKey).order_by(APIKey.created_at.desc()))
        keys = result.scalars().all()

    if not keys:
        console.print("[yellow]No API keys found.[/yellow]")
        return

    table = Table(title="Registered API Keys", border_style="cyan")
    table.add_column("ID", style="dim", no_wrap=True)
    table.add_column("Client Name", style="bold")
    table.add_column("Tier", style="magenta")
    table.add_column("Rate Limit", justify="right")
    table.add_column("Daily Quota", justify="right")
    table.add_column("Status", justify="center")
    table.add_column("Created At", style="dim")

    for k in keys:
        status_str = "[green]ACTIVE[/green]" if k.is_active else "[red]REVOKED[/red]"
        created_str = k.created_at.strftime("%Y-%m-%d %H:%M") if k.created_at else "N/A"
        table.add_row(
            str(k.id)[:8] + "...",
            k.client_name,
            k.tier,
            f"{k.rate_limit_per_min}/m",
            str(k.daily_quota),
            status_str,
            created_str,
        )

    console.print(table)

@apikey_app.command("revoke")
@coro
async def revoke_key(key_id: str = typer.Argument(..., help="ID or prefix of the API key to revoke")):
    """Revoke an active API key."""
    async with async_session_maker() as session:
        result = await session.execute(select(APIKey).where(APIKey.id.startswith(key_id)))
        key = result.scalar_one_or_none()
        if not key:
            console.print(f"[red]No API key found matching ID '{key_id}'[/red]")
            return

        key.is_active = False
        await session.commit()

        # Invalidate Redis cache
        redis_client = get_redis_client()
        await redis_client.delete(f"auth_key:{key.key_hash}")

        console.print(f"[bold green]✓ Revoked API key for client '{key.client_name}' ({key.id})[/bold green]")

# Cache commands
@cache_app.command("flush")
@coro
async def flush_cache():
    """Clear all cached search queries."""
    cache = CacheManager()
    await cache.flush_all()
    console.print("[bold green]✓ Redis cache flushed successfully![/bold green]")

@cache_app.command("stats")
@coro
async def cache_stats():
    """Display Redis cache statistics."""
    redis_client = get_redis_client()
    try:
        info = await redis_client.info("memory")
        keys = await redis_client.keys("*")
        table = Table(title="Redis Cache Stats", border_style="blue")
        table.add_column("Metric", style="bold")
        table.add_column("Value", style="cyan")

        table.add_row("Total Cached Keys", str(len(keys)))
        table.add_row("Used Memory", str(info.get("used_memory_human", "N/A")))
        table.add_row("Peak Memory", str(info.get("used_memory_peak_human", "N/A")))
        console.print(table)
    except Exception as e:
        console.print(f"[red]Could not retrieve Redis stats:[/red] {e}")

# Crawlers commands
@crawlers_app.command("status")
@coro
async def crawler_status():
    """Show registered providers and health status."""
    providers = crawler_registry.list_providers()
    table = Table(title="Registered Crawlers & Capabilities", border_style="green")
    table.add_column("Provider", style="bold")
    table.add_column("Supported Services", style="cyan")
    table.add_column("Status", justify="center")

    for p in providers:
        services = ", ".join(p["services"])
        table.add_row(p["name"], services, "[green]READY[/green]")

    console.print(table)

# Provider Tokens commands
@token_app.command("set")
@coro
async def cli_token_set(
    provider: str = typer.Option(..., "--provider", "-p", help="Provider name (e.g. jajiga)"),
    token: str = typer.Option(..., "--token", "-t", help="JWT or API Bearer token"),
    expires_at: Optional[str] = typer.Option(None, "--expires-at", "-e", help="Expiration ISO datetime, e.g. 2027-10-01T00:00:00Z"),
    days: Optional[int] = typer.Option(None, "--days", "-d", help="Token validity in days from today"),
):
    """Set primary token for a provider, resetting or initializing the pool."""
    exp = expires_at
    if days and not exp:
        from datetime import datetime, timezone, timedelta
        exp = (datetime.now(timezone.utc) + timedelta(days=days)).isoformat()

    result = await set_provider_token(provider=provider, token=token, expires_at=exp)
    console.print(Panel(
        f"[bold green]✓ Provider Token Pool Initialized![/bold green]\n\n"
        f"[bold cyan]Provider:[/bold cyan] {provider}\n"
        f"[bold cyan]Token ID:[/bold cyan] {result.get('id', 'tok_1')}\n"
        f"[bold cyan]Type:[/bold cyan] {result.get('token_type', 'Bearer')}\n"
        f"[bold cyan]Expires At:[/bold cyan] {result.get('expires_at') or 'No expiration'}\n"
        f"[bold cyan]Token Prefix:[/bold cyan] {result['token'][:25]}...",
        title="Primary Token Set",
        border_style="green",
    ))

@token_app.command("add")
@coro
async def cli_token_add(
    provider: str = typer.Option(..., "--provider", "-p", help="Provider name (e.g. jajiga)"),
    token: str = typer.Option(..., "--token", "-t", help="Additional JWT or API Bearer token for pool rotation"),
    expires_at: Optional[str] = typer.Option(None, "--expires-at", "-e", help="Expiration ISO datetime, e.g. 2027-10-01T00:00:00Z"),
    days: Optional[int] = typer.Option(None, "--days", "-d", help="Token validity in days from today"),
):
    """Add a new token to the provider's token pool for multi-token 429 rotation."""
    exp = expires_at
    if days and not exp:
        from datetime import datetime, timezone, timedelta
        exp = (datetime.now(timezone.utc) + timedelta(days=days)).isoformat()

    result = await add_provider_token(provider=provider, token=token, expires_at=exp)
    console.print(Panel(
        f"[bold green]✓ New Token Added to Pool![/bold green]\n\n"
        f"[bold cyan]Provider:[/bold cyan] {provider}\n"
        f"[bold cyan]Token ID:[/bold cyan] {result['id']}\n"
        f"[bold cyan]Expires At:[/bold cyan] {result.get('expires_at') or 'N/A'}\n"
        f"[bold cyan]Token Prefix:[/bold cyan] {result['token'][:25]}...",
        title="Token Pool Enlarged",
        border_style="green",
    ))

@token_app.command("rotate")
@coro
async def cli_token_rotate(
    provider: str = typer.Option(..., "--provider", "-p", help="Provider name (e.g. jajiga)"),
):
    """Manually advance to the next token in the pool."""
    next_tok = await rotate_provider_token(provider=provider, reason="manual_cli")
    if not next_tok:
        console.print(f"[yellow]No token pool configured for '{provider}' to rotate.[/yellow]")
        return

    console.print(Panel(
        f"[bold green]✓ Rotated to Next Token![/bold green]\n\n"
        f"[bold cyan]Provider:[/bold cyan] {provider}\n"
        f"[bold cyan]Active Token ID:[/bold cyan] {next_tok.get('id')}\n"
        f"[bold cyan]Active Prefix:[/bold cyan] {next_tok['token'][:25]}...",
        title="Token Rotated",
        border_style="cyan",
    ))

@token_app.command("remove")
@coro
async def cli_token_remove(
    provider: str = typer.Option(..., "--provider", "-p", help="Provider name (e.g. jajiga)"),
    token: str = typer.Option(..., "--token", "-t", help="Token ID or prefix to remove"),
):
    """Remove a specific token from the pool by ID or prefix."""
    removed = await remove_provider_token(provider=provider, token_id_or_prefix=token)
    if removed:
        console.print(f"[bold green]✓ Removed token '{token}' from pool for {provider}.[/bold green]")
    else:
        console.print(f"[yellow]No matching token found with ID/prefix '{token}' in {provider} pool.[/yellow]")

@token_app.command("get")
@coro
async def cli_token_get(
    provider: str = typer.Option(..., "--provider", "-p", help="Provider name (e.g. jajiga)"),
):
    """Get currently active token details for a provider."""
    data = await get_provider_token(provider)
    if not data:
        console.print(f"[yellow]No active token configured for provider '{provider}'.[/yellow]")
        return

    cd = data.get("cooldown_until")
    cd_status = f"[bold red]COOLDOWN until {cd}[/bold red]" if cd else "[bold green]HEALTHY[/bold green]"

    console.print(Panel(
        f"[bold cyan]Provider:[/bold cyan] {provider}\n"
        f"[bold cyan]Token ID:[/bold cyan] {data.get('id', 'N/A')}\n"
        f"[bold cyan]Type:[/bold cyan] {data.get('token_type', 'Bearer')}\n"
        f"[bold cyan]Status:[/bold cyan] {cd_status}\n"
        f"[bold cyan]Expires At:[/bold cyan] {data.get('expires_at', 'N/A')}\n"
        f"[bold cyan]Token:[/bold cyan] {data['token'][:30]}...{data['token'][-15:]}",
        title=f"Active Token for {provider}",
        border_style="cyan",
    ))

@token_app.command("list")
@coro
async def cli_token_list():
    """List all configured provider token pools and statuses."""
    pools = await list_provider_tokens()
    if not pools:
        console.print("[yellow]No provider token pools configured.[/yellow]")
        return

    table = Table(title="Provider Token Pools & Rotation Status", border_style="cyan")
    table.add_column("Provider", style="bold")
    table.add_column("Token ID", style="magenta")
    table.add_column("Status", justify="center")
    table.add_column("Expires At", style="green")
    table.add_column("Token Preview", style="dim")

    for p in pools:
        p_name = p.get("provider", "unknown")
        tokens = p.get("tokens", [])
        active_idx = p.get("active_index", 0) % len(tokens) if tokens else 0

        for i, t in enumerate(tokens):
            is_active = (i == active_idx)
            is_cd = bool(t.get("cooldown_until"))
            if is_cd:
                status_str = "[bold red]COOLDOWN (429)[/bold red]"
            elif is_active:
                status_str = "[bold green]ACTIVE (IN-USE)[/bold green]"
            else:
                status_str = "[dim]STANDBY[/dim]"

            tok_str = t["token"]
            preview = f"{tok_str[:20]}...{tok_str[-10:]}" if len(tok_str) > 30 else tok_str
            table.add_row(
                p_name if i == 0 else "",
                t.get("id", f"tok_{i+1}"),
                status_str,
                t.get("expires_at", "N/A"),
                preview,
            )

    console.print(table)

@token_app.command("revoke")
@coro
async def cli_token_revoke(
    provider: str = typer.Option(..., "--provider", "-p", help="Provider name to revoke"),
):
    """Revoke and remove all tokens for a provider."""
    removed = await revoke_provider_token(provider)
    if removed:
        console.print(f"[bold green]✓ Revoked all tokens for provider '{provider}'[/bold green]")
    else:
        console.print(f"[yellow]No active token pool found to revoke for '{provider}'.[/yellow]")


@providers_app.command("status")
@coro
async def cli_providers_status():
    """Show providers with supported services and token health."""
    providers = crawler_registry.list_providers()
    tokens = {t["provider"]: t for t in await list_provider_tokens()}

    table = Table(title="Providers Status & Credentials", border_style="blue")
    table.add_column("Provider", style="bold")
    table.add_column("Services", style="cyan")
    table.add_column("Token Auth", justify="center")
    table.add_column("Expires", style="dim")

    for p in providers:
        p_name = p["name"]
        services = ", ".join(p["services"])
        tok = tokens.get(p_name)
        if tok:
            auth_str = "[bold green]CONFIGURED (JWT)[/bold green]"
            exp_str = tok.get("expires_at", "N/A")
        else:
            auth_str = "[dim]PUBLIC (NONE)[/dim]"
            exp_str = "-"
        table.add_row(p_name, services, auth_str, exp_str)

    console.print(table)

# Restaurants commands
@restaurants_app.command("sync")
@coro
async def sync_restaurants(
    city: str = typer.Option(..., "--city", "-c", help="City name to crawl and sync (e.g. Isfahan, Yazd, Tehran)"),
):
    """Crawl restaurants for a city via OpenStreetMap and store in database."""
    console.print(f"[bold yellow]Crawling restaurants for city '{city}'...[/bold yellow]")
    crawler = crawler_registry.get_crawler("openstreetmap")
    if not crawler:
        console.print("[bold red]✗ OpenStreetMap crawler not found in registry![/bold red]")
        return
    query = RestaurantSearchQuery(city=city, limit=500)
    try:
        results = await crawler.search_restaurants(query)
        console.print(f"[bold green]Fetched {len(results)} restaurants from OpenStreetMap.[/bold green]")
        if not results:
            return

        async with async_session_maker() as session:
            count = 0
            for r in results:
                stmt = select(Restaurant).where(Restaurant.osm_id == r.id)
                res = await session.execute(stmt)
                existing = res.scalar_one_or_none()
                if existing:
                    existing.name = r.name
                    existing.name_en = r.name_en
                    existing.cuisine = r.cuisine
                    existing.latitude = r.latitude
                    existing.longitude = r.longitude
                    existing.address = r.address
                    existing.phone = r.phone
                    existing.website = r.website
                    existing.opening_hours = r.opening_hours
                    existing.last_edited = r.last_edited
                    existing.tags_json = json.dumps(r.tags, ensure_ascii=False)
                else:
                    item = Restaurant(
                        osm_id=r.id,
                        name=r.name,
                        name_en=r.name_en,
                        city=city,
                        cuisine=r.cuisine,
                        amenity=r.amenity,
                        latitude=r.latitude,
                        longitude=r.longitude,
                        address=r.address,
                        phone=r.phone,
                        website=r.website,
                        opening_hours=r.opening_hours,
                        last_edited=r.last_edited,
                        tags_json=json.dumps(r.tags, ensure_ascii=False),
                    )
                    session.add(item)
                count += 1
            await session.commit()
            console.print(f"[bold green]✓ Successfully synced {count} restaurants for '{city}' to DB![/bold green]")
    except Exception as e:
        console.print(f"[bold red]✗ Sync failed:[/bold red] {e}")

@restaurants_app.command("list")
@coro
async def list_restaurants(
    city: str = typer.Option(..., "--city", "-c", help="City name"),
    limit: int = typer.Option(20, "--limit", "-l", help="Number of records to display"),
):
    """List restaurants stored in the database for a city."""
    async with async_session_maker() as session:
        stmt = select(Restaurant).where(Restaurant.city.ilike(f"%{city}%")).limit(limit)
        res = await session.execute(stmt)
        items = res.scalars().all()

        if not items:
            console.print(f"[yellow]No restaurants found in DB for city '{city}'[/yellow]")
            return

        table = Table(title=f"Restaurants in {city} (DB)", border_style="cyan")
        table.add_column("OSM ID", style="dim")
        table.add_column("Name", style="bold green")
        table.add_column("Cuisine", style="cyan")
        table.add_column("Phone", style="magenta")
        table.add_column("Address", style="white")

        for r in items:
            table.add_row(r.osm_id, r.name, r.cuisine or "-", r.phone or "-", r.address or "-")

        console.print(table)

if __name__ == "__main__":
    app()


