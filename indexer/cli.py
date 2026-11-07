"""Indexer CLI."""

import typer

from indexer.config import get_settings

app = typer.Typer(no_args_is_help=True)


@app.callback()
def main() -> None:
    """Web3 Indexer - CLI."""
    try:
        from indexer.logging import setup_logging
        setup_logging()
    except Exception:
        pass


@app.command()
def status() -> None:
    """Show the loaded configuration."""
    s = get_settings()
    typer.echo(f"chain_id:         {s.chain_id}")
    typer.echo(f"database_url:     {s.database_url}")
    typer.echo(f"start_block:      {s.start_block}")
    typer.echo(f"confirmations:    {s.confirmations}")
    typer.echo(f"max_block_range:  {s.max_block_range}")
    typer.echo(f"log_level:        {s.log_level}")
    typer.echo(f"rpc_url:          {'***' if s.rpc_url else 'MISSING'}")


@app.command("rpc-check")
def rpc_check() -> None:
    """Verify the RPC connection."""
    from indexer.core.rpc import RPCClient
    s = get_settings()
    typer.echo(f"Connecting to chain_id={s.chain_id}...")
    client = RPCClient(s)
    head = client.block_number()
    typer.echo(f"OK, connection. Head: {head}")


@app.command("db-init")
def db_init() -> None:
    """Create the core tables."""
    from indexer.persistence.db import init_db
    init_db()
    typer.echo("Tables created (or already existed).")


@app.command("adapters")
def adapters_cmd() -> None:
    """List the registered adapters."""
    from indexer.adapters.registry import list_adapters
    for name in list_adapters():
        typer.echo(name)


@app.command("run")
def run_cmd(
    adapter_name: str = typer.Option(..., "--adapter", "-a", help="Adapter name"),
    from_block: int | None = typer.Option(None, "--from-block"),
    to_block: int | None = typer.Option(None, "--to-block"),
    tail: bool = typer.Option(False, "--tail", help="Don't stop when reaching head"),
    skip_backlog: bool = typer.Option(False, "--skip-backlog", help="Jump straight to the current block, ignoring missing history"),
    max_iterations: int | None = typer.Option(None, "--max-iterations"),
) -> None:
    """Run the ingester for an adapter."""
    from indexer.adapters.registry import get_adapter
    from indexer.core.ingester import run as run_ingester
    from indexer.core.rpc import RPCClient
    from indexer.persistence.db import session_scope
    from indexer.persistence.repositories import checkpoints as cp_repo

    s = get_settings()
    adapter = get_adapter(adapter_name)
    rpc = RPCClient(s)

    if tail and not skip_backlog:
        with session_scope() as session:
            cp = cp_repo.get_last_block(session, adapter.chain_id, adapter.name)
        head = rpc.block_number() - s.confirmations
        if head - cp > 5000:
            typer.echo(f"⚠️  WARNING: Your checkpoint is {head - cp} blocks behind.", err=True)
            typer.echo("⚠️  This may take hours. Use --skip-backlog to jump to the present.", err=True)
            typer.echo("", err=True)

    typer.echo(f"Adapter: {adapter.name} (chain_id={adapter.chain_id})")
    typer.echo(f"from_block: {from_block if from_block is not None else 'checkpoint'}")
    typer.echo(f"to_block:   {to_block if to_block is not None else 'head-confirmations'}")
    typer.echo(f"tail:       {tail}")
    typer.echo(f"skip-backlog: {skip_backlog}")
    if max_iterations:
        typer.echo(f"max_iter:   {max_iterations}")
    typer.echo("")

    stats = run_ingester(
        adapter, rpc, s,
        from_block=from_block,
        to_block=to_block,
        tail=tail,
        skip_backlog=skip_backlog,
        max_iterations=max_iterations,
    )

    typer.echo("")
    typer.echo(
        f"OK: {stats.iterations} iterations, {stats.blocks_processed} blocks, "
        f"{stats.events_processed} events, {stats.reorgs_handled} reorgs"
    )


@app.command("backfill")
def backfill_cmd(
    adapter_name: str = typer.Option(..., "--adapter", "-a"),
    from_block: int | None = typer.Option(None, "--from-block", help="Force start block (optional)"),
    to_block: int | None = typer.Option(None, "--to-block", help="Force end block (optional)"),
    chunk_size: int = typer.Option(1000, "--chunk-size", help="Blocks to scan per iteration in automatic mode"),
    log_chunk: int = typer.Option(20, "--log-chunk", help="Log batch size to avoid overloading the RPC"),
    reset: bool = typer.Option(False, "--reset", help="Restart the scan from the current highest block"),
) -> None:
    """Fill in historical gaps.

    If --from-block and --to-block are given, process that exact range forward.
    Otherwise, scan the DB backward, skipping existing blocks,
    until reaching the contract's creation block.
    """
    from indexer.adapters.registry import get_adapter
    from indexer.core.ingester import run as run_ingester
    from indexer.core.rpc import RPCClient
    from indexer.persistence.db import session_scope
    from indexer.persistence.repositories import checkpoints as cp_repo
    from sqlalchemy import text

    s = get_settings()
    adapter = get_adapter(adapter_name)
    rpc = RPCClient(s)

    # If the user specified an exact range, run the traditional backfill
    if from_block is not None or to_block is not None:
        if from_block is None or to_block is None:
            typer.echo("Error: You must specify --from-block and --to-block together, or neither (for automatic mode).", err=True)
            raise typer.Exit(code=1)
        if from_block > to_block:
            typer.echo("Error: --from-block must be <= --to-block", err=True)
            raise typer.Exit(code=1)

        cp_key = f"{adapter.name}:backfill"
        if reset:
            with session_scope() as session:
                cp_repo.set_checkpoint(session, adapter.chain_id, cp_key, 0, None)
            typer.echo(f"Checkpoint '{cp_key}' reset to 0")

        typer.echo(f"Manual mode: processing range {from_block}..{to_block} (batches of {log_chunk})")
        stats = run_ingester(
            adapter, rpc, s,
            from_block=from_block,
            to_block=to_block,
            tail=False,
            checkpoint_key=cp_key,
            max_block_range=log_chunk,  # <-- Force small batches
        )
        with session_scope() as session:
            final_cp = cp_repo.get_last_block(session, adapter.chain_id, cp_key)
        typer.echo(f"OK: {stats.blocks_processed} blocks, {stats.events_processed} events.")
        typer.echo(f"Final checkpoint '{cp_key}': {final_cp}")
        return

    # Automatic mode (backward scan)
    cp_key = f"{adapter.name}:backward"

    with session_scope() as session:
        max_db_block = session.execute(
            text("SELECT MAX(number) FROM blocks WHERE chain_id = :cid"),
            {"cid": adapter.chain_id}
        ).scalar() or 0

    if max_db_block == 0:
        typer.echo("The database is empty. Run the tail first.")
        return

    if reset:
        with session_scope() as session:
            cp_repo.set_checkpoint(session, adapter.chain_id, cp_key, 0, None)
        typer.echo(f"Checkpoint '{cp_key}' reset.")

    with session_scope() as session:
        current_cp = cp_repo.get_last_block(session, adapter.chain_id, cp_key)

    if current_cp == 0:
        current_cp = max_db_block
        with session_scope() as session:
            cp_repo.set_checkpoint(session, adapter.chain_id, cp_key, current_cp, None)

    typer.echo(f"Starting automatic (backward) backfill from block {current_cp}...")
    typer.echo(f"Scanning in chunks of {chunk_size}, processing in batches of {log_chunk}.\n")

    while current_cp > 0:
        end_block = current_cp
        start_block = max(end_block - chunk_size + 1, 0)

        any_code = False
        for addr in adapter.contract_addresses():
            if rpc.has_code(addr, start_block):
                any_code = True
                break

        if not any_code:
            typer.echo(f"\nContract did not exist at block {start_block}. Stopping historical scan.")
            break

        with session_scope() as session:
            count = session.execute(text(
                "SELECT COUNT(*) FROM blocks WHERE chain_id = :cid AND number >= :start AND number <= :end"
            ), {"cid": adapter.chain_id, "start": start_block, "end": end_block}).scalar()

        expected = end_block - start_block + 1

        if count == expected:
            typer.echo(f"Chunk {start_block}..{end_block}: Complete. Jumping further back.")
        else:
            typer.echo(f"Chunk {start_block}..{end_block}: Missing {expected - count} blocks. Filling in (batches of {log_chunk})...")
            with session_scope() as session:
                cp_repo.set_checkpoint(session, adapter.chain_id, cp_key, start_block - 1, None)

            stats = run_ingester(
                adapter, rpc, s,
                from_block=start_block,
                to_block=end_block,
                tail=False,
                checkpoint_key=cp_key,
                max_block_range=log_chunk,  # <-- Force small batches
            )
            typer.echo(f"  -> Filled in {stats.events_processed} new events.")

        current_cp = start_block - 1
        with session_scope() as session:
            cp_repo.set_checkpoint(session, adapter.chain_id, cp_key, current_cp, None)

    typer.echo("\nBackfill finished. The database is consolidated.")


@app.command("reprocess")
def reprocess_cmd(
    adapter_name: str = typer.Option(..., "--adapter", "-a"),
    from_block: int = typer.Option(..., "--from-block"),
    to_block: int = typer.Option(..., "--to-block"),
    clean: bool = typer.Option(False, "--clean"),
) -> None:
    """Reprocess raw_logs without RPC."""
    from indexer.adapters.registry import get_adapter
    from indexer.core.reprocess import reprocess as do_reprocess
    from indexer.persistence.db import session_scope

    adapter = get_adapter(adapter_name)
    with session_scope() as session:
        stats = do_reprocess(session, adapter, from_block, to_block, clean=clean)

    typer.echo(f"OK: {stats.logs_read} logs, {stats.events_dispatched} dispatched, {stats.decode_errors} errors")


@app.command("serve")
def serve(
    host: str = typer.Option("127.0.0.1", "--host"),
    port: int = typer.Option(8000, "--port"),
    reload: bool = typer.Option(False, "--reload"),
) -> None:
    """Start the HTTP API."""
    import uvicorn
    typer.echo(f"API at http://{host}:{port}  (docs: /docs)")
    uvicorn.run("indexer.api.app:create_app", factory=True, host=host, port=port, reload=reload)
