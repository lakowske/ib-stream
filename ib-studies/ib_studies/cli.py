"""Command line interface for IB-Studies."""

import asyncio
import logging
import signal
import sys
from typing import Optional

import click

from ib_studies.formatters.human import HumanFormatter
from ib_studies.formatters.json import JSONFormatter
from ib_studies.models import StreamConfig, StudyConfig
from ib_studies.multi_study_runner import MultiStudyRunner
from ib_studies.stream_client import StreamClient
from ib_studies.studies.bollinger_bands import BollingerBandsStudy
from ib_studies.studies.delta import DeltaStudy
from ib_studies.studies.multi_delta import MultiStreamDeltaStudy
from ib_studies.studies.passthrough import PassThroughStudy
from ib_studies.studies.vwap import VWAPStudy
from ib_studies.ws_client import WebSocketMultiStreamClient

# Configure logging to stderr
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s",
    stream=sys.stderr
)
logger = logging.getLogger(__name__)


class StudyRunner:
    """Manages running studies with stream client."""

    def __init__(self, study, formatter, stream_config: StreamConfig):
        """Initialize study runner."""
        self.study = study
        self.formatter = formatter
        self.stream_config = stream_config
        self.stream_client = None
        self.running = False
        self._stop_event = asyncio.Event()

    async def run(self, contract_id: int, tick_types: Optional[list[str]] = None) -> None:
        """Run the study."""
        self.running = True

        # Setup aggressive signal handlers for immediate termination
        def signal_handler():
            logger.info("Received interrupt signal, stopping stream immediately...")
            self._stop_event.set()

            # Force stop stream client
            if self.stream_client:
                logger.info("Force stopping stream client...")
                # Cancel the stream client's operations
                asyncio.create_task(self._force_cleanup())

        def emergency_exit(sig, frame):
            logger.error("Emergency exit - forcing immediate shutdown")
            sys.exit(1)

        # For Windows compatibility
        if sys.platform != "win32":
            loop = asyncio.get_running_loop()
            loop.add_signal_handler(signal.SIGTERM, signal_handler)
            loop.add_signal_handler(signal.SIGINT, signal_handler)
            # Add emergency handler
            signal.signal(signal.SIGQUIT, emergency_exit)
        else:
            # Windows doesn't support signal handlers in event loops
            signal.signal(signal.SIGINT, lambda s, f: signal_handler())
            signal.signal(signal.SIGTERM, lambda s, f: signal_handler())

        try:
            # Create and connect stream client
            self.stream_client = StreamClient(self.stream_config)
            # Use provided tick types or fall back to study's required types
            stream_tick_types = tick_types or self.study.required_tick_types
            await self.stream_client.connect(contract_id, stream_tick_types)

            # Show header
            if hasattr(self.formatter, 'format_header'):
                header = self.formatter.format_header(
                    contract_id,
                    self.study.name,
                    window_seconds=self.study.config.window_seconds,
                    timestamp=self.study._start_time.isoformat()
                )
                self.formatter.output(header)

            # Start consumption with stop event monitoring
            consume_task = asyncio.create_task(self.stream_client.consume(self._handle_tick))
            stop_task = asyncio.create_task(self._stop_event.wait())

            # Wait for either consumption to complete or stop signal
            done, pending = await asyncio.wait(
                [consume_task, stop_task],
                return_when=asyncio.FIRST_COMPLETED
            )

            # Cancel pending tasks
            for task in pending:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

        except KeyboardInterrupt:
            logger.info("Interrupted by user")
        except Exception as e:
            logger.error("Error running study: %s", e, exc_info=True)
            if hasattr(self.formatter, 'format_error'):
                error_msg = self.formatter.format_error(str(e))
                self.formatter.output(error_msg)
        finally:
            await self.cleanup()

    async def _handle_tick(self, tick_type: str, data: dict, stream_id: str = "", timestamp: str = "") -> None:
        """Handle incoming v2 protocol tick data."""
        if self._stop_event.is_set():
            return

        logger.debug("StudyRunner._handle_tick: tick_type=%s, stream_id=%s, timestamp=%s, data=%s",
                    tick_type, stream_id, timestamp, data)

        try:
            # Process tick through study with v2 protocol signature
            result = self.study.process_tick(tick_type, data, stream_id, timestamp)
            logger.debug("Study result: %s", result)

            # Format and output result
            if result:
                logger.debug("Formatting output for result: %s", result)
                output = self.formatter.format_update(result)
                self.formatter.output(output)
            else:
                logger.debug("No result from study, skipping output")

        except Exception as e:
            logger.error("Error processing tick: %s", e, exc_info=True)

    async def _force_cleanup(self) -> None:
        """Force immediate cleanup of all resources."""
        logger.info("Force cleanup initiated")
        try:
            if self.stream_client:
                # Stop the stream client
                await self.stream_client.stop()
                await asyncio.wait_for(self.stream_client.disconnect(), timeout=2.0)
        except asyncio.TimeoutError:
            logger.warning("Force cleanup timed out, proceeding anyway")
        except Exception as e:
            logger.error("Error in force cleanup: %s", e)
        finally:
            # Exit after cleanup attempt
            logger.info("Force cleanup complete, exiting...")
            sys.exit(0)

    async def cleanup(self) -> None:
        """Clean up resources."""
        self.running = False

        # Show final summary
        if hasattr(self.formatter, 'format_final_summary'):
            summary = self.study.get_summary()
            final_output = self.formatter.format_final_summary({"summary": summary})
            self.formatter.output(final_output)

        # Disconnect stream client
        if self.stream_client:
            await self.stream_client.disconnect()

        # Close formatter
        if hasattr(self.formatter, 'close'):
            self.formatter.close()


class WebSocketStudyRunner:
    """Study runner for WebSocket transport."""

    def __init__(self, study, formatter, stream_config: StreamConfig):
        """Initialize WebSocket study runner."""
        self.study = study
        self.formatter = formatter
        self.stream_config = stream_config
        self.ws_client = None
        self.running = False
        self._stop_event = asyncio.Event()

    async def run(self, contract_id: int, tick_types: Optional[list[str]] = None) -> None:
        """Run the study using WebSocket transport."""
        self.running = True

        # Setup signal handlers
        def signal_handler():
            logger.info("Received interrupt signal, stopping WebSocket stream...")
            self._stop_event.set()

        def emergency_exit(sig, frame):
            logger.error("Emergency exit - forcing immediate shutdown")
            sys.exit(1)

        # Signal handling setup
        if sys.platform != "win32":
            loop = asyncio.get_running_loop()
            loop.add_signal_handler(signal.SIGTERM, signal_handler)
            loop.add_signal_handler(signal.SIGINT, signal_handler)
            signal.signal(signal.SIGQUIT, emergency_exit)
        else:
            signal.signal(signal.SIGINT, lambda s, f: signal_handler())
            signal.signal(signal.SIGTERM, lambda s, f: signal_handler())

        try:
            # Create WebSocket client
            self.ws_client = WebSocketMultiStreamClient(self.stream_config)

            # Use provided tick types or fall back to study's required types
            stream_tick_types = tick_types or self.study.required_tick_types

            # Show header
            if hasattr(self.formatter, 'format_header'):
                header = self.formatter.format_header(
                    contract_id,
                    self.study.name,
                    window_seconds=self.study.config.window_seconds,
                    timestamp=self.study._start_time.isoformat()
                )
                self.formatter.output(header)

            # Connect and start consumption
            await self.ws_client.connect_multiple(contract_id, stream_tick_types, self._handle_tick)

            # Start consumption task
            consume_task = asyncio.create_task(self.ws_client.consume(self._handle_tick))
            stop_task = asyncio.create_task(self._stop_event.wait())

            # Wait for either consumption to complete or stop signal
            done, pending = await asyncio.wait(
                [consume_task, stop_task],
                return_when=asyncio.FIRST_COMPLETED
            )

            # Cancel pending tasks
            for task in pending:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

        except KeyboardInterrupt:
            logger.info("Interrupted by user")
        except Exception as e:
            logger.error("Error running WebSocket study: %s", e, exc_info=True)
            if hasattr(self.formatter, 'format_error'):
                error_msg = self.formatter.format_error(str(e))
                self.formatter.output(error_msg)
        finally:
            await self.cleanup()

    async def _handle_tick(self, tick_type: str, data: dict, stream_id: str = "", timestamp: str = "") -> None:
        """Handle incoming v2 protocol tick data."""
        if self._stop_event.is_set():
            return

        logger.debug("WebSocketStudyRunner._handle_tick: tick_type=%s, stream_id=%s, timestamp=%s, data=%s",
                    tick_type, stream_id, timestamp, data)

        try:
            # Process tick through study with v2 protocol signature
            result = self.study.process_tick(tick_type, data, stream_id, timestamp)
            logger.debug("Study result: %s", result)

            # Format and output result
            if result:
                logger.debug("Formatting output for result: %s", result)
                output = self.formatter.format_update(result)
                self.formatter.output(output)
            else:
                logger.debug("No result from study, skipping output")

        except Exception as e:
            logger.error("Error processing tick: %s", e, exc_info=True)

    async def cleanup(self) -> None:
        """Clean up resources."""
        self.running = False

        # Show final summary
        if hasattr(self.formatter, 'format_final_summary'):
            summary = self.study.get_summary()
            final_output = self.formatter.format_final_summary({"summary": summary})
            self.formatter.output(final_output)

        # Disconnect WebSocket client
        if self.ws_client:
            await self.ws_client.disconnect_all()

        # Close formatter
        if hasattr(self.formatter, 'close'):
            self.formatter.close()


@click.group()
@click.option('--verbose', '-v', is_flag=True, help='Enable verbose logging')
@click.option('--base-url', default='http://localhost:8001', help='IB-Stream base URL')
@click.option('--transport', type=click.Choice(['sse', 'websocket']), default='sse',
              help='Transport protocol (sse or websocket)')
@click.pass_context
def cli(ctx, verbose, base_url, transport):
    """IB-Studies: Real-time market data analysis using IB-Stream."""
    ctx.ensure_object(dict)

    # Configure logging
    if verbose:
        logging.getLogger('ib_studies').setLevel(logging.DEBUG)
    else:
        logging.getLogger('ib_studies').setLevel(logging.INFO)

    # Store config
    ctx.obj['stream_config'] = StreamConfig(base_url=base_url)
    ctx.obj['transport'] = transport


@cli.command()
@click.option('--contract', '-c', type=int, required=True, help='Contract ID to analyze')
@click.option('--window', '-w', type=int, default=60, help='Time window in seconds')
@click.option('--json', 'output_json', is_flag=True, help='Output in JSON format')
@click.option('--output', '-o', type=click.Path(), help='Output file path')
@click.option('--tick-types', default='BidAsk,Last', help='Comma-separated tick types')
@click.option('--timeout', type=int, help='Stream timeout in seconds (no timeout if not specified)')
@click.option('--neutral-zone', type=float, default=0.0, help='Neutral zone percentage')
@click.option('--timezone', help='Display timezone (e.g., "US/Eastern", "UTC", defaults to local)')
@click.pass_context
def delta(ctx, contract, window, output_json, output, tick_types, timeout, neutral_zone, timezone):
    """Run delta study to analyze buying/selling pressure."""

    # Parse tick types
    tick_type_list = [t.strip() for t in tick_types.split(',')]

    # Create study config
    study_config = StudyConfig(
        window_seconds=window,
        neutral_zone_percent=neutral_zone
    )

    # Update stream config
    stream_config = ctx.obj['stream_config']
    if timeout is not None:
        stream_config.timeout = timeout

    # Create study
    study = DeltaStudy(study_config)

    # Create formatter
    output_file = None
    if output:
        output_file = open(output, 'w')

    if output_json:
        formatter = JSONFormatter(output_file, pretty=False)
    else:
        formatter = HumanFormatter(output_file, display_timezone=timezone)

    # Select runner based on transport
    transport = ctx.obj.get('transport', 'sse')

    if transport == 'websocket':
        # Use WebSocket transport
        runner = WebSocketStudyRunner(study, formatter, stream_config)
    else:
        # Use SSE transport (default)
        runner = StudyRunner(study, formatter, stream_config)

    def handle_interrupt(sig, frame):
        logger.info("Interrupt received, forcing exit...")
        sys.exit(0)

    # Set up emergency signal handler
    signal.signal(signal.SIGINT, handle_interrupt)

    try:
        asyncio.run(runner.run(contract, tick_type_list))
    except KeyboardInterrupt:
        logger.info("Stopped by user")
        sys.exit(0)
    except Exception as e:
        logger.error("Error: %s", e)
        sys.exit(1)
    finally:
        if output_file:
            output_file.close()


@cli.command()
@click.option('--contract', '-c', type=int, required=True, help='Contract ID to analyze')
@click.option('--window', '-w', type=int, default=60, help='Time window in seconds')
@click.option('--json', 'output_json', is_flag=True, help='Output in JSON format')
@click.option('--output', '-o', type=click.Path(), help='Output file path')
@click.option('--timeout', type=int, help='Stream timeout in seconds (no timeout if not specified)')
@click.option('--neutral-zone', type=float, default=0.0, help='Neutral zone percentage')
@click.option('--timezone', help='Display timezone (e.g., "US/Eastern", "UTC", defaults to local)')
@click.pass_context
def true_delta(ctx, contract, window, output_json, output, timeout, neutral_zone, timezone):
    """Run true delta study using both BidAsk and Last streams simultaneously."""

    # Create study config
    study_config = StudyConfig(
        window_seconds=window,
        neutral_zone_percent=neutral_zone
    )

    # Update stream config
    stream_config = ctx.obj['stream_config']
    if timeout is not None:
        stream_config.timeout = timeout

    # Create multi-stream delta study
    study = MultiStreamDeltaStudy(study_config)

    # Create formatter
    output_file = None
    if output:
        output_file = open(output, 'w')

    if output_json:
        formatter = JSONFormatter(output_file, pretty=False)
    else:
        formatter = HumanFormatter(output_file, display_timezone=timezone)

    # Select runner based on transport
    transport = ctx.obj.get('transport', 'sse')

    if transport == 'websocket':
        # Use WebSocket transport
        runner = WebSocketStudyRunner(study, formatter, stream_config)
    else:
        # Use SSE transport (default)
        runner = MultiStudyRunner(study, formatter, stream_config)

    def handle_interrupt(sig, frame):
        logger.info("Interrupt received, forcing exit...")
        sys.exit(0)

    # Set up emergency signal handler
    signal.signal(signal.SIGINT, handle_interrupt)

    try:
        # Use the study's required tick types (BidAsk and Last)
        asyncio.run(runner.run(contract, study.required_tick_types))
    except KeyboardInterrupt:
        logger.info("Stopped by user")
        sys.exit(0)
    except Exception as e:
        logger.error("Error: %s", e)
        sys.exit(1)
    finally:
        if output_file:
            output_file.close()


@cli.command()
@click.option('--contract', '-c', type=int, required=True, help='Contract ID to analyze')
@click.option('--json', 'output_json', is_flag=True, help='Output in JSON format')
@click.option('--output', '-o', type=click.Path(), help='Output file path')
@click.option('--tick-types', default='BidAsk,Last', help='Comma-separated tick types')
@click.option('--timeout', type=int, help='Stream timeout in seconds (no timeout if not specified)')
@click.option('--timezone', help='Display timezone (e.g., "US/Eastern", "UTC", defaults to local)')
@click.pass_context
def passthrough(ctx, contract, output_json, output, tick_types, timeout, timezone):
    """Pass-through study to see all incoming tick data."""

    # Parse tick types
    tick_type_list = [t.strip() for t in tick_types.split(',')]

    # Create study config
    study_config = StudyConfig(window_seconds=60)  # Default window

    # Update stream config
    stream_config = ctx.obj['stream_config']
    if timeout is not None:
        stream_config.timeout = timeout

    # Create study
    study = PassThroughStudy(study_config)

    # Create formatter
    output_file = None
    if output:
        output_file = open(output, 'w')

    if output_json:
        formatter = JSONFormatter(output_file, pretty=True)
    else:
        formatter = HumanFormatter(output_file, display_timezone=timezone)

    # Select runner based on transport
    transport = ctx.obj.get('transport', 'sse')

    if transport == 'websocket':
        # Use WebSocket transport
        runner = WebSocketStudyRunner(study, formatter, stream_config)
    else:
        # Use SSE transport (default)
        runner = StudyRunner(study, formatter, stream_config)

    try:
        asyncio.run(runner.run(contract, tick_type_list))
    except KeyboardInterrupt:
        logger.info("Stopped by user")
    except Exception as e:
        logger.error("Error: %s", e)
        sys.exit(1)
    finally:
        if output_file:
            output_file.close()


@cli.command()
@click.option('--base-url', help='IB-Stream base URL (overrides global)')
@click.pass_context
def health(ctx, base_url):
    """Check IB-Stream server health."""

    # Use provided URL or default
    stream_config = ctx.obj['stream_config']
    if base_url:
        stream_config.base_url = base_url

    async def check_health():
        client = StreamClient(stream_config)
        try:
            health_info = await client.check_health()
            click.echo(f"Health: {health_info}")
        except Exception as e:
            click.echo(f"Health check failed: {e}")
            sys.exit(1)

    asyncio.run(check_health())


@cli.command()
@click.option('--base-url', help='IB-Stream base URL (overrides global)')
@click.pass_context
def info(ctx, base_url):
    """Get IB-Stream server information."""

    # Use provided URL or default
    stream_config = ctx.obj['stream_config']
    if base_url:
        stream_config.base_url = base_url

    async def get_info():
        client = StreamClient(stream_config)
        try:
            info_data = await client.get_stream_info()
            click.echo(f"Server Info: {info_data}")
        except Exception as e:
            click.echo(f"Info request failed: {e}")
            sys.exit(1)

    asyncio.run(get_info())


@cli.command()
@click.option('--contract', '-c', type=int, required=True, help='Contract ID to analyze')
@click.option('--window', '-w', type=int, default=0, help='Time window in seconds (0 for session-based)')
@click.option('--json', 'output_json', is_flag=True, help='Output in JSON format')
@click.option('--output', '-o', type=click.Path(), help='Output file path')
@click.option('--tick-types', default='last', help='Comma-separated tick types')
@click.option('--timeout', type=int, help='Stream timeout in seconds (no timeout if not specified)')
@click.option('--std-dev', type=float, default=3.0, help='Standard deviation multiplier for bands')
@click.option('--timezone', help='Display timezone (e.g., "US/Eastern", "UTC", defaults to local)')
@click.pass_context
def vwap(ctx, contract, window, output_json, output, tick_types, timeout, std_dev, timezone):
    """Run VWAP study to analyze volume-weighted average price with volatility bands."""

    # Parse tick types
    tick_type_list = [t.strip() for t in tick_types.split(',')]

    # Create study config
    study_config = StudyConfig(
        window_seconds=window,
        vwap_std_dev_multiplier=std_dev
    )

    # Update stream config
    stream_config = ctx.obj['stream_config']
    if timeout is not None:
        stream_config.timeout = timeout

    # Create study
    study = VWAPStudy(study_config)

    # Create formatter
    output_file = None
    if output:
        output_file = open(output, 'w')

    if output_json:
        formatter = JSONFormatter(output_file, pretty=False)
    else:
        formatter = HumanFormatter(output_file, display_timezone=timezone)

    # Select runner based on transport
    transport = ctx.obj.get('transport', 'sse')

    if transport == 'websocket':
        # Use WebSocket transport
        runner = WebSocketStudyRunner(study, formatter, stream_config)
    else:
        # Use SSE transport (default)
        runner = StudyRunner(study, formatter, stream_config)

    def handle_interrupt(sig, frame):
        logger.info("Interrupt received, forcing exit...")
        sys.exit(0)

    # Set up emergency signal handler
    signal.signal(signal.SIGINT, handle_interrupt)

    try:
        asyncio.run(runner.run(contract, tick_type_list))
    except KeyboardInterrupt:
        logger.info("Stopped by user")
        sys.exit(0)
    except Exception as e:
        logger.error("Error: %s", e)
        sys.exit(1)
    finally:
        if output_file:
            output_file.close()


@cli.command()
@click.option('--contract', '-c', type=int, required=True, help='Contract ID to analyze')
@click.option('--period', '-p', type=int, default=1200, help='Period in seconds (default 20 minutes)')
@click.option('--json', 'output_json', is_flag=True, help='Output in JSON format')
@click.option('--output', '-o', type=click.Path(), help='Output file path')
@click.option('--tick-types', default='last', help='Comma-separated tick types')
@click.option('--timeout', type=int, help='Stream timeout in seconds (no timeout if not specified)')
@click.option('--std-dev', type=float, default=1.0, help='Standard deviation multiplier for bands')
@click.option('--timezone', help='Display timezone (e.g., "US/Eastern", "UTC", defaults to local)')
@click.pass_context
def bollinger(ctx, contract, period, output_json, output, tick_types, timeout, std_dev, timezone):
    """Run Bollinger Bands study to analyze price with moving average and volatility bands."""

    # Parse tick types
    tick_type_list = [t.strip() for t in tick_types.split(',')]

    # Create study config with Bollinger-specific settings
    study_config = StudyConfig(
        window_seconds=period,
        bollinger_period_seconds=period,
        bollinger_std_dev_multiplier=std_dev
    )

    # Update stream config
    stream_config = ctx.obj['stream_config']
    if timeout is not None:
        stream_config.timeout = timeout

    # Create study
    study = BollingerBandsStudy(study_config)

    # Create formatter
    output_file = None
    if output:
        output_file = open(output, 'w')

    if output_json:
        formatter = JSONFormatter(output_file, pretty=False)
    else:
        formatter = HumanFormatter(output_file, display_timezone=timezone)

    # Select runner based on transport
    transport = ctx.obj.get('transport', 'sse')

    if transport == 'websocket':
        # Use WebSocket transport
        runner = WebSocketStudyRunner(study, formatter, stream_config)
    else:
        # Use SSE transport (default)
        runner = StudyRunner(study, formatter, stream_config)

    def handle_interrupt(sig, frame):
        logger.info("Interrupt received, forcing exit...")
        sys.exit(0)

    # Set up emergency signal handler
    signal.signal(signal.SIGINT, handle_interrupt)

    try:
        asyncio.run(runner.run(contract, tick_type_list))
    except KeyboardInterrupt:
        logger.info("Stopped by user")
        sys.exit(0)
    except Exception as e:
        logger.error("Error: %s", e)
        sys.exit(1)
    finally:
        if output_file:
            output_file.close()


@cli.command()
def version():
    """Show version information."""
    from ib_studies import __version__
    click.echo(f"IB-Studies version {__version__}")


def main():
    """Main entry point."""
    cli()


if __name__ == '__main__':
    main()
