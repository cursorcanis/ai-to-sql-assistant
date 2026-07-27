import streamlit as st
from streamlit.errors import StreamlitSecretNotFoundError
import re
from dotenv import load_dotenv
import os
from openai import OpenAI, APIError, APITimeoutError, RateLimitError
from sqlalchemy import create_engine
from sqlalchemy.exc import SQLAlchemyError

load_dotenv()


def get_secret(name):
    """Read config from Streamlit secrets first, then the environment.

    Streamlit Cloud has no .env file — secrets come from the app's Secrets
    panel. Locally there are no Streamlit secrets, so .env is used. Checking
    both means the same code runs in either place.
    """
    try:
        if name in st.secrets:
            return st.secrets[name]
    except (FileNotFoundError, StreamlitSecretNotFoundError):
        pass  # No secrets.toml locally — expected.
    return os.getenv(name)


openrouter_key = get_secret("OPENROUTER_API_KEY")
if not openrouter_key:
    st.error(
        "OPENROUTER_API_KEY is not set. Add it to .env locally, or to the "
        "Secrets panel on Streamlit Cloud."
    )
    st.stop()

# The SDK defaults to a 600s read timeout with 2 retries — a stalled or
# rate-limited request would leave the user staring at a spinner for up to
# half an hour. Fail fast instead and let them retry.
client = OpenAI(
    api_key=openrouter_key,
    base_url="https://openrouter.ai/api/v1",
    timeout=30.0,
    max_retries=1,
)

MODEL = "nvidia/nemotron-3-super-120b-a12b:free"

DATABASE_URL = get_secret("DATABASE_URL")
if not DATABASE_URL:
    st.error(
        "DATABASE_URL is not set. Add your Supabase connection string to .env "
        "locally, or to the Secrets panel on Streamlit Cloud."
    )
    st.stop()

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
        max_tokens=900,  # explanation + SQL; bounds a runaway reply
        messages=[
            {
                "role": "system",
                "content": (
                    "You are an assistant that converts natural language questions into "
                    "PostgreSQL queries. Only use the tables and columns that exist in "
                    "this schema: "
                    "TABLE customers(customer_id, name, city, email); "
                    "TABLE products(product_id, product_name, category, price); "
                    "TABLE orders(order_id, customer_id, product_id, order_date, quantity, total). "
                    "All identifiers are lowercase snake_case — never quote them. "
                    "order_date is a DATE column, so use PostgreSQL date functions "
                    "such as EXTRACT or DATE_TRUNC rather than SQLite's strftime. "
                    "Write a single read-only SELECT statement. "
                    "Before returning SQL, briefly explain what the query will do "
                    "in as many sentences as it takes. Then return SQL only, with "
                    "no markdown fences."
                )
            },
            {"role": "user", "content": question}
        ]
    )

    reply = (response.choices[0].message.content or "").strip()

    # Remove markdown ``` fences and optional "sql" labels. The prompt asks for
    # no fences, but models add them anyway often enough to keep this.
    if "```" in reply:
        parts = reply.split("```")
        if len(parts) >= 2:
            prose = parts[0].strip()
            inner = parts[1].lstrip()
            if inner.lower().startswith("sql"):
                inner = inner[3:].lstrip()
            return prose, inner.strip()

    return split_explanation_and_sql(reply)


def split_explanation_and_sql(reply):
    """Separate the model's prose from the statement itself.

    The prompt asks for an explanation followed by SQL, so the reply is two
    things in one string. is_safe_sql requires the query to *start* with
    SELECT/WITH, and the UI needs to syntax-highlight the SQL alone — so split
    at the first line that opens a statement and treat everything above it as
    the explanation.
    """
    lines = reply.splitlines()
    for i, line in enumerate(lines):
        if re.match(r"^\s*(SELECT|WITH)\b", line, re.IGNORECASE):
            return "\n".join(lines[:i]).strip(), "\n".join(lines[i:]).strip()

    # No statement found — hand the whole thing back as SQL so the safety
    # check rejects it and the user sees what the model actually said.
    return "", reply

@st.cache_resource
def get_engine():
    """One pooled engine for the whole app.

    Streamlit re-runs this script top to bottom on every interaction, so
    connecting per query would exhaust a free-tier connection limit quickly.
    cache_resource keeps a single engine alive across reruns and sessions.
    """
    return create_engine(
        DATABASE_URL,
        pool_size=2,
        max_overflow=0,
        pool_pre_ping=True,   # a pooled connection may have been closed by the
        pool_recycle=300,     # server while idle; check and recycle it
    )


def run_sql_query(query):
    """Return (rows, columns) on success, or (None, error_message) on failure."""
    try:
        with get_engine().connect() as connection:
            # Second line of defence behind the read-only role: even a write
            # this transaction was somehow permitted is refused.
            connection.exec_driver_sql("SET TRANSACTION READ ONLY")

            # exec_driver_sql, not text(): text() would parse ':' in the query
            # as a bind parameter and choke on casts like '::int'.
            result = connection.exec_driver_sql(query)

            if result.returns_rows is False:
                return None, "That query returned no result set."

            columns = list(result.keys())
            rows = result.fetchall()
            return rows, columns

    except SQLAlchemyError as e:
        # __cause__ is the underlying psycopg2 error, which is far more
        # readable than SQLAlchemy's wrapper.
        return None, str(e.__cause__ or e)


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
    try:
        with st.spinner("Generating SQL..."):
            explanation, sql = generate_sql_from_question(user_question)
    except APITimeoutError:
        st.error("The model took too long to respond. Please try again.")
        st.stop()
    except RateLimitError:
        st.error(
            "Rate limit reached on the free tier. Wait a moment and try again."
        )
        st.stop()
    except APIError as e:
        st.error(f"The model could not be reached: {e}")
        st.stop()

    if explanation:
        st.subheader("What this query does")
        st.write(explanation)

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
