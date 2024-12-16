#pip install requests pandas seaborn matplotlib python-dotenv chardet
import requests
import pandas as pd
import os
import sys
import chardet
from dotenv import load_dotenv
import json
import matplotlib.pyplot as plt
import seaborn as sns
import traceback
import io
import itertools


# Load environment variables from .env file
load_dotenv()
AIPROXY_TOKEN = os.getenv("AIPROXY_TOKEN")

# Define the AI Proxy URL and model
url = "https://aiproxy.sanand.workers.dev/openai/v1/chat/completions"
model = "gpt-4o-mini"
headers = {"Content-Type": "application/json", "Authorization": f"Bearer {AIPROXY_TOKEN}"}

# Function to read and process CSV file
def load_dataset(file_path):
    with open(file_path, 'rb') as f:
        result = chardet.detect(f.read())  # Detect file encoding
    df = pd.read_csv(file_path, encoding=result['encoding'])
    return df.dropna()  # Drop rows with missing values

# Function to calculate correlations and generate summary data
def calculate_correlations(df):
    numeric_columns = df.select_dtypes(include=['float64', 'int64']).columns
    column_combinations = itertools.combinations(numeric_columns, 2)

    max_corr = -1
    second_max_corr = -1
    data = {}

    for col1, col2 in column_combinations:
        correlation = df[[col1, col2]].corr().iloc[0, 1]
        if correlation > max_corr:
            max_corr = correlation
            max_corr_pair = (col1, col2)
            data[col1] = json.loads(df.describe()[col1].to_json())
            data[col2] = json.loads(df.describe()[col2].to_json())

        if correlation > second_max_corr and correlation < max_corr:
            second_max_corr_pair = (col1, col2)
            data[col1] = json.loads(df.describe()[col1].to_json())
            data[col2] = json.loads(df.describe()[col2].to_json())

    return max_corr_pair, second_max_corr_pair, data

# Function to send a request to the AI model and handle the response
def get_ai_response(data, content, function_name):
    json_data = {
        "model": model,
        "messages": [
            {"role": "system", "content": content},
            {"role": "system", "content": json.dumps(data)}
        ],
        "functions": [{
            "name": function_name,
            "description": "Analyzes correlations between columns",
            "parameters": {
                "type": "object",
                "properties": {
                    "is_columns_common": {"type": "boolean", "description": "Are columns similar?"},
                    "reason": {"type": "string", "description": "Explanation for the correlation behavior"}
                },
                "required": ["is_columns_common", "reason"]
            }
        }],
        "function_call": {"name": function_name}
    }

    response = requests.post(url=url, headers=headers, json=json_data)
    return response.json()

# Function to generate Python code and a README for visualization and insights
def generate_code_and_readme(data, folder_name, instructions):
    json_data = {
        "model": model,
        "messages": [
            {"role": "system", "content": instructions},
            {"role": "system", "content": json.dumps(data)}
        ],
        "functions": [{
            "name": "generate_appropriate_chart_and_readme",
            "description": "Generates python code to create charts and README file",
            "parameters": {
                "type": "object",
                "properties": {
                    "python_code": {"type": "string", "description": "Python code for visualization"},
                    "folder": {"type": "object", "properties": {
                        "contents": [{"type": "file", "name": "*.png"}, {"type": "file", "name": "README.md"}]
                    }},
                    "chart_name": {"type": "string", "description": "Name of the generated chart"},
                    "readme_file_summary": {"type": "string", "description": "Content for the README file"}
                },
                "required": ["folder", "python_code", "chart_name", "readme_file_summary"]
            }
        }],
        "function_call": {"name": "generate_appropriate_chart_and_readme"}
    }

    response = requests.post(url=url, headers=headers, json=json_data)
    return response.json()

# Function to handle error responses and retry
def handle_errors(code, error, retry_limit=3):
    for attempt in range(retry_limit):
        try:
            print("Attempt:", attempt + 1)
            r = get_ai_response(code, error, "generate_appropriate_chart_and_readme")
            print("Response:", r.json())
            return r.json()
        except Exception as e:
            error_message = traceback.format_exc()
            print("Error occurred:", error_message)
            if attempt == retry_limit - 1:
                print("Max retries reached. Exiting.")
                break

# Function to generate and save plots
def generate_charts(df, folder_name):
    # Save charts for the top 2 correlated columns
    chart_file_paths = []
    max_corr_pair, second_max_corr_pair, _ = calculate_correlations(df)
    
    for pair in [max_corr_pair, second_max_corr_pair]:
        if pair:
            col1, col2 = pair
            plt.figure(figsize=(6, 4))
            sns.regplot(x=col1, y=col2, data=df, scatter_kws={'s': 10}, line_kws={'color': 'red'})
            chart_name = f"{folder_name}_{col1}_{col2}.png"
            chart_file_paths.append(chart_name)
            plt.savefig(chart_name, dpi=300)
            plt.close()
    return chart_file_paths

# Main function to drive the entire process
def main(file_path):
    df = load_dataset(file_path)
    max_corr_pair, second_max_corr_pair, data = calculate_correlations(df)
    
    # Content for AI model based on correlation analysis
    content = (
        f"Dataset: {file_path}\n"
        f"Columns: {df.columns}\n"
        "Based on the column summaries, determine if the two most correlated columns have common features. "
        "Also, explain why they might or might not be correlated, and if common columns exist, consider if "
        "they could be output values."
    )

    # Get response from AI about correlation analysis
    ai_response = get_ai_response(data, content, "correlation")
    print("AI Response for correlation analysis:", ai_response)

    # Generate charts and save them
    folder_name = os.path.splitext(file_path)[0]
    chart_file_paths = generate_charts(df, folder_name)

    # Write a README.md file with insights
    readme_content = f"# Data Analysis Report for {file_path}\n\n"
    readme_content += "## Insights\n\nThe top two correlated columns are analyzed and visualized below:\n\n"
    for chart_path in chart_file_paths:
        readme_content += f"![Chart]({chart_path})\n"
    readme_content += "\n### Summary of Analysis:\n" + json.dumps(ai_response, indent=2)

    with open(f"{folder_name}/README.md", "w") as f:
        f.write(readme_content)

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: uv run autolysis.py dataset.csv")
    else:
        main(sys.argv[1])
