import os
from pathlib import Path
from typing import List, Dict, Tuple

def get_prompts_dir() -> Path:
    return Path(__file__).parent.parent / 'prompts'

def load_system_prompt() -> str:
    prompt_path = get_prompts_dir() / 'system_prompt.md'
    try:
        return prompt_path.read_text(encoding='utf-8')
    except Exception as e:
        print(f"Error loading system prompt from {prompt_path}: {e}")
        return ""

def load_user_prompt(files: List[Dict], context: str = "") -> str:
    prompt_path = get_prompts_dir() / 'user_prompt.md'
    try:
        template = prompt_path.read_text(encoding='utf-8')
        
        files_section = "\n\n".join([
            f"File: {f['name']}\n```\n{f['content']}\n```"
            for f in files
        ])
        
        return template.format(
            context=context if context else 'General code review',
            files_section=files_section
        )
    except Exception as e:
        print(f"Error loading user prompt from {prompt_path}: {e}")
        return ""

def build_prompt(files: List[Dict], context: str = "") -> Tuple[str, str]:
    """Build the system and user prompts for code review"""
    return load_system_prompt(), load_user_prompt(files, context)
