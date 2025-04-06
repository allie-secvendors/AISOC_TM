# -*- coding: utf-8 -*-
"""
Created on Friday Jan 3 13:23:39 2025
# Text2SQL LLM Agentic Tool based approach to Optimize the SQL Queries for Application Health Monitoring
@author: Akram Sheriff
"""
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import ConfigurableField
from pydantic import BaseModel
from langchain_core.tools import tool
from langchain.agents import create_tool_calling_agent, AgentExecutor
from openai import OpenAI
import os,sys
import sqlite3
import streamlit as st
from langchain_community.utilities import SQLDatabase
from langchain_openai import ChatOpenAI
import openai
import re

from pydantic import BaseModel, Field
from typing import Dict, List, Optional, Any
from langchain_openai import ChatOpenAI
from langchain.agents import create_tool_calling_agent, AgentExecutor , tool
from langchain_core.tools import tool

# Increase recursion limit (temporary solution)
sys.setrecursionlimit(10000)

os.environ["OPENAI_API_KEY"]=""
# Set up OpenAI API key
OPENAI_API_KEY=""

client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

db_directory = "/Users/akram_personal/"
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

def validate_sql_query(sql_query):
    """
    Validates SQL query for potentially dangerous operations.
    
    Args:
        sql_query (str): SQL query to validate
    
    Returns:
        tuple: (is_safe, message) where is_safe is a boolean and message contains validation details
    """
    if not sql_query or not isinstance(sql_query, str):
        return False, "Empty or invalid SQL query"
    
    # Convert to lowercase for case-insensitive matching
    sql_lower = sql_query.lower()
    
    # Check for dangerous SQL operations
    dangerous_patterns = [
        (r'\bdrop\b', "DROP operation detected"),
        (r'\bdelete\b(?!.*\bwhere\b)', "DELETE without WHERE clause"),
        (r'\btruncate\b', "TRUNCATE operation detected"),
        (r'\balter\b', "ALTER operation detected"),
        (r'\bcreate\s+user\b', "User creation operation detected"),
        (r'\bgrant\b', "GRANT permission operation detected"),
        (r'\binto\s+outfile\b', "File system write operation detected"),
        (r'\bload_file\b', "File system read operation detected"),
        (r'\bexec\b|\bexecute\b', "Command execution detected"),
        (r'\bsys\b|\bsystem\b', "System function detected"),
        (r';(?!\s*$)', "Multiple SQL statements detected"),
        (r'\bupdate\b(?!.*\bwhere\b)', "UPDATE without WHERE clause"),
        (r'--', "SQL comment detected"),
        (r'/\*', "SQL comment block detected")
    ]
    
    for pattern, message in dangerous_patterns:
        if re.search(pattern, sql_lower):
            return False, message
    
    # Additional security checks can be added here
    
    return True, "SQL query passed validation"

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
    # Enhanced prompt with security guidelines
    prompt = f"""You are an expert SQL developer. Convert the following requirement into a well-written SQL query.
    
SECURITY GUIDELINES:
1. Only write SELECT statements that read data - no modification operations
2. Do not use any destructive operations (DROP, DELETE, UPDATE, ALTER, TRUNCATE)
3. Do not use multiple SQL statements (no semicolons except at the end)
4. Avoid system tables, stored procedures, or sensitive system information
5. Write queries that are appropriate for a monitoring/analysis context

Requirement:
{requirement}

SQL Query:"""
    try:
        response = client.chat.completions.create(model="gpt-4",
        messages=[{"role": "system", "content": "You are an expert AI assistant focused on secure SQL generation."},
                  {"role": "user", "content": prompt}],
        max_tokens=300,
        temperature=0.0)
        
        generated_sql = response.choices[0].message.content.strip()
        
        # Validate the generated SQL
        is_safe, reason = validate_sql_query(generated_sql)
        
        if not is_safe:
            print(f"Warning: Potentially unsafe SQL generated: {reason}")
            
            # Try to generate a safer version
            safe_prompt = f"""The previously generated SQL query was flagged as potentially unsafe: {reason}
            
Please rewrite the query following these strict security guidelines:
1. Use ONLY SELECT statements for read-only operations
2. Do not use any data modification operations
3. Focus solely on data retrieval and analysis
4. Avoid any system tables or procedures

Original requirement: {requirement}

Safe SQL Query:"""
            
            safe_response = client.chat.completions.create(model="gpt-4",
            messages=[{"role": "system", "content": "You are a security-focused SQL expert."},
                      {"role": "user", "content": safe_prompt}],
            max_tokens=300,
            temperature=0.0)
            
            safe_sql = safe_response.choices[0].message.content.strip()
            
            # Re-validate the new query
            is_safe_now, new_reason = validate_sql_query(safe_sql)
            
            if is_safe_now:
                return f"-- Note: Original query was modified for security reasons.\n{safe_sql}"
            else:
                return f"-- ERROR: Unable to generate a safe SQL query.\n-- Reason: {new_reason}\n-- Please refine your requirement to focus on data retrieval only."
        
        return generated_sql
        
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
        
        improved_sql = response.choices[0].message.content.strip()
        
        # Validate the improved SQL for safety
        is_safe, reason = validate_sql_query(improved_sql)
        if not is_safe:
            print(f"Warning: Improved SQL contains unsafe elements: {reason}")
            return f"-- Warning: The improved query contains unsafe elements. Using original query instead.\n-- Reason: {reason}\n{query}"
            
        return improved_sql
    except Exception as e:
        print(f"Error improving SQL query: {e}")
        return None


# Define the SQL tool for query execution
@tool
def execute_sql_query(query, conn):
    """
    Executes a SQL query on the given database connection and returns the results.
    Validates the query for security before execution.

    Args:
        query (str): The SQL query to execute
        conn: Database connection object

    Returns:
        list: Results of the query if successful
        None: If query execution fails

    Raises:
        sqlite3.Error: If there's an error during query execution
    """
    # Validate query before execution
    is_safe, reason = validate_sql_query(query)
    if not is_safe:
        print(f"Error: Cannot execute potentially unsafe SQL. Reason: {reason}")
        return f"Error: Cannot execute potentially unsafe SQL. Reason: {reason}"
        
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
    st.title("Automated SQL Query generation(variant agnostic) with LLM based Agentic Approach")

    requirement = st.selectbox("Select a Product Backlog requirement for which SQL has to be generated", backlog_requirements)

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