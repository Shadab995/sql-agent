"""
SQL Agent: ask your database questions in plain English
========================================================
A LangGraph agent that turns a question into SQL with Claude, checks that the
query is safe (read-only), runs it, fixes its own mistakes, and explains the result.

Graph:
    START -> get_schema -> generate_sql -> validate_sql --(unsafe)--> answer
                               ^                +--(safe)--> run_sql --(error, retries left)--> generate_sql
                               |                                     +--(success)------------> answer -> END
"""

from __future__ import annotations

import os
import re
from typing import Any, TypedDict

from dotenv import load_dotenv
from langchain_anthropic import ChatAnthropic
from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel, Field
from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.engine import Engine

load_dotenv()

DEFAULT_MODEL = os.getenv("CLAUDE_MODEL", "claude-haiku-5-5")
DEFAULT_DB_URL = os.getenv("DATABASE_URL", "sqlite:///shop.db")
MAX_ROWS = 100       # never return more rows than this to the LLM
MAX_ATTEMPTS = 3     # how many times the agent may retry after a SQL error


# ---------------------------------------------------------------------------
# 1. State
# ---------------------------------------------------------------------------
class SQLState(TypedDict, total=False):
    question: str
    schema: str
    sql: str
    explanation: str
    error: str            # last SQL error (fed back to Claude so it can fix the query)
    attempts: int
    columns: list[str]
    rows: list[list[Any]]
    answer: str


class SQLQuery(BaseModel):
    sql: str = Field(description="A single read-only SQL query (SELECT or WITH ... SELECT).")
    explanation: str = Field(description="One or two sentences explaining what the query does, for a non-technical user.")


# ---------------------------------------------------------------------------
# 2. Database helpers
# ---------------------------------------------------------------------------
def make_engine(db_url: str = DEFAULT_DB_URL) -> Engine:
    engine = create_engine(db_url)
    if engine.dialect.name == "sqlite":
        # Defense in depth: SQLite itself will refuse any write on these connections.
        @event.listens_for(engine, "connect")
        def _read_only(dbapi_conn, _):
            dbapi_conn.execute("PRAGMA query_only = ON")
    return engine


def describe_schema(engine: Engine, sample_rows: int = 3) -> str:
    """Build a text description of every table: columns, keys and a few example rows."""
    insp = inspect(engine)
    parts = []
    with engine.connect() as conn:
        for table in insp.get_table_names():
            cols = insp.get_columns(table)
            pk = set(insp.get_pk_constraint(table).get("constrained_columns", []))
            fks = {
                c: f"{fk['referred_table']}.{fk['referred_columns'][0]}"
                for fk in insp.get_foreign_keys(table)
                for c in fk["constrained_columns"]
            }
            col_lines = []
            for c in cols:
                extra = " PRIMARY KEY" if c["name"] in pk else ""
                if c["name"] in fks:
                    extra += f" -> {fks[c['name']]}"
                col_lines.append(f"  - {c['name']} ({c['type']}){extra}")
            rows = conn.execute(text(f'SELECT * FROM "{table}" LIMIT {sample_rows}')).fetchall()
            examples = "\n".join(f"  {tuple(r)}" for r in rows)
            parts.append(f"Table {table}:\n" + "\n".join(col_lines) + f"\n Example rows:\n{examples}")
    return "\n\n".join(parts)


FORBIDDEN = re.compile(
    r"\b(insert|update|delete|drop|alter|create|replace|truncate|attach|detach|pragma|grant|revoke|vacuum|merge|exec|execute)\b",
    re.IGNORECASE,
)


def check_sql_is_safe(sql: str) -> str | None:
    """Return an error message if the query is not a single read-only statement, else None."""
    cleaned = re.sub(r"--.*?$|/\*.*?\*/", " ", sql, flags=re.MULTILINE | re.DOTALL).strip().rstrip(";")
    if ";" in cleaned:
        return "Only one SQL statement is allowed."
    if not re.match(r"^\s*(select|with)\b", cleaned, re.IGNORECASE):
        return "Only SELECT queries are allowed."
    if match := FORBIDDEN.search(cleaned):
        return f"Forbidden keyword in query: {match.group(0).upper()}"
    return None


# ---------------------------------------------------------------------------
# 3. Graph
# ---------------------------------------------------------------------------
def build_graph(db_url: str = DEFAULT_DB_URL, model: str | None = None):
    engine = make_engine(db_url)
    llm = ChatAnthropic(model=model or DEFAULT_MODEL, temperature=0, max_tokens=2048)
    dialect = engine.dialect.name

    def get_schema(state: SQLState) -> dict:
        """Read the database structure so Claude knows which tables and columns exist."""
        return {"schema": describe_schema(engine), "attempts": 0, "error": ""}

    def generate_sql(state: SQLState) -> dict:
        """Ask Claude to write the SQL. On a retry, include the previous error so it can fix it."""
        retry_note = ""
        if state.get("error"):
            retry_note = (
                f"\n\nYour previous query failed.\nQuery:\n{state['sql']}\nError:\n{state['error']}\n"
                "Fix the query."
            )
        writer = llm.with_structured_output(SQLQuery)
        result = writer.invoke(
            f"You are an expert {dialect} SQL analyst. Write ONE read-only SQL query that answers "
            "the user's question using the schema below.\n"
            "Rules:\n"
            "- Use only tables and columns that exist in the schema.\n"
            "- Use JOINs through the foreign keys shown.\n"
            f"- Unless the user asks for everything, LIMIT results to at most {MAX_ROWS} rows.\n"
            "- Give columns readable aliases (e.g. total_revenue).\n"
            "- Round money values to 2 decimals.\n\n"
            f"Schema:\n{state['schema']}\n\nQuestion: {state['question']}{retry_note}"
        )
        return {"sql": result.sql.strip(), "explanation": result.explanation, "attempts": state["attempts"] + 1}

    def validate_sql(state: SQLState) -> dict:
        """Guardrail: block anything that is not a single SELECT before it touches the database."""
        problem = check_sql_is_safe(state["sql"])
        return {"error": f"BLOCKED: {problem}" if problem else ""}

    def run_sql(state: SQLState) -> dict:
        """Execute the query. If it fails, store the error so the agent can retry."""
        try:
            with engine.connect() as conn:
                result = conn.execute(text(state["sql"]))
                columns = list(result.keys())
                rows = [list(r) for r in result.fetchmany(MAX_ROWS)]
            return {"columns": columns, "rows": rows, "error": ""}
        except Exception as exc:  # noqa: BLE001 - we want to show any DB error to the model
            return {"error": str(exc).split("\n")[0], "columns": [], "rows": []}

    def answer(state: SQLState) -> dict:
        """Explain the result in plain English (or explain why we couldn't answer)."""
        if state.get("error"):
            return {
                "answer": "Sorry, I couldn't answer that question.\n\n"
                f"Last query:\n{state.get('sql', '')}\n\nReason: {state['error']}"
            }
        table = "\n".join([" | ".join(state["columns"])] + [" | ".join(map(str, r)) for r in state["rows"][:50]])
        response = llm.invoke(
            "Answer the user's question in clear, friendly plain English based on the SQL result. "
            "Be concise. Mention key numbers. If the result is empty, say so.\n\n"
            f"Question: {state['question']}\nSQL used:\n{state['sql']}\n\nResult ({len(state['rows'])} rows):\n{table}"
        )
        return {"answer": response.content}

    # Routing functions (conditional edges)
    def after_validation(state: SQLState) -> str:
        return "answer" if state["error"] else "run_sql"

    def after_run(state: SQLState) -> str:
        if state["error"] and state["attempts"] < MAX_ATTEMPTS:
            return "generate_sql"  # self-correction loop
        return "answer"

    graph = StateGraph(SQLState)
    graph.add_node("get_schema", get_schema)
    graph.add_node("generate_sql", generate_sql)
    graph.add_node("validate_sql", validate_sql)
    graph.add_node("run_sql", run_sql)
    graph.add_node("answer", answer)

    graph.add_edge(START, "get_schema")
    graph.add_edge("get_schema", "generate_sql")
    graph.add_edge("generate_sql", "validate_sql")
    graph.add_conditional_edges("validate_sql", after_validation, ["run_sql", "answer"])
    graph.add_conditional_edges("run_sql", after_run, ["generate_sql", "answer"])
    graph.add_edge("answer", END)

    return graph.compile()
