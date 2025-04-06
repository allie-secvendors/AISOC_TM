import streamlit as st
from openai import OpenAI
import re
import sqlite3

client = OpenAI(api_key="")

# SQLite connection
conn = sqlite3.connect("your_database.db")
cursor = conn.cursor()

# Backlog requirements
backlog_requirements = [
    "Create a query to alert when any API endpoint experiences a 50% increase in average response time compared to the previous hour's baseline.",
    "Users have reported unusual account activity. Create monitoring to detect anomalous user session patterns that could indicate account compromise. Consider factors like login frequency, concurrent sessions, and access patterns.",
    "Monitor for scenarios where error rates exceed 5% of total requests per endpoint while also having high response times (>2s) in the last 15 minutes.",
    "The application seems slow during peak hours. Create a query to help us understand what's causing it.",
    "Create proactive monitoring for resource utilization across our microservices. We need early warning when any service is trending towards capacity limits, considering historical usage patterns and growth rates."
]

def generate_sql_query(requirement):
    prompt = f"""You are an expert SQL developer. Convert the following requirement into a well-written SQL query:

{requirement}

SQL Query:"""
    try:
        response = client.chat.completions.create(model="gpt-4",
        messages=[{"role": "developer", "content": "You are an expert assistant."},
                  {"role": "user", "content": prompt}],
        max_tokens=300,
        temperature=0.5)
        return response.choices[0].message.content.strip()
    except Exception as e:
        st.error(f"Error generating SQL query: {e}")
        return None

def is_safe_select_query(query):
    """
    Validates that a SQL query is safe to execute by checking:
    1. It's a SELECT statement (not modifying data)
    2. No dangerous SQL patterns
    """
    # Remove comments and normalize whitespace
    query = re.sub(r'--.*?(\n|$)', ' ', query)
    query = re.sub(r'/\*.*?\*/', ' ', query, flags=re.DOTALL)
    query = ' '.join(query.split())
    
    # Check if it's a SELECT statement
    if not re.match(r'^\s*SELECT\b', query, re.IGNORECASE):
        return False
    
    # Check for dangerous patterns
    dangerous_patterns = [
        r'\bDROP\b',
        r'\bDELETE\b',
        r'\bUPDATE\b',
        r'\bINSERT\b',
        r'\bALTER\b',
        r'\bTRUNCATE\b',
        r'\bGRANT\b',
        r'\bREVOKE\b',
        r'\bCREATE\b',
        r'\bPRAGMA\b',
        r'\bATTACH\b',
        r';',  # Multiple statements
        r'--', # SQL comments that could hide malicious code
        r'/\*', # Block comments that could hide malicious code
        r'\bINTO\s+OUTFILE\b',
        r'\bINTO\s+DUMPFILE\b',
    ]
    
    for pattern in dangerous_patterns:
        if re.search(pattern, query, re.IGNORECASE):
            return False
    
    return True

def improve_sql_query(query):
    prompt = f"""You are an SQL optimization expert. Improve the following SQL query for readability, efficiency, and performance.
You must ONLY return a safe SELECT query. Do not include any data modification statements like INSERT, UPDATE, DELETE.
Do not change the intent or functionality of the original query.

Original SQL Query:
{query}

Improved SQL Query:"""
    try:
        response = client.chat.completions.create(model="gpt-4",
        messages=[{"role": "system", "content": "You are an expert assistant who only generates safe SELECT queries with no side effects."},
                  {"role": "user", "content": prompt}],
        max_tokens=300,
        temperature=0.5)
        
        improved_query = response.choices[0].message.content.strip()
        
        # Validate the improved query before returning it
        if is_safe_select_query(improved_query):
            return improved_query
        else:
            st.error("The improved query contains potentially unsafe operations and has been rejected.")
            return None
    except Exception as e:
        st.error(f"Error improving SQL query: {e}")
        return None

def execute_sql_query(query):
    # Final safety validation before execution
    if not is_safe_select_query(query):
        st.error("Unsafe SQL query detected. Execution aborted.")
        return None
        
    try:
        cursor.execute(query)
        results = cursor.fetchall()
        return results
    except sqlite3.Error as e:
        st.error(f"Error executing SQL query: {e}")
        return None

def main():
    st.title("Backlog Requirements and SQL Queries")

    requirement = st.selectbox("Select a backlog requirement", backlog_requirements)

    if requirement:
        generated_query = generate_sql_query(requirement)
        if generated_query:
            st.write("Generated SQL Query:")
            st.code(generated_query, language="sql")
            improved_query = improve_sql_query(generated_query)
            if improved_query:
                st.write("Improved SQL Query:")
                st.code(improved_query, language="sql")

                if st.button("Execute Query"):
                    results = execute_sql_query(improved_query)
                    if results:
                        st.write("Query Results:")
                        st.dataframe(results)
                    else:
                        st.warning("Query execution failed.")

if __name__ == "__main__":
    main()