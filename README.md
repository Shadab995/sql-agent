# 🗄️ SQL Agent: ask your database questions in plain English

An AI agent that **turns plain-English questions into SQL, runs them safely, fixes its own mistakes and explains the answer**, built with **LangGraph** and **Claude**.

No SQL knowledge needed: ask *"Who are my top 5 customers?"* and get the query, the table and a human-readable answer.

```text
$ python main.py "What is the revenue per product category?"

🛠️  Generated SQL:
SELECT p.category, ROUND(SUM(oi.quantity * oi.unit_price), 2) AS total_revenue
FROM order_items oi
JOIN products p ON p.product_id = oi.product_id
GROUP BY p.category
ORDER BY total_revenue DESC;
💡 Adds up the money from every order line, grouped by product category.

category    | total_revenue
------------+--------------
Furniture   | 33254.0
Electronics | 31186.66
Books       | 5051.0
Accessories | 3277.5

🤖 Furniture brings in the most revenue (€33,254), just ahead of Electronics (€31,187).
   Books and Accessories are much smaller at about €5,051 and €3,278.
```

---

## ✨ Features

- **Plain English → SQL** with Claude, using your real schema (tables, columns, keys and example rows)
- **Safety guardrails**: only single `SELECT` queries are allowed. Writes (`INSERT`, `DELETE`, `DROP`, ...) are blocked before they reach the database, and SQLite connections are opened in read-only mode as a second layer.
- **Self-correction**: if a query fails, the error is sent back to Claude, which fixes the query (up to 3 attempts)
- **Explainable**: shows the SQL, a one-line explanation, the result table and a plain-English answer
- **Works with any SQL database** supported by SQLAlchemy (SQLite, PostgreSQL, MySQL, ...)
- **Sample database included**: a small online shop to play with right away
- **Two interfaces**: an interactive command line and a Streamlit web app

---

## 🧠 How it works

The agent is a LangGraph **state graph**: five nodes connected by edges, two of which are **conditional** (the agent decides where to go next).

```mermaid
flowchart TD
    A([START]) --> B[get_schema<br/>read tables, columns, keys]
    B --> C[generate_sql<br/>Claude writes the query]
    C --> D{validate_sql<br/>is it a safe SELECT?}
    D -- "blocked" --> F[answer<br/>explain why it was refused]
    D -- "safe" --> E{run_sql<br/>execute on the database}
    E -- "error and attempts < 3<br/>(send the error back)" --> C
    E -- "success" --> G[answer<br/>Claude explains the result]
    F --> H([END])
    G --> H
```

| Node | What it does | Uses the LLM? |
|------|--------------|:---:|
| `get_schema` | Inspects the database with SQLAlchemy and builds a text description of every table, its columns, primary/foreign keys and 3 example rows | ❌ |
| `generate_sql` | Claude writes **one** SQL query and a short explanation. It returns **structured output** (`SQLQuery` Pydantic model). On a retry, the failed query and its error are included in the prompt. | ✅ |
| `validate_sql` | A guardrail in plain Python: rejects multiple statements, anything not starting with `SELECT`/`WITH`, and dangerous keywords | ❌ |
| `run_sql` | Executes the query and fetches at most 100 rows. If the database raises an error, it's saved in the state. | ❌ |
| `answer` | Claude turns the result table into a short, friendly answer | ✅ |

### Key concepts (useful when explaining this project to others)

- **Schema grounding**: an LLM can't guess your table names. Giving it the schema **plus example rows** lets it see real values (e.g. that `status` is `'delivered'`, not `'DELIVERED'`), which greatly improves accuracy.
- **Structured output**: `llm.with_structured_output(SQLQuery)` forces Claude to return `{sql, explanation}` instead of free text, so there's no fragile parsing of Markdown code blocks.
- **Guardrails outside the LLM**: never trust the model to "promise" it won't write `DROP TABLE`. The safety check is deterministic code, and the database connection itself is read-only. That's **defense in depth**.
- **Self-correction loop**: real-world SQL often fails the first time (wrong column, wrong date function). Feeding the exact error back lets the model fix it, the same way a human developer would.
- **Bounded retries**: `MAX_ATTEMPTS = 3` keeps the loop from running forever.
- **Mixing LLM and non-LLM steps**: only 2 of the 5 nodes call Claude. Good agents use the model only where judgment is needed and plain code everywhere else.

---

## 🚀 Getting started

### 1. Prerequisites

- Python **3.10+**
- An **Anthropic API key**: [console.anthropic.com](https://console.anthropic.com)

### 2. Install

```bash
git clone https://github.com/Shadab995/sql-agent.git
cd sql-agent

python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

pip install -r requirements.txt
```

### 3. Configure

```bash
cp .env.example .env             # Windows: copy .env.example .env
```

Then add your `ANTHROPIC_API_KEY` to `.env`.

### 4. Create the sample database

```bash
python create_sample_db.py
```

This creates `shop.db`, a small online shop:

```mermaid
erDiagram
    customers ||--o{ orders : places
    orders ||--|{ order_items : contains
    products ||--o{ order_items : "appears in"
    customers {
        int customer_id PK
        text first_name
        text last_name
        text country
        text city
        date signup_date
    }
    orders {
        int order_id PK
        int customer_id FK
        date order_date
        text status
    }
    order_items {
        int order_item_id PK
        int order_id FK
        int product_id FK
        int quantity
        real unit_price
    }
    products {
        int product_id PK
        text name
        text category
        real price
    }
```

### 5. Run it

**Interactive command line:**

```bash
python main.py
```

**Single question:**

```bash
python main.py "Which country has the most customers?"
```

**Web app:**

```bash
streamlit run app.py
```

Then open http://localhost:8501.

**Your own database:**

```bash
python main.py --db "postgresql+psycopg2://user:pass@localhost:5432/mydb" "How many users signed up last week?"
```

You'll need the matching driver, e.g. `pip install psycopg2-binary` or `pymysql`. You can also set `DATABASE_URL` in `.env`.

### Example questions to try

- Who are our top 5 customers by total spending?
- What's the average order value per country?
- How many orders were placed each month in 2026?
- Which products have never been ordered by customers in France?
- What percentage of orders were cancelled?
- Delete all customers. *(it should refuse 😉)*

---

## 📁 Project structure

```text
sql-agent/
├── sql_agent.py           # The agent: state, guardrails, nodes, graph (start reading here)
├── main.py                # Command-line interface (interactive or single question)
├── app.py                 # Streamlit web interface
├── create_sample_db.py    # Builds the sample shop.db SQLite database
├── requirements.txt
├── .env.example
└── README.md
```

---

## 🔐 Security notes

- The keyword filter is intentionally strict. It may occasionally block a harmless query, for example one using SQLite's `REPLACE()` string function. That's a deliberate trade-off.
- For production, **also connect with a read-only database user**. This is the strongest protection, and it works on any database.
- Results are capped at 100 rows to protect your token budget and avoid sending large amounts of data to the LLM.
- The schema and up to 3 example rows per table are sent to the Claude API. Don't point this at data you're not allowed to share with an external API.

---

## 🛠️ Ideas to extend it

- **Charts**: let Claude choose a chart type and plot results in the Streamlit app
- **Conversation memory**: support follow-ups like "now only for France" (LangGraph checkpointer)
- **Human approval**: pause before running the query (LangGraph `interrupt`)
- **Large schemas**: add a node that selects only the relevant tables before writing SQL
- **Evaluation**: a test set of questions with expected answers to measure accuracy

---

## 📚 Learn more

- [LangGraph docs](https://langchain-ai.github.io/langgraph/)
- [SQLAlchemy docs](https://docs.sqlalchemy.org/)
- [Claude API docs](https://docs.claude.com/)

## 📄 License

MIT. See [LICENSE](LICENSE).
