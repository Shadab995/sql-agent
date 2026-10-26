"""Command-line interface for the SQL Agent.

Usage:
    python main.py                                   # interactive chat
    python main.py "Top 5 customers by revenue"      # one question
    python main.py --db "sqlite:///other.db" "How many orders per month?"
"""

import argparse

from sql_agent import DEFAULT_DB_URL, build_graph


def print_table(columns: list[str], rows: list[list], limit: int = 15) -> None:
    if not columns:
        return
    shown = [[str(v) for v in r] for r in rows[:limit]]
    widths = [max(len(c), *(len(r[i]) for r in shown)) if shown else len(c) for i, c in enumerate(columns)]
    line = "+".join("-" * (w + 2) for w in widths)
    print(" | ".join(c.ljust(w) for c, w in zip(columns, widths)))
    print(line)
    for r in shown:
        print(" | ".join(v.ljust(w) for v, w in zip(r, widths)))
    if len(rows) > limit:
        print(f"... ({len(rows) - limit} more rows)")


def ask(app, question: str) -> None:
    final = {}
    for step in app.stream({"question": question}, stream_mode="updates"):
        for node, update in step.items():
            final.update(update)
            if node == "generate_sql":
                label = "🛠️  Generated SQL" if update["attempts"] == 1 else f"🔁 Fixed SQL (attempt {update['attempts']})"
                print(f"\n{label}:\n{update['sql']}\n💡 {update['explanation']}")
            elif node == "run_sql" and update.get("error"):
                print(f"⚠️  SQL error: {update['error']}")
            elif node == "validate_sql" and update.get("error"):
                print(f"⛔ {update['error']}")
    print()
    print_table(final.get("columns", []), final.get("rows", []))
    print(f"\n🤖 {final['answer']}\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Ask questions about a SQL database in plain English.")
    parser.add_argument("question", nargs="?", help="Question (omit for interactive mode)")
    parser.add_argument("--db", default=DEFAULT_DB_URL, help=f"SQLAlchemy database URL (default: {DEFAULT_DB_URL})")
    parser.add_argument("--model", default=None, help="Claude model (default: CLAUDE_MODEL env var)")
    args = parser.parse_args()

    app = build_graph(db_url=args.db, model=args.model)

    if args.question:
        ask(app, args.question)
        return

    print("💬 SQL Agent: ask questions about your data (type 'exit' to quit)")
    while True:
        try:
            question = input("\nYou: ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if question.lower() in {"exit", "quit", "q"}:
            break
        if question:
            ask(app, question)


if __name__ == "__main__":
    main()
