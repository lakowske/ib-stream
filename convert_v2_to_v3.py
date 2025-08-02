#!/usr/bin/env python3
"""
V2 to V3 Storage Converter CLI

Command-line interface for converting v2 storage data to optimized v3 format.
"""

import asyncio
import argparse
import logging
import sys
from pathlib import Path

# Add the source directory to path
sys.path.insert(0, str(Path(__file__).parent / 'ib-stream' / 'src'))

from ib_stream.storage.v2_to_v3_converter import V2ToV3StorageConverter


def setup_logging(verbose: bool = False):
    """Setup logging configuration."""
    level = logging.DEBUG if verbose else logging.INFO
    
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(sys.stdout)
        ]
    )
    
    # Reduce noise from other loggers
    logging.getLogger('asyncio').setLevel(logging.WARNING)


async def main():
    """Main entry point for the conversion CLI."""
    parser = argparse.ArgumentParser(
        description='Convert IB Stream v2 storage to optimized v3 format',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Convert all data from storage/v2 to storage/v3
  python convert_v2_to_v3.py storage/v2 storage/v3
  
  # Convert with verbose logging
  python convert_v2_to_v3.py storage/v2 storage/v3 --verbose
  
  # Convert only to JSON format (skip protobuf)
  python convert_v2_to_v3.py storage/v2 storage/v3 --no-protobuf
  
  # Use smaller buffer for memory-constrained environments
  python convert_v2_to_v3.py storage/v2 storage/v3 --buffer-size 100
        """
    )
    
    parser.add_argument('source_path', type=Path,
                       help='Path to v2 storage directory')
    parser.add_argument('target_path', type=Path,
                       help='Path where v3 storage will be created')
    
    parser.add_argument('--no-json', action='store_true',
                       help='Skip conversion to JSON format')
    parser.add_argument('--no-protobuf', action='store_true',
                       help='Skip conversion to protobuf format')
    parser.add_argument('--buffer-size', type=int, default=1000,
                       help='Number of messages to buffer before writing (default: 1000)')
    parser.add_argument('--report-path', type=Path,
                       help='Custom path for conversion report (default: target_path/conversion-TIMESTAMP.json)')
    parser.add_argument('--verbose', '-v', action='store_true',
                       help='Enable verbose logging')
    parser.add_argument('--dry-run', action='store_true',
                       help='Show what would be converted without actually doing it')
    
    args = parser.parse_args()
    
    # Setup logging
    setup_logging(args.verbose)
    logger = logging.getLogger(__name__)
    
    # Validate arguments
    if not args.source_path.exists():
        logger.error(f"Source path does not exist: {args.source_path}")
        sys.exit(1)
    
    if not args.source_path.is_dir():
        logger.error(f"Source path is not a directory: {args.source_path}")
        sys.exit(1)
    
    if args.no_json and args.no_protobuf:
        logger.error("Cannot disable both JSON and protobuf conversion")
        sys.exit(1)
    
    if args.buffer_size < 1:
        logger.error("Buffer size must be at least 1")
        sys.exit(1)
    
    # Create converter
    converter = V2ToV3StorageConverter(
        v2_storage_path=args.source_path,
        v3_storage_path=args.target_path,
        enable_json=not args.no_json,
        enable_protobuf=not args.no_protobuf,
        buffer_size=args.buffer_size
    )
    
    # Show configuration
    logger.info("V2 to V3 Storage Converter")
    logger.info("=" * 50)
    logger.info(f"Source path: {args.source_path}")
    logger.info(f"Target path: {args.target_path}")
    logger.info(f"JSON conversion: {'enabled' if not args.no_json else 'disabled'}")
    logger.info(f"Protobuf conversion: {'enabled' if not args.no_protobuf else 'disabled'}")
    logger.info(f"Buffer size: {args.buffer_size}")
    logger.info(f"Dry run: {'yes' if args.dry_run else 'no'}")
    logger.info("")
    
    if args.dry_run:
        # Find files that would be converted
        v2_files = converter.v2_reader.find_v2_files()
        logger.info(f"Would convert {len(v2_files)} files:")
        
        total_size = 0
        for file_path in v2_files[:20]:  # Show first 20 files
            size_mb = file_path.stat().st_size / (1024 * 1024)
            total_size += file_path.stat().st_size
            logger.info(f"  {file_path} ({size_mb:.2f} MB)")
        
        if len(v2_files) > 20:
            logger.info(f"  ... and {len(v2_files) - 20} more files")
        
        logger.info(f"Total size: {total_size / (1024 * 1024):.2f} MB")
        logger.info(f"Estimated target size: {total_size * 0.5 / (1024 * 1024):.2f} MB (50% reduction)")
        return
    
    try:
        # Check if target already exists and is not empty
        if args.target_path.exists() and any(args.target_path.iterdir()):
            response = input(f"Target directory {args.target_path} already exists and is not empty. Continue? (y/N): ")
            if response.lower() not in ['y', 'yes']:
                logger.info("Conversion cancelled by user")
                return
        
        # Start conversion
        logger.info("Starting conversion...")
        start_time = asyncio.get_event_loop().time()
        
        report = await converter.convert_all()
        
        end_time = asyncio.get_event_loop().time()
        duration = end_time - start_time
        
        # Save conversion report
        report_path = await converter.save_conversion_report(report, args.report_path)
        
        # Display summary
        logger.info("")
        logger.info("Conversion Summary")
        logger.info("=" * 50)
        logger.info(f"Duration: {duration:.1f} seconds")
        logger.info(f"Files processed: {report.total_files_processed}")
        logger.info(f"Messages converted: {report.total_messages_converted:,}")
        logger.info(f"Messages failed: {report.total_messages_failed:,}")
        
        if report.total_source_size_bytes > 0:
            source_mb = report.total_source_size_bytes / (1024 * 1024)
            target_mb = report.total_target_size_bytes / (1024 * 1024)
            saved_mb = report.space_saved_bytes / (1024 * 1024)
            saved_pct = (1 - report.compression_ratio) * 100
            
            logger.info(f"Source size: {source_mb:.2f} MB")
            logger.info(f"Target size: {target_mb:.2f} MB")
            logger.info(f"Space saved: {saved_mb:.2f} MB ({saved_pct:.1f}%)")
            
            if duration > 0:
                throughput = report.total_messages_converted / duration
                logger.info(f"Throughput: {throughput:,.0f} messages/second")
        
        if report.errors:
            logger.warning(f"Conversion completed with {len(report.errors)} errors")
            logger.warning("See conversion report for details")
        else:
            logger.info("Conversion completed successfully!")
        
        logger.info(f"Report saved to: {report_path}")
        
        # Exit with error code if there were failures
        if report.total_messages_failed > 0 or report.errors:
            sys.exit(1)
    
    except KeyboardInterrupt:
        logger.info("Conversion interrupted by user")
        sys.exit(130)
    except Exception as e:
        logger.error(f"Conversion failed: {e}")
        if args.verbose:
            logger.exception("Full traceback:")
        sys.exit(1)


if __name__ == '__main__':
    asyncio.run(main())