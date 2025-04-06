import streamlit as st
from openai import OpenAI
import sqlite3
import re  # Added for regex pattern matching in query validation
import os

# Get OpenAI API key from environment variable
api_key = os.environ.get("OPENAI_API_KEY")
if not api_key:
    st.error("OpenAI API key not found. Please set the OPENAI_API_KEY environment variable.")

# Create an OpenAI client
client = OpenAI(api_key=api_key)

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

# SQL queries
sql_queries = {
    "Alert on API endpoint response time increase": """
        SELECT endpoint, AVG(response_time) AS avg_response_time,
               AVG(response_time) / (SELECT AVG(response_time) FROM api_requests 
                                    WHERE timestamp >= DATE('now', '-1 hour')
                                    AND timestamp < DATE('now', '-30 minutes')) AS ratio
        FROM api_requests
        WHERE timestamp >= DATE('now', '-30 minutes')
        GROUP BY endpoint
        HAVING ratio > 1.5;
    """,
    "Anomaly detection for user sessions": """
        SELECT user_id, COUNT(*) AS total_sessions,
               COUNT(*) / (SELECT COUNT(*) FROM user_sessions 
                            WHERE start_time >= DATE('now', '-1 day')) AS ratio
        FROM user_sessions
        WHERE start_time >= DATE('now', '-1 day')
        GROUP BY user_id
        HAVING ratio > 0.1;
    """,
    "Error rate and response time anomalies": """
        SELECT endpoint, COUNT(*) AS total_requests,
               COUNT(*) / (SELECT COUNT(*) FROM api_requests 
                            WHERE timestamp >= DATE('now', '-15 minutes')) AS ratio,
               AVG(response_time) AS avg_response_time
        FROM api_requests
        WHERE timestamp >= DATE('now', '-15 minutes')
        GROUP BY endpoint
        HAVING ratio > 0.05 AND avg_response_time > 2;
    """,
    "Slow application monitoring": """
        SELECT endpoint, AVG(response_time) AS avg_response_time,
               COUNT(*) AS total_requests
        FROM api_requests
        WHERE timestamp >= DATE('now', '-1 hour')
        GROUP BY endpoint
        ORDER BY avg_response_time DESC
        LIMIT 10;
    """,
    "Resource utilization monitoring": """
        SELECT resource_type, server_id, current_usage, max_capacity,
               (current_usage / max_capacity * 100) AS usage_percentage
        FROM resource_utilization
        WHERE usage_percentage > 80
        ORDER BY usage_percentage DESC;
    """
}

def generate_sql_query(requirement):
    prompt = f"Convert the following requirement into a well-written SQL query:\n\n{requirement}\n\nSQL Query:"
    response = client.completions.create(
        model="text-davinci-002",
        prompt=prompt,
        max_tokens=200,
        n=1,
        stop=None,
        temperature=0.7
    )
    return response.choices[0].text.strip()

def improve_sql_query(query):
    prompt = f"Improve the following SQL query:\n\n{query}\n\nImproved SQL Query:"
    response = client.completions.create(
        model="text-davinci-002",
        prompt=prompt,
        max_tokens=200,
        n=1,
        stop=None,
        temperature=0.7
    )
    return response.choices[0].text.strip()

def is_read_only_query(query):
    """
    Determines if a query is read-only (safe for execution).
    """
    # Strip comments and whitespace for analysis
    query_clean = " ".join(query.lower().strip().split())
    
    # Check if query starts with SELECT and doesn't contain data modification keywords
    is_select = query_clean.startswith("select")
    
    # Some SELECT queries can still modify data (WITH ... UPDATE, etc.)
    # Check for data modification keywords outside of string literals
    modify_keywords = ["insert", "update", "delete", "drop", "alter", "truncate", "create", "grant", "revoke"]
    
    # Simple check for modification keywords (not perfect for complex queries)
    for keyword in modify_keywords:
        # Check if keyword appears as a whole word
        if re.search(r'\b' + keyword + r'\b', query_clean):
            return False
    
    return is_select

def validate_sql_query(query):
    """
    Validates a SQL query for potential security issues.
    Returns (is_valid, reason) tuple.
    """
    if not query or not isinstance(query, str):
        return False, "Invalid query format"
    
    # Check if query is read-only
    if not is_read_only_query(query):
        return False, "Only read-only SELECT queries are allowed"
    
    # Check for multiple statements (e.g., query; another_query)
    if ";" in query and not query.rstrip().endswith(";"):
        return False, "Multiple SQL statements are not allowed"
    
    # Check for common SQL injection patterns
    injection_patterns = [
        "--", "/*", "*/", 
        "union all select", "union select", 
        "or 1=1", "or 1 = 1", 
        "' or '", "\" or \"", 
        "'; --", "\"; --"
    ]
    
    query_lower = query.lower()
    for pattern in injection_patterns:
        if pattern in query_lower:
            return False, f"Potential SQL injection pattern detected: {pattern}"
    
    return True, "Query validated successfully"

def execute_sql_query(query):
    """
    Safely executes a validated SQL query.
    """
    # Validate the query first
    is_valid, reason = validate_sql_query(query)
    
    if not is_valid:
        st.error(f"SQL security validation failed: {reason}")
        return None
    
    try:
        # Execute the validated query
        cursor.execute(query)
        results = cursor.fetchall()
        return results
    except sqlite3.Error as e:
        st.error(f"Error executing SQL query: {e}")
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

    if st.button("Execute Query"):
        results = execute_sql_query(improved_query)
        if results:
            st.write("Query Results:")
            st.dataframe(results)
        else:
            st.warning("Query execution failed.")

if __name__ == "__main__":
    main()