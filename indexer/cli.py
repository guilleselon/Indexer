"""CLI del indexador."""

import typer

from indexer.config import get_settings

app = typer.Typer(no_args_is_help=True)


@app.callback()
def main() -> None:
    """Indexador Web3 - CLI."""
    try:
        from indexer.logging import setup_logging
        setup_logging()
    except Exception:
        pass


@app.command()
def status() -> None:
    """Muestra la configuración cargada."""
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
    """Verifica la conexión al RPC."""
    from indexer.core.rpc import RPCClient
    s = get_settings()
    typer.echo(f"Conectando a chain_id={s.chain_id}...")
    client = RPCClient(s)
    head = client.block_number()
    typer.echo(f"OK conexión. Head: {head}")


@app.command("db-init")
def db_init() -> None:
    """Crea las tablas del core."""
    from indexer.persistence.db import init_db
    init_db()
    typer.echo("Tablas creadas (o ya existían).")


@app.command("adapters")
def adapters_cmd() -> None:
    """Lista los adapters registrados."""
    from indexer.adapters.registry import list_adapters
    for name in list_adapters():
        typer.echo(name)


@app.command("run")
def run_cmd(
    adapter_name: str = typer.Option(..., "--adapter", "-a", help="Nombre del adapter"),
    from_block: int | None = typer.Option(None, "--from-block"),
    to_block: int | None = typer.Option(None, "--to-block"),
    tail: bool = typer.Option(False, "--tail", help="No parar al alcanzar el head"),
    skip_backlog: bool = typer.Option(False, "--skip-backlog", help="Saltar directo al bloque actual ignorando el historial faltante"),
    max_iterations: int | None = typer.Option(None, "--max-iterations"),
) -> None:
    """Ejecuta el ingester para un adapter."""
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
            typer.echo(f"⚠️  ADVERTENCIA: Tu checkpoint está a {head - cp} bloques de distancia.", err=True)
            typer.echo("⚠️  Esto puede tardar horas. Usa --skip-backlog para saltar al presente.", err=True)
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
        f"OK: {stats.iterations} iteraciones, {stats.blocks_processed} bloques, "
        f"{stats.events_processed} eventos, {stats.reorgs_handled} reorgs"
    )


@app.command("backfill")
def backfill_cmd(
    adapter_name: str = typer.Option(..., "--adapter", "-a"),
    from_block: int | None = typer.Option(None, "--from-block", help="Forzar bloque de inicio (opcional)"),
    to_block: int | None = typer.Option(None, "--to-block", help="Forzar bloque de fin (opcional)"),
    chunk_size: int = typer.Option(1000, "--chunk-size", help="Bloques a escanear por iteración en modo automático"),
    log_chunk: int = typer.Option(20, "--log-chunk", help="Tamaño de lote de logs para no saturar el RPC"),
    reset: bool = typer.Option(False, "--reset", help="Reiniciar el escaneo desde el bloque más alto actual"),
) -> None:
    """Rellena huecos históricos.
    
    Si se pasan --from-block y --to-block, procesa ese rango exacto hacia adelante.
    Si no, escanea la DB de atrás hacia adelante saltando bloques existentes
    hasta llegar al bloque de creación del contrato.
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
    
    # Si el usuario especificó un rango exacto, hacemos el backfill tradicional
    if from_block is not None or to_block is not None:
        if from_block is None or to_block is None:
            typer.echo("Error: Debes especificar --from-block y --to-block juntos, o ninguno (para modo automático).", err=True)
            raise typer.Exit(code=1)
        if from_block > to_block:
            typer.echo("Error: --from-block debe ser <= --to-block", err=True)
            raise typer.Exit(code=1)

        cp_key = f"{adapter.name}:backfill"
        if reset:
            with session_scope() as session:
                cp_repo.set_checkpoint(session, adapter.chain_id, cp_key, 0, None)
            typer.echo(f"Checkpoint '{cp_key}' reseteado a 0")

        typer.echo(f"Modo manual: procesando rango {from_block}..{to_block} (lotes de {log_chunk})")
        stats = run_ingester(
            adapter, rpc, s,
            from_block=from_block,
            to_block=to_block,
            tail=False,
            checkpoint_key=cp_key,
            max_block_range=log_chunk,  # <-- Forzamos lotes pequeños
        )
        with session_scope() as session:
            final_cp = cp_repo.get_last_block(session, adapter.chain_id, cp_key)
        typer.echo(f"OK: {stats.blocks_processed} bloques, {stats.events_processed} eventos.")
        typer.echo(f"Checkpoint final '{cp_key}': {final_cp}")
        return

    # Modo automático (escaneo inverso)
    cp_key = f"{adapter.name}:backward"
    
    with session_scope() as session:
        max_db_block = session.execute(
            text("SELECT MAX(number) FROM blocks WHERE chain_id = :cid"), 
            {"cid": adapter.chain_id}
        ).scalar() or 0
    
    if max_db_block == 0:
        typer.echo("La base de datos está vacía. Corre el tail primero.")
        return

    if reset:
        with session_scope() as session:
            cp_repo.set_checkpoint(session, adapter.chain_id, cp_key, 0, None)
        typer.echo(f"Checkpoint '{cp_key}' reseteado.")

    with session_scope() as session:
        current_cp = cp_repo.get_last_block(session, adapter.chain_id, cp_key)

    if current_cp == 0:
        current_cp = max_db_block
        with session_scope() as session:
            cp_repo.set_checkpoint(session, adapter.chain_id, cp_key, current_cp, None)

    typer.echo(f"Iniciando Backfill automático (inverso) desde bloque {current_cp}...")
    typer.echo(f"Escaneo en bloques de {chunk_size}, procesamiento en lotes de {log_chunk}.\n")

    while current_cp > 0:
        end_block = current_cp
        start_block = max(end_block - chunk_size + 1, 0)

        any_code = False
        for addr in adapter.contract_addresses():
            if rpc.has_code(addr, start_block):
                any_code = True
                break
        
        if not any_code:
            typer.echo(f"\nEl contrato no existía en el bloque {start_block}. Deteniendo escaneo histórico.")
            break

        with session_scope() as session:
            count = session.execute(text(
                "SELECT COUNT(*) FROM blocks WHERE chain_id = :cid AND number >= :start AND number <= :end"
            ), {"cid": adapter.chain_id, "start": start_block, "end": end_block}).scalar()

        expected = end_block - start_block + 1
        
        if count == expected:
            typer.echo(f"Chunk {start_block}..{end_block}: Completo. Saltando al pasado.")
        else:
            typer.echo(f"Chunk {start_block}..{end_block}: Faltan {expected - count} bloques. Rellenando (lotes de {log_chunk})...")
            with session_scope() as session:
                cp_repo.set_checkpoint(session, adapter.chain_id, cp_key, start_block - 1, None)
            
            stats = run_ingester(
                adapter, rpc, s,
                from_block=start_block,
                to_block=end_block,
                tail=False,
                checkpoint_key=cp_key,
                max_block_range=log_chunk,  # <-- Forzamos lotes pequeños
            )
            typer.echo(f"  -> Rellenados {stats.events_processed} eventos nuevos.")

        current_cp = start_block - 1
        with session_scope() as session:
            cp_repo.set_checkpoint(session, adapter.chain_id, cp_key, current_cp, None)

    typer.echo("\nBackfill finalizado. La base de datos está consolidada.")


@app.command("reprocess")
def reprocess_cmd(
    adapter_name: str = typer.Option(..., "--adapter", "-a"),
    from_block: int = typer.Option(..., "--from-block"),
    to_block: int = typer.Option(..., "--to-block"),
    clean: bool = typer.Option(False, "--clean"),
) -> None:
    """Reprocesa raw_logs sin RPC."""
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
    """Arranca la API HTTP."""
    import uvicorn
    typer.echo(f"API en http://{host}:{port}  (docs: /docs)")
    uvicorn.run("indexer.api.app:create_app", factory=True, host=host, port=port, reload=reload)
