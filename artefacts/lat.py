# -*- coding: utf-8 -*-
"""
Created on Friday Jan 3 13:23:39 2025
# Text2SQL LLM Agentic Tool based approach to Optimize the SQL Queries for Application Health Monitoring
@author: Akram Sheriff
"""
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import ConfigurableField
from langchain_core.tools import tool
from langchain.agents import create_tool_calling_agent, AgentExecutor
import openai
from openai import OpenAI
import sys

from langchain_openai import ChatOpenAI
from typing import Dict, List, Optional, Any

# Temporary increase of recursion limit
sys.setrecursionlimit(10000)

client = OpenAI(api_key="")
import os
import sqlite3
import streamlit as st
from langchain_community.utilities import SQLDatabase

# Set up OpenAI API key

db_directory = "/Users/akram/Desktop/TM"
db_path = os.path.join(db_directory, "database.db")

# Ensure the directory exists
os.makedirs(db_directory, exist_ok=True)

# Create and initialize the database
if not os.path.exists(db_path):
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Create a sample table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS sample_table (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT
            )
        """)

        # Insert some sample data
        cursor.execute("""
            INSERT INTO sample_table (name, description)
            VALUES ('Test Item', 'This is a test description')
        """)

        conn.commit()
        conn.close()
        print("Database initialized with sample table")
    except Exception as e:
        print(f"Error initializing database: {e}")
        raise

try:
    # Connect using SQLDatabase
    db_uri = f"sqlite:///{db_path}"
    db = SQLDatabase.from_uri(db_uri)
    print("Successfully connected to the database")
    print(f"Dialect: {db.dialect}")
    print(f"Available tables: {db.get_usable_table_names()}")

except Exception as e:
    print(f"Error connecting to database: {e}")


prompt = ChatPromptTemplate.from_messages(
    [
        ("system", "you're a helpful AI assistant"),
        ("human", "{input}"),
        ("placeholder", "{agent_scratchpad}"),
    ]
)

def validate_sql_query(query):
    """
    Validates a SQL query for potentially malicious operations.
    
    Args:
        query (str): The SQL query to validate
        
    Returns:
        tuple: (is_valid, message) where is_valid is a boolean indicating if the query is safe,
               and message provides details if the query is not safe
    """
    if not query or not isinstance(query, str):
        return False, "Query must be a non-empty string"
    
    # Convert to uppercase for easier pattern matching
    upper_query = query.upper()
    
    # Define patterns for dangerous operations
    dangerous_patterns = [
        "DROP ", "TRUNCATE ", "ALTER ", 
        "GRANT ", "REVOKE ", "EXEC ", "EXECUTE ",
        "CREATE USER", "DROP USER", 
        "PRAGMA", "ATTACH", "DETACH",
        ";", "--", "/*", "*/"  # SQL injection patterns
    ]
    
    # Check for dangerous patterns
    for pattern in dangerous_patterns:
        if pattern in upper_query:
            return False, f"Query contains potentially dangerous operation: {pattern}"
    
    # For this monitoring application, we primarily allow SELECT queries
    # We conditionally allow CREATE TABLE/VIEW for setting up monitoring structures
    allowed_starts = ["SELECT ", "CREATE TABLE ", "CREATE VIEW "]
    
    valid_start = False
    for start in allowed_starts:
        if upper_query.strip().startswith(start):
            valid_start = True
            break
    
    if not valid_start:
        return False, "Query must start with SELECT or specific CREATE operations for monitoring purposes"
    
    return True, "Query is valid"

# Define the Agentic  SQL tool using the @tool decorator - To generate SQL
@tool
def generate_sql_query(requirement):
    """
       Generates a SQL query based on the given natural language requirement.
       Args:
           requirement (str): Natural language description of the desired SQL query
       Returns:
           str: Generated SQL query based on the requirement
    """
    prompt = f"""You are an expert SQL developer. Convert the following requirement into a well-written SQL query.
    Focus on creating safe, efficient queries for monitoring purposes. 
    ONLY generate SELECT queries or CREATE TABLE/VIEW statements for monitoring.
    NEVER include dangerous operations like DROP, TRUNCATE, ALTER, GRANT, REVOKE, or any operations 
    that could compromise database security.

{requirement}

SQL Query:"""
    try:
        response = client.chat.completions.create(model="gpt-4",
        messages=[{"role": "developer", "content": "You are an expert assistant."},
                  {"role": "user", "content": prompt}],
        max_tokens=300,
        temperature=0.5)
        
        generated_query = response.choices[0].message.content.strip()
        
        # Validate the generated query
        is_valid, message = validate_sql_query(generated_query)
        if not is_valid:
            return f"Error: Generated query is not safe. {message}"
        
        return generated_query
    except Exception as e:
        print(f"Error generating SQL query: {e}")
        return None

# Define the Agentic SQL tool for query improvement- Tom Improve SQL
@tool
def improve_sql_query(query):
    """
        Improves and optimizes the given SQL query for better performance and readability.
        Args:
            query (str): The original SQL query that needs optimization
        Returns:
            str: An optimized version of the input SQL query with improved performance and readability
    """
    prompt = f"""You are an SQL optimization expert. Improve the following SQL query for readability, efficiency, and performance:

{query}

Improved SQL Query:"""
    try:
        response = client.chat.completions.create(model="gpt-4",
        messages=[{"role": "system", "content": "You are an expert assistant."},
                  {"role": "user", "content": prompt}],
        max_tokens=300,
        temperature=0.5)
        improved_query = response.choices[0].message.content.strip()
        
        # Validate the improved query
        is_valid, message = validate_sql_query(improved_query)
        if not is_valid:
            return f"Error: Improved query is not safe. {message}"
            
        return improved_query
    except Exception as e:
        print(f"Error improving SQL query: {e}")
        return query  # Return original query in case of error


# Define the SQL tool for query execution
@tool
def execute_sql_query(query, conn):
    """
    Executes a SQL query on the given database connection and returns the results.

    Args:
        query (str): The SQL query to execute
        conn: Database connection object

    Returns:
        list: Results of the query if successful
        None: If query execution fails

    Raises:
        sqlite3.Error: If there's an error during query execution
    """
    # Validate the query before execution
    is_valid, message = validate_sql_query(query)
    if not is_valid:
        print(f"Error: {message}")
        return None
        
    cursor = None
    try:
        cursor = conn.cursor()
        cursor.execute(query)
        results = cursor.fetchall()
        return results
    except sqlite3.Error as e:
        print(f"Error executing SQL query: {e}")
        return None
    finally:
        if cursor:
            cursor.close()

# Create a list of AI  Agent or LLM  Agent tools
tools = [generate_sql_query, improve_sql_query, execute_sql_query]

llm = ChatOpenAI(model="gpt-4", openai_api_key=OPENAI_API_KEY, temperature=0)

# Create the agent
agent = create_tool_calling_agent(llm, tools, prompt)

# Create the agent executor
agent_executor = AgentExecutor(
    agent=agent, tools=tools, handle_parsing_errors=True, verbose=True
)

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# Backlog requirements
backlog_requirements = [
    "Create a query to alert when any API endpoint experiences a 50% increase in average response time compared to the previous hour's baseline.",
    "Users have reported unusual account activity. Create monitoring to detect anomalous user session patterns that could indicate account compromise. Consider factors like login frequency, concurrent sessions, and access patterns.",
    "Monitor for scenarios where error rates exceed 5% of total requests per endpoint while also having high response times (>2s) in the last 15 minutes.",
    "The application seems slow during peak hours. Create a query to help us understand what's causing it.",
    "Create proactive monitoring for resource utilization across our microservices. We need early warning when any service is trending towards capacity limits, considering historical usage patterns and growth rates."
]

def main():
    st.title("Product Backlog Requirements and SQL Queries")

    requirement = st.selectbox("Select a Product Backlog requirement", backlog_requirements)

    if requirement:
        try:
            # Call the agent executor with the selected requirement
            result = agent_executor.invoke(
                {"input": requirement},
                additional_context={"conn": conn}
            )
            # Process the result
            if "generated_query" in result:
                generated_query = result["generated_query"]
                st.write("Generated SQL Query:")
                st.code(generated_query, language="sql")

                if "improved_query" in result:
                    improved_query = result["improved_query"]
                    st.write("Improved SQL Query:")
                    st.code(improved_query, language="sql")

                    if st.button("Execute Query"):
                        results = result["query_results"]
                        if results:
                            st.write("Query Results:")
                            st.dataframe(results)
                        else:
                            st.warning("Query execution failed.")

        except openai.APIConnectionError as e:
            st.error("Failed to connect to the OpenAI API: " + str(e))

if __name__ == "__main__":
    main()