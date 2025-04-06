# -*- coding: utf-8 -*-
"""
Refactored on Friday Jan 7 13:23:39 2025
# Text2SQL LLM Agentic Tool based approach to Optimize the SQL Queries for Application Health Monitoring
@author: Akram Sheriff
"""
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import ConfigurableField
from langchain_core.tools import tool
from langchain.agents import create_tool_calling_agent, AgentExecutor
from openai import OpenAI
import os, sys
import sqlite3
import streamlit as st
from langchain_community.utilities import SQLDatabase
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
import openai

# Increase recursion limit (temporary solution)
sys.setrecursionlimit(10000)

os.environ["OPENAI_API_KEY"] = ""

# Set up OpenAI API key
OPENAI_API_KEY = ""
client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

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
        ("system", "you're a helpful assistant"),
        ("human", "{input}"),
        ("placeholder", "{agent_scratchpad}"),
    ]
)

def is_potentially_harmful_sql(sql_query):
    """
    Check if the SQL query contains potentially harmful operations.
    
    Args:
        sql_query (str): SQL query to check
        
    Returns:
        bool: True if potentially harmful, False otherwise
    """
    if not sql_query:
        return False
        
    # Convert to lowercase for easier matching
    sql_lower = sql_query.lower()
    
    # Check for dangerous operations
    dangerous_patterns = [
        "drop table", "drop database", "truncate table",
        "delete from", "update", "insert into",  # These need WHERE clauses
        "alter table", "create trigger", "execute",
        "exec", "xp_", "sp_", "--", "/*", ";--",
        "1=1", "or 1=1", "or '1'='1'",
        "union select", "information_schema", "concat("
    ]
    
    # First pass: check for definitely harmful patterns
    for pattern in ["drop", "truncate", "--", ";--", "/*", "union"]:
        if pattern in sql_lower:
            return True
    
    # Second pass: check DELETE/UPDATE without WHERE (simplified check)
    if "delete from" in sql_lower and "where" not in sql_lower:
        return True
    if "update " in sql_lower and "where" not in sql_lower:
        return True
    
    # Check for other dangerous patterns
    for pattern in dangerous_patterns:
        if pattern in sql_lower:
            # Allow reads (SELECT statements) for specified tables
            if pattern == "information_schema" and "select" in sql_lower:
                continue
            if (pattern == "insert into" or pattern == "update" or pattern == "delete from") and "where" in sql_lower:
                continue
            return True
    
    return False

# Define the Agentic SQL tool to detect poorly written SQL queries
@tool
def detect_and_improve_sql(requirement):
    """
    Detects poorly written SQL queries in the input, identifies their issues, and provides improvements.

    Args:
        requirement (str): SQL query or description of the problem

    Returns:
        str: Analysis including original query, identified issues, and improved query
    """
    # Input validation
    if not requirement or len(requirement.strip()) == 0:
        return "Error: Empty input provided"
    
    # Check input for potentially harmful content
    if ";" in requirement and ("--" in requirement or "/*" in requirement):
        return "Error: Potentially harmful input detected"
    
    # Enhanced system prompt with safety guidelines
    system_prompt = """You are an SQL expert tasked with improving SQL queries. 
    
    IMPORTANT SAFETY RULES:
    1. Never generate SQL that could be harmful to a database
    2. Never include DROP, TRUNCATE, or DELETE without proper WHERE clauses
    3. Do not include any data modification statements (INSERT, UPDATE, DELETE) unless explicitly required
    4. Always validate inputs and use parameterized queries when applicable
    5. Never include SQL commands that could bypass access controls
    
    Analyze the provided SQL query or requirement, detect any issues, and provide improvements."""
    
    user_prompt = f"""Analyze the following SQL query or requirement, detect any issues, and improve it:

Requirement:
{requirement}

Respond with three clearly labeled sections:
1. Original Query: (The provided query or your interpretation of what is needed)
2. Issues: (List any issues, inefficiencies, or problems with the original)
3. Improved Query: (Your improved version with better performance, readability, and security)"""
    
    try:
        response = client.chat.completions.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            max_tokens=500,
            temperature=0.0
        )
        
        output_text = response.choices[0].message.content.strip()
        
        # Extract the improved SQL query to check if it's safe
        improved_query = ""
        capture_improved = False
        for line in output_text.split('\n'):
            if "improved query" in line.lower() or "improved sql" in line.lower():
                capture_improved = True
                continue
            if capture_improved:
                improved_query += line + "\n"
        
        improved_query = improved_query.strip()
        
        # Check if the improved query is potentially harmful
        if improved_query and is_potentially_harmful_sql(improved_query):
            return "Error: The improved SQL query contains potentially harmful operations. Query generation aborted."
            
        return output_text
            
    except Exception as e:
        print(f"Error detecting and improving SQL query: {e}")
        return f"Error: {str(e)}"

# Define the Agentic SQL tool for generating queries
@tool
def generate_sql_query(requirement):
    """
       Generates a SQL query based on the given natural language requirement with security validations.
       Args:
           requirement (str): Natural language description of the desired SQL query
       Returns:
           str: Generated SQL query based on the requirement
    """
    # Input validation
    if not requirement or len(requirement.strip()) == 0:
        return "Error: Empty input provided"
    
    # Check input for potentially harmful content
    if ";" in requirement and ("--" in requirement or "/*" in requirement):
        return "Error: Potentially harmful input detected"
    
    # Enhanced system prompt with safety guidelines
    system_prompt = """You are a SQL security expert. Generate only secure SQL queries that cannot harm database integrity. By default, generate only SELECT queries unless data modification is explicitly requested. Always include strong WHERE clauses and appropriate limits."""
    
    user_prompt = f"""Generate a secure SQL query for this requirement: {requirement}

Return ONLY the SQL query with no additional text."""
    
    try:
        response = client.chat.completions.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            max_tokens=300,
            temperature=0.0
        )
        
        generated_query = response.choices[0].message.content.strip()
        
        # Additional validation step
        validation_response = client.chat.completions.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "You are a SQL security validator with a focus on preventing injection and database corruption."},
                {"role": "user", "content": f"Validate if this SQL query is secure and meets the requirement. If it's safe, respond with 'SAFE'. If it's not safe, respond with 'UNSAFE'.

Requirement: {requirement}

Query: {generated_query}"},
            ],
            max_tokens=50,
            temperature=0.0
        )
        
        if "UNSAFE" in validation_response.choices[0].message.content.upper():
            return "Error: Generated query failed security validation."
        
        return generated_query
    except Exception as e:
        print(f"Error generating SQL query: {e}")
        return f"Error: Failed to generate SQL query: {str(e)}"

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
    # Initialize cursor to None for the finally block
    cursor = None
    
    try:
        # Trim the query and remove ending semicolon if present
        query = query.strip()
        if query.endswith(';'):
            query = query[:-1]
            
        # Basic validation to prevent multiple SQL statements
        if ";" in query:
            print("Error: Multiple SQL statements are not allowed.")
            return None
            
        # Check if query appears to be a data modification query
        query_lower = query.lower().strip()
        if (query_lower.startswith("insert") or 
            query_lower.startswith("update") or 
            query_lower.startswith("delete") or 
            query_lower.startswith("drop") or 
            query_lower.startswith("alter") or 
            query_lower.startswith("create")):
            print("Error: Only SELECT queries are allowed.")
            return None
            
        cursor = conn.cursor()
        
        # Execute the validated query
        cursor.execute(query)
        results = cursor.fetchall()
        return results
    except sqlite3.Error as e:
        print(f"Error executing SQL query: {e}")
        return None
    finally:
        if cursor:
            cursor.close()

# Create a list of AI Agent or LLM Agent tools
tools = [generate_sql_query, detect_and_improve_sql, execute_sql_query]

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