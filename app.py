"""Streamlit web UI for the SQL Agent.

Run with:
    streamlit run app.py
"""

import pandas as pd
import streamlit as st

from sql_agent import DEFAULT_DB_URL, build_graph, describe_schema, make_engine

st.set_page_config(page_title="SQL Agent", page_icon="🗄️", layout="wide")
st.title("🗄️ SQL Agent: talk to your database")
st.caption("LangGraph + Claude: plain English in, safe read-only SQL and answers out.")

with st.sidebar:
    db_url = st.text_input("Database URL", DEFAULT_DB_URL)
    with st.expander("📋 Database schema"):
        try:
            st.code(describe_schema(make_engine(db_url), sample_rows=0), language="text")
        except Exception as exc:  # noqa: BLE001
            st.error(f"Could not connect: {exc}")
    st.markdown("**Try asking:**")
    examples = [
        "Who are our top 5 customers by total spending?",
        "What is the revenue per product category?",
        "How many orders were placed each month in 2026?",
        "Which products have never been ordered by customers in France?",
    ]
    for ex in examples:
        if st.button(ex, use_container_width=True):
            st.session_state.question = ex


@st.cache_resource
def get_app(url: str):
    return build_graph(db_url=url)


question = st.text_input("Ask a question about your data", key="question")

if st.button("Ask", type="primary", disabled=not question):
    final = {}
    with st.status("Thinking...", expanded=True) as status:
        for step in get_app(db_url).stream({"question": question}, stream_mode="updates"):
            for node, update in step.items():
                final.update(update)
                if node == "get_schema":
                    st.write("📋 Read the database schema")
                elif node == "generate_sql":
                    st.write(f"🛠️ Wrote SQL (attempt {update['attempts']})")
                elif node == "validate_sql":
                    st.write("⛔ " + update["error"] if update["error"] else "🛡️ Safety check passed")
                elif node == "run_sql":
                    st.write(f"⚠️ SQL error: {update['error']}" if update["error"] else f"▶️ Ran query: {len(update['rows'])} rows")
        status.update(label="Done!", state="complete", expanded=False)

    st.markdown(f"### 🤖 Answer\n{final.get('answer', '')}")
    if final.get("sql"):
        with st.expander("🔍 SQL query", expanded=True):
            st.code(final["sql"], language="sql")
            st.caption(final.get("explanation", ""))
    if final.get("columns"):
        st.dataframe(pd.DataFrame(final["rows"], columns=final["columns"]), use_container_width=True)
