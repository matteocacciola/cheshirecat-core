#!/usr/bin/env python3
"""
Redis Migration Management CLI

Usage:
    python manage_migrations.py upgrade [revision]
    python manage_migrations.py downgrade [revision]
    python manage_migrations.py current
    python manage_migrations.py history [-v|--verbose]
    python manage_migrations.py heads
    python manage_migrations.py show <revision>
    python manage_migrations.py revision -m "message"
"""
import argparse
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


def get_redis_client():
    """Get Redis client from environment or defaults"""
    from cat.db.database import get_db

    return get_db()


def generate_revision_id() -> str:
    """Generate a unique revision ID"""
    # Use timestamp-based ID like Alembic
    return datetime.now().strftime("%Y%m%d%H%M%S")


def get_current_head(migrations_dir: Path) -> str | None:
    """Get current head revision from migrations"""
    revisions = {}
    down_revisions = set()

    for file_path in migrations_dir.glob("*.py"):
        if file_path.name.startswith("__"):
            continue

        with open(file_path, "r") as f:
            content = f.read()

        # Extract revision and down_revision
        for line in content.split("\n"):
            if line.strip().startswith("revision: str = "):
                rev = line.split("=")[1].strip().strip("'\"")
                revisions[rev] = file_path
            elif line.strip().startswith("down_revision: Union[str, Sequence[str], None] = "):
                down_rev = line.split("=")[1].strip().strip("'\"")
                if down_rev != "None":
                    down_revisions.add(down_rev)

    # Head is the revision that's not a down_revision of any other
    for rev in revisions:
        if rev not in down_revisions:
            return rev

    return None


def create_revision(message: str, migrations_dir: Path) -> None:
    """Create a new migration revision"""
    # Generate revision ID
    revision_id = generate_revision_id()

    # Get current head
    head = get_current_head(migrations_dir)

    # Create filename
    filename = f"{revision_id}_{message.lower().replace(" ", "_")}.py"
    filepath = migrations_dir / filename

    # Load template
    template_path = migrations_dir.parent / "script.py.mako"
    if not template_path.exists():
        print(f"Error: Template not found at {template_path}")
        print("Please create the template file first")
        sys.exit(1)

    with open(template_path, "r") as f:
        template_content = f.read()

    # Prepare template variables
    template_vars = {
        "message": message,
        "up_revision": revision_id,
        "down_revision": head,
        "create_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "repr": repr  # Make repr available in template
    }

    # Simple template substitution using string formatting
    # Replace ${variable} with actual values
    content = template_content
    for key, value in template_vars.items():
        if key == "repr":
            continue
        # Handle ${repr(variable)} pattern
        content = content.replace(f"${{repr({key})}}", repr(value))
        # Handle ${variable} pattern
        content = content.replace(f"${{{key}}}", str(value) if value is not None else "None")

    # Write file
    with open(filepath, "w") as f:
        f.write(content)

    print(f"Generated migration: {filename}")
    print(f"  Revision ID: {revision_id}")
    print(f"  Revises: {head or "base"}")
    print(f"\nPlease edit the file to implement upgrade() and downgrade() functions")


def main():
    parser = argparse.ArgumentParser(description="Redis Migration Management")
    subparsers = parser.add_subparsers(dest="command", help="Command to execute")

    # upgrade command
    upgrade_parser = subparsers.add_parser("upgrade", help="Upgrade to a later version")
    upgrade_parser.add_argument("revision", nargs="?", default="head", help="Target revision (default: head)")

    # downgrade command
    downgrade_parser = subparsers.add_parser("downgrade", help="Revert to a previous version")
    downgrade_parser.add_argument("revision", nargs="?", default="-1", help="Target revision (default: -1)")

    # current command
    subparsers.add_parser("current", help="Display the current revision")

    # history command
    history_parser = subparsers.add_parser("history", help="List migration history")
    history_parser.add_argument("-v", "--verbose", action="store_true", help="Verbose output")

    # heads command
    subparsers.add_parser("heads", help="Show current available heads")

    # show command
    show_parser = subparsers.add_parser("show", help="Show revision details")
    show_parser.add_argument("revision", help="Revision to show")

    # revision command (create new migration)
    revision_parser = subparsers.add_parser("revision", help="Create a new migration")
    revision_parser.add_argument("-m", "--message", required=True, help="Migration message")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    # Get migrations directory
    migrations_dir = Path(__file__).parent / "versions"
    migrations_dir.mkdir(parents=True, exist_ok=True)

    # Handle revision creation separately (doesn't need Redis)
    if args.command == "revision":
        create_revision(args.message, migrations_dir)
        return

    # For other commands, need Redis connection
    try:
        r = get_redis_client()
        r.ping()
    except Exception as e:
        print(f"Failed to connect to Redis: {e}")
        sys.exit(1)

    # Import MigrationCommands
    from migrations.env import MigrationCommands
    commands = MigrationCommands(r, str(migrations_dir))

    # Execute command
    if args.command == "upgrade":
        commands.upgrade(args.revision)
    elif args.command == "downgrade":
        commands.downgrade(args.revision)
    elif args.command == "current":
        commands.current()
    elif args.command == "history":
        commands.history(verbose=args.verbose)
    elif args.command == "heads":
        commands.heads()
    elif args.command == "show":
        commands.show(args.revision)


if __name__ == "__main__":
    main()