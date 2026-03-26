#!/usr/bin/env python3
import argparse
import glob
import json
import logging
import os
import sys

def serialize_fawn_quirks(input_dir: str, output_file: str) -> None:
    """Read all .json files in the given directory and bundle them into a single list."""
    logging.info(f"Scanning for quirks in {input_dir}")
    search_pattern = os.path.join(input_dir, "**/*.json")
    files = glob.glob(search_pattern, recursive=True)

    if not files:
        logging.warning("No JSON quirk files found.")
        return

    bundled_quirks = []
    failed_parses = 0

    for filepath in sorted(files):
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
                
                # Support single-object definitions
                if isinstance(data, dict):
                    bundled_quirks.append(data)
                # Support files that are already arrays
                elif isinstance(data, list):
                    bundled_quirks.extend(data)
                else:
                    logging.error(f"Unsupported JSON format in {filepath}. Expected dict or list.")
                    failed_parses += 1
        except json.JSONDecodeError as e:
            logging.error(f"Malformed JSON in {filepath}: {e}")
            failed_parses += 1
        except Exception as e:
            logging.error(f"Error reading {filepath}: {e}")
            failed_parses += 1

    if failed_parses > 0:
        logging.critical(f"Failed to parse {failed_parses} files. Aborting bundling to ensure deterministic state.")
        sys.exit(1)

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(bundled_quirks, f, indent=2)

    logging.info(f"Successfully bundled {len(bundled_quirks)} quirks into {output_file}")


def main():
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    parser = argparse.ArgumentParser(description="Bundle multiple Fawn JSON quirks into a single array payload.")
    parser.add_argument("--input-dir", required=True, help="Directory containing .json quirk files.")
    parser.add_argument("--output", required=True, help="Destination filename for the bundled JSON array.")

    args = parser.parse_args()

    if not os.path.isdir(args.input_dir):
        logging.critical(f"Input directory does not exist: {args.input_dir}")
        sys.exit(1)

    serialize_fawn_quirks(args.input_dir, args.output)


if __name__ == "__main__":
    main()
