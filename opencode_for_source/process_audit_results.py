import json
import os
import pandas as pd
from pathlib import Path
import re

def extract_audit_results_from_file(file_path):
    """从单个JSON文件中提取audit_result数据"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        audit_result = data.get('audit_result', [])
        
        if isinstance(audit_result, str):
            json_match = re.search(r'```json\s*(\[.*?\])\s*```', audit_result, re.DOTALL)
            if json_match:
                audit_result = json.loads(json_match.group(1))
            else:
                json_match = re.search(r'(\[.*?\])', audit_result, re.DOTALL)
                if json_match:
                    audit_result = json.loads(json_match.group(1))
                else:
                    return []
        
        if not isinstance(audit_result, list):
            return []
        
        results = []
        for item in audit_result:
            row = {
                'git_url': data.get('git_url', ''),
                'branch_name': data.get('branch_name', ''),
                'session_id': data.get('session_id', ''),
                'session_title': data.get('session_title', ''),
                'timestamp': data.get('timestamp', ''),
                'annotation': item.get('annotation', ''),
                'language': item.get('language', ''),
                'application_type': item.get('application_type', ''),
                'project_description': item.get('project_description', ''),
                'project_name': item.get('project_name', ''),
                'git_addr': item.get('git_addr', ''),
                'branch': item.get('branch', '')
            }
            results.append(row)
        
        return results
    except Exception as e:
        print(f"处理文件 {file_path} 时出错: {e}")
        return []

def process_audit_results_directory(directory_path, output_excel_path):
    """处理audit_results目录中的所有JSON文件，生成Excel"""
    directory = Path(directory_path)
    all_results = []
    
    json_files = list(directory.glob('*.json'))
    print(f"找到 {len(json_files)} 个JSON文件")
    
    for json_file in json_files:
        results = extract_audit_results_from_file(json_file)
        all_results.extend(results)
        print(f"处理 {json_file.name}: 提取了 {len(results)} 条记录")
    
    if not all_results:
        print("没有提取到任何数据")
        return
    
    df = pd.DataFrame(all_results)
    df.to_excel(output_excel_path, index=False, engine='openpyxl')
    print(f"成功生成Excel文件: {output_excel_path}")
    print(f"总共 {len(all_results)} 条记录")

if __name__ == '__main__':
    audit_results_dir = Path(__file__).parent / 'audit_results'
    output_file = Path(__file__).parent / 'audit_results.xlsx'
    
    process_audit_results_directory(audit_results_dir, output_file)
