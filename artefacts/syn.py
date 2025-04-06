import streamlit as st
from openai import OpenAI
import sqlite3
import re

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
    prompt = f"""Convert the following requirement into a well-written, safe SQL query:

{requirement}

Important guidelines:
1. The query should be for read-only operations (SELECT statements only)
2. Do not include any data modification operations (INSERT, UPDATE, DELETE)
3. Do not include any schema modification operations (CREATE, ALTER, DROP)
4. Do not use system functions or commands
5. Use proper escaping for any string literals
6. Follow best practices for SQL security

SQL Query:"""
    
    response = client.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[{"role": "system", "content": prompt}],
        max_tokens=200,
        temperature=0.7
    )
    return response.choices[0].message.content.strip()

def improve_sql_query(query):
    prompt = f"""Improve the following SQL query, making it more efficient and readable, while maintaining strict security guidelines:

{query}

Important guidelines:
1. The improved query should remain a read-only operation (SELECT statement only)
2. Do not include any data modification operations (INSERT, UPDATE, DELETE)
3. Do not include any schema modification operations (CREATE, ALTER, DROP)
4. Do not use system functions or commands
5. Use proper escaping for any string literals
6. Follow best practices for SQL security

Improved SQL Query:"""
    
    response = client.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[{"role": "system", "content": prompt}],
        max_tokens=200,
        temperature=0.7
    )
    return response.choices[0].message.content.strip()

def validate_sql_query(query):
    """
    Validates if the SQL query is safe to execute.
    Only allows SELECT statements and rejects potentially harmful operations.
    
    Returns:
        (bool, str): A tuple containing (is_valid, error_message)
    """
    # Remove comments to prevent comment-based evasion
    query_no_comments = re.sub(r'--.*?$|/\*.*?\*/', ' ', query, flags=re.MULTILINE | re.DOTALL)
    
    # Normalize whitespace
    normalized_query = ' '.join(query_no_comments.split())
    
    # Convert to uppercase for easier checking
    query_upper = normalized_query.strip().upper()
    
    # Check if the query starts with SELECT
    if not query_upper.startswith("SELECT"):
        return False, "Only SELECT queries are allowed for security reasons"
    
    # Check for dangerous operations and SQL keywords
    dangerous_keywords = [
        "DROP", "DELETE", "UPDATE", "INSERT", "ALTER", "CREATE", 
        "TRUNCATE", "GRANT", "REVOKE", "ATTACH", "DETACH", "PRAGMA",
        "UNION", "INTO OUTFILE", "LOAD_FILE", "EXECUTE", "EXEC",
        "--", "/*", "*/", ";"
    ]
    
    for keyword in dangerous_keywords:
        pattern = r'\b' + re.escape(keyword) + r'\b'
        if re.search(pattern, query_upper):
            return False, f"Potentially harmful operation detected: {keyword}"
    
    # Check for multiple statements (using semicolons)
    if ";" in query_upper[:-1]:  # Allow semicolon at the end
        return False, "Multiple SQL statements are not allowed"
    
    # Advanced checks for SQL injection attempts
    if query_upper.count("SELECT") > 1:
        # This might be a union-based injection or subquery
        if "UNION" in query_upper:
            return False, "UNION operations are not allowed"
    
    return True, ""

def execute_sql_query(query):
    try:
        # Validate the SQL query first
        is_valid, validation_message = validate_sql_query(query)
        
        if not is_valid:
            st.error(f"SQL validation failed: {validation_message}")
            return None
        
        # Final safety check before execution
        if not query.lstrip().upper().startswith("SELECT"):
            raise sqlite3.Error("Only SELECT queries are allowed for security reasons")
        
        # Execute the query only if it's valid
        cursor.execute(query)
        results = cursor.fetchall()
        return results
    except sqlite3.Error as e:
        # Use a generic error message instead of exposing the raw error
        st.error("An error occurred while executing the SQL query. Please check your query syntax or contact the administrator.")
        return None

def main():
    st.title("Backlog Requirements and SQL Queries")

    requirement = st.selectbox("Select a backlog requirement", backlog_requirements)

    generated_query = generate_sql_query(requirement)
    st.write("Generated SQL Query:")
    st.code(generated_query, language="sql")

    improved_query = improve_sql_query(generated_query)
    st.write("Improved SQL Query:")
    st.code(improved_query, language="sql")

    # Validate the SQL query before showing the execute button
    is_valid, error_message = validate_sql_query(improved_query)
    
    if not is_valid:
        st.error(f"SQL validation failed: {error_message}")
        st.warning("Query execution prevented due to security concerns.")
    else:
        if st.button("Execute Query"):
            results = execute_sql_query(improved_query)
            if results:
                st.write("Query Results:")
                st.dataframe(results)
            else:
                st.warning("Query execution failed.")

if __name__ == "__main__":
    main()