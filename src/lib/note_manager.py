import argparse
import sys

import notes_db


def list_notes() -> None:
    """Print all packages that have notes, aligned in two columns."""
    rows = notes_db.list_notes_rows()
    if not rows:
        print("No notes found.")
        return
    col_w = max(len(name) for name, _ in rows)
    for name, note in rows:
        print(f"{name:<{col_w}}  {note}")


def main() -> None:
    parser = argparse.ArgumentParser(
        usage=argparse.SUPPRESS,
        description="Manage per-package usage notes",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  pacfz -D firefox "daily browser"   set a note
  pacfz -D firefox -d                delete the note
  pacfz --notes-list                 list all packages with notes
""",
    )
    parser.add_argument('-D', metavar='PKG', dest='pkg', help='package to operate on')
    parser.add_argument('-d', '--delete', action='store_true',
                        help='delete the note for -D <pkg>')
    parser.add_argument('note', nargs='?',
                        help='note text to set (use with -D <pkg>)')
    parser.add_argument('--list', action='store_true',
                        help='list all packages that have notes')
    # --get is for internal/subprocess use.
    parser.add_argument('--get', metavar='PKG', help=argparse.SUPPRESS)

    args = parser.parse_args()

    try:
        if args.list:
            list_notes()
        elif args.get:
            note = notes_db.get_note(args.get)
            if note:
                print(note)
        elif args.pkg:
            if args.delete:
                if notes_db.delete_note(args.pkg):
                    print(f"\u2713 Note deleted for '{args.pkg}'")
                else:
                    print(f"No note found for '{args.pkg}'")
            elif args.note is not None:
                notes_db.set_note(args.pkg, args.note)
                print(f"\u2713 Note set for '{args.pkg}'")
            else:
                parser.error("provide a note string or -d to delete")
        else:
            parser.print_help()
    except RuntimeError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
