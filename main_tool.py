import os
import sqlite3
import streamlit as st
import re
from typing import List, Dict, Tuple, Union
from langchain import SQLDatabase, FewShotPromptTemplate, PromptTemplate, LLMChain
from langchain.llms import OpenAI
from langchain.agents import initialize_agent
from langchain.tools import Tool

# OpenAI API Key Configuration
os.environ["OPENAI_API_KEY"] = ""

# Database Setup
DB_DIRECTORY = "/Users/akram/Desktop/TM"
DB_PATH = os.path.join(DB_DIRECTORY, "database.db")
os.makedirs(DB_DIRECTORY, exist_ok=True)

if not os.path.exists(DB_PATH):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sample_table (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT
        )
    """)
    cursor.execute("INSERT INTO sample_table (name, description) VALUES ('Test Item', 'Sample Description')")
    conn.commit()
    conn.close()
print("Database setup complete.")

# Connect to the database
db = SQLDatabase.from_uri(f"sqlite:///{DB_PATH}")

# Define LLM
llm = OpenAI(model="gpt-4", temperature=0)

# Define FewShotPromptTemplate for SQL Examples
examples = [
    {"input": "Get all items", "query": "SELECT * FROM sample_table;"},
    {"input": "Find item by name", "query": "SELECT * FROM sample_table WHERE name = 'Test Item';"}
]

prompt_template = FewShotPromptTemplate(
    examples=examples,
    example_prompt=PromptTemplate(
        input_variables=["input", "query"],
        template="Input: {input}\nQuery: {query}\n"
    ),
    prefix="You are a SQL expert. Convert the following inputs into SQL queries. Only generate simple read-only SELECT statements and avoid any complex operations. Never include DROP, DELETE, UPDATE, INSERT, CREATE, ALTER, or any other potentially harmful SQL operations:\n",
    suffix="\nInput: {input}\nQuery:",
    input_variables=["input"]
)

# SQL Query Validator
def validate_sql_query(query: str) -> Tuple[bool, str]:
    """
    Validates if the SQL query is safe to execute.
    Returns a tuple of (is_valid, reason).
    """
    if not query or not isinstance(query, str):
        return False, "Invalid query format"
        
    # Convert to lowercase for easier pattern matching
    query_lower = query.lower().strip()
    
    # Only allow SELECT statements
    if not query_lower.startswith("select"):
        return False, "Only SELECT queries are allowed."
    
    # Check for potentially dangerous SQL operations
    dangerous_patterns = [
        "drop", "delete", "update", "insert", "alter", "create", 
        "truncate", "exec", "execute", "union", "--", ";", "/*", "*/"
    ]
    
    for pattern in dangerous_patterns:
        if pattern in query_lower:
            return False, f"Potentially dangerous SQL pattern detected: {pattern}"
    
    # Validate that the query only targets our known tables
    allowed_tables = ["sample_table"]
    table_pattern = r"from\s+(\w+)"
    tables = re.findall(table_pattern, query_lower)
    
    for table in tables:
        if table not in allowed_tables:
            return False, f"Access to table '{table}' is not allowed."
    
    return True, "Query is valid."

# Safe SQL Execution
def safe_execute_sql(query: str) -> Union[List[Dict], Dict]:
    """
    Safely executes a validated SQL query.
    """
    # First validate the query
    is_valid, reason = validate_sql_query(query)
    if not is_valid:
        return {"error": reason}
    
    try:
        # Connect directly to SQLite for more control
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # Execute the query
        cursor.execute(query)
        
        # Fetch results
        rows = cursor.fetchall()
        results = [dict(row) for row in rows]
        
        conn.close()
        return results
    except Exception as e:
        return {"error": f"Error executing query: {str(e)}"}

# Define functions for tools
def generate_sql_query(requirement: str) -> str:
    """Generates SQL query from requirements."""
    generated = LLMChain(llm=llm, prompt=prompt_template).run(requirement)
    is_valid, _ = validate_sql_query(generated)
    if not is_valid:
        return "SELECT * FROM sample_table LIMIT 5;"
    return generated

def execute_sql_query(query: str) -> Union[List[Dict], Dict]:
    """Safely executes SQL query and returns results."""
    return safe_execute_sql(query)

def optimize_sql_query(query: str) -> str:
    """Optimizes SQL query for performance."""
    optimized = LLMChain(
        llm=llm,
        prompt=PromptTemplate(
            input_variables=["query"],
            template="You are an SQL optimization expert. Improve the following SQL query for performance, but do not change its semantic meaning or introduce any operations other than SELECT:\n\n{query}\n\nOptimized Query:"
        )
    ).run(query)
    
    # Validate optimized query
    is_valid, _ = validate_sql_query(optimized)
    if not is_valid:
        return query  # Return original if optimization made it unsafe
    
    return optimized

# Define tools correctly
generate_sql_query_tool = Tool(
    name="Generate SQL Query",
    func=lambda requirement: generate_sql_query(requirement),
    description="Generates SQL query from requirements."
)

execute_sql_query_tool = Tool(
    name="Execute SQL Query",
    func=lambda query: execute_sql_query(query),
    description="Executes SQL query and returns results."
)

optimize_sql_query_tool = Tool(
    name="Optimize SQL Query",
    func=lambda query: optimize_sql_query(query),
    description="Optimizes SQL query for performance."
)

# Initialize Agent
tools = [generate_sql_query_tool, execute_sql_query_tool, optimize_sql_query_tool]
agent = initialize_agent(tools=tools, llm=llm, verbose=True)

# Map requirements to safe SQL queries
SAFE_REQUIREMENT_MAPPING = {
    "Fetch all records from the table.": "SELECT * FROM sample_table;",
    "Find an item with a specific name.": "SELECT * FROM sample_table WHERE name = 'Test Item';",
    "Fetch records with a description containing 'Sample'.": "SELECT * FROM sample_table WHERE description LIKE '%Sample%';"
}

# Streamlit App
def main():
    st.title("Automated SQL Query Generation and Optimization")

    requirement = st.selectbox(
        "Select a Requirement",
        list(SAFE_REQUIREMENT_MAPPING.keys())
    )

    if requirement:
        st.write("Generating SQL Query...")
        
        # Use the safe mapping for requirements
        sql_query = SAFE_REQUIREMENT_MAPPING.get(requirement, "")
        
        if not sql_query:
            # Fallback to AI generation (with validation)
            generated_query = agent.run({"input": requirement})
            
            # Validate query before displaying
            is_valid, reason = validate_sql_query(generated_query)
            if not is_valid:
                st.error(f"Generated query is not valid: {reason}")
                sql_query = "SELECT * FROM sample_table LIMIT 5;"
            else:
                sql_query = generated_query
        
        st.code(sql_query, language="sql")

        if st.button("Optimize Query"):
            optimized_query = optimize_sql_query(sql_query)
            st.code(optimized_query, language="sql")

        if st.button("Execute Query"):
            results = execute_sql_query(sql_query)
            st.write(results)

if __name__ == "__main__":
    main()