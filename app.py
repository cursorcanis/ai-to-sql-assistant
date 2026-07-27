import streamlit as st
import sqlite3
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

# --- NEW (03_01): SQL safety check ---
def is_safe_sql(query):
    unsafe_keywords = ["DROP", "DELETE", "UPDATE", "INSERT", "ALTER", "CREATE"]
    upper_query = query.upper()
    return not any(keyword in upper_query for keyword in unsafe_keywords)

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

# Run SQL safely
def run_sql_query(query):
    connection = sqlite3.connect("sample_database.db")
    cursor = connection.cursor()

    try:
        cursor.execute(query)
        results = cursor.fetchall()
        columns = [description[0] for description in cursor.description]
        connection.close()
        return results, columns

    except Exception as e:
        connection.close()
        return None, f"SQL error: {str(e)}"   # ← updated per 03_01


# --- Streamlit UI ---
st.set_page_config(page_title="AI SQL Assistant")

st.title("AI SQL Assistant")
st.write("Ask a question in plain English, and I’ll help you turn it into SQL.")

with st.form("user_question_form"):
    user_question = st.text_input("What would you like to know about your data?")
    submitted = st.form_submit_button("Generate SQL")

if submitted:
    # 1. Generate SQL
    sql = generate_sql_from_question(user_question)
    st.subheader("Generated SQL")
    st.code(sql, language="sql")

    # --- NEW (03_01): Safety filter ---
    if not is_safe_sql(sql):
        st.error("The generated SQL looks unsafe to run. Please try rephrasing your question.")
        st.stop()

    # 2. Run SQL against the database
    results, columns_or_error = run_sql_query(sql)

    st.subheader("Results")

    # 3. Display results or errors
    if results is None:
        st.error(f"Error running SQL: {columns_or_error}")
    else:
        st.dataframe(
            {columns_or_error[i]: [row[i] for row in results] for i in range(len(columns_or_error))}
        )
