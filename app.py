import streamlit as st
import sqlite3
import re
from dotenv import load_dotenv
import os
from openai import OpenAI

# Load environment variables and initialize the OpenRouter client.
# OpenRouter is OpenAI-API-compatible, so we keep the official OpenAI SDK
# and just point it at a different base URL.
load_dotenv()
openrouter_key = os.getenv("OPENROUTER_API_KEY")
if not openrouter_key:
    st.error("OPENROUTER_API_KEY is not set. Add it to your .env file.")
    st.stop()

client = OpenAI(
    api_key=openrouter_key,
    base_url="https://openrouter.ai/api/v1",
)

MODEL = "nvidia/nemotron-3-super-120b-a12b:free"

# Verbs that must never appear as a bare word in a query we are willing to run.
FORBIDDEN_VERBS = (
    r"\b(DROP|DELETE|UPDATE|INSERT|ALTER|CREATE|REPLACE|TRUNCATE"
    r"|ATTACH|DETACH|PRAGMA|VACUUM|GRANT|REVOKE|REINDEX)\b"
)


def _strip_literals_and_comments(query):
    """Blank out anything whose contents shouldn't be read as SQL keywords.

    Without this, a perfectly safe query like WHERE Status = 'UPDATED' trips a
    keyword scan on the *data*, and a comment could hide a second statement.
    """
    query = re.sub(r"--[^\n]*", " ", query)          # -- line comments
    query = re.sub(r"/\*.*?\*/", " ", query, flags=re.S)  # /* block comments */
    query = re.sub(r"'(?:[^']|'')*'", "''", query)   # 'string literals'
    query = re.sub(r'"(?:[^"]|"")*"', '""', query)   # "quoted identifiers"
    return query


def is_safe_sql(query):
    """Allow a single read-only statement, and nothing else.

    An allowlist (must be SELECT/WITH) rather than a blocklist of bad words:
    anything we failed to think of is rejected by default instead of admitted.
    """
    cleaned = _strip_literals_and_comments(query)

    # Reject chained statements — "SELECT 1; DROP TABLE orders" is two queries.
    statements = [s for s in cleaned.split(";") if s.strip()]
    if len(statements) != 1:
        return False

    statement = statements[0].strip()

    # Must be a read. CTEs (WITH ...) are fine; they still resolve to a SELECT.
    if not re.match(r"^(SELECT|WITH)\b", statement, re.IGNORECASE):
        return False

    # Belt and braces: catch a write verb smuggled into a subquery.
    return not re.search(FORBIDDEN_VERBS, statement, re.IGNORECASE)

# Function to convert question → SQL
def generate_sql_from_question(question):
    response = client.chat.completions.create(
        model=MODEL,
        # Nemotron 3 Super enables reasoning by default; we want bare SQL, not
        # a chain of thought wrapped around it. Reasoning is optional on this
        # model, so turn it off.
        extra_body={"reasoning": {"enabled": False}},
        temperature=0,  # model default is 1.0 — far too loose for SQL
        messages=[
            {
                "role": "system",
                "content": (
                    "You are an assistant that converts natural language questions into SQL queries. "
                    "Only use the tables and columns that exist in this SQLite schema: "
                    "TABLE customers(CustomerID, Name, City, Email); "
                    "TABLE products(ProductID, ProductName, Category, Price); "
                    "TABLE orders(OrderID, CustomerID, ProductID, OrderDate, Quantity, Total). "
                    "Return SQL only, no explanation."
                )
            },
            {"role": "user", "content": question}
        ]
    )

    sql_query = response.choices[0].message.content or ""
    sql_query = sql_query.strip()

    # Remove markdown ``` fences and optional "sql" labels
    if "```" in sql_query:
        parts = sql_query.split("```")
        if len(parts) >= 2:
            inner = parts[1].lstrip()
            if inner.lower().startswith("sql"):
                inner = inner[3:].lstrip()
            sql_query = inner.strip()

    return sql_query

DB_PATH = "sample_database.db"


# Run SQL safely
def run_sql_query(query):
    """Return (rows, columns) on success, or (None, error_message) on failure.

    The connection is opened read-only, so a query that slips past is_safe_sql
    still cannot modify the database.
    """
    connection = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)

    try:
        cursor = connection.cursor()
        cursor.execute(query)
        results = cursor.fetchall()

        # A statement that returns no result set leaves description as None.
        if cursor.description is None:
            return None, "That query returned no result set."

        columns = [description[0] for description in cursor.description]
        return results, columns

    except sqlite3.Error as e:
        return None, str(e)

    finally:
        connection.close()


# --- Streamlit UI ---
st.set_page_config(page_title="AI SQL Assistant")

st.title("AI SQL Assistant")
st.write("Ask a question in plain English, and I’ll help you turn it into SQL.")

with st.form("user_question_form"):
    user_question = st.text_input("What would you like to know about your data?")
    submitted = st.form_submit_button("Generate SQL")

if submitted:
    # 1. Don't spend an API call on an empty box — the model would happily
    #    invent a question we were never asked.
    if not user_question.strip():
        st.warning("Please enter a question first.")
        st.stop()

    # 2. Generate SQL
    with st.spinner("Generating SQL..."):
        sql = generate_sql_from_question(user_question)

    st.subheader("Generated SQL")
    st.code(sql, language="sql")

    if not sql:
        st.error("The model returned an empty response. Please try again.")
        st.stop()

    # 3. Safety filter: single read-only statement, or we refuse to run it
    if not is_safe_sql(sql):
        st.error("The generated SQL looks unsafe to run. Please try rephrasing your question.")
        st.stop()

    # 4. Run SQL against the database
    results, columns_or_error = run_sql_query(sql)

    st.subheader("Results")

    # 5. Display results or errors
    if results is None:
        st.error(f"Error running SQL: {columns_or_error}")
    elif not results:
        st.info("That query ran successfully but matched no rows.")
    else:
        st.dataframe(
            {columns_or_error[i]: [row[i] for row in results] for i in range(len(columns_or_error))}
        )
