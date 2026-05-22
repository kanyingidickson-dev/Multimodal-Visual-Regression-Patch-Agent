"""
Demo script for Contextual Code Review Assistant
Tests the reviewer with sample code from the project
"""

import os
import json
from dotenv import load_dotenv
load_dotenv()
from code_reviewer import CodeReviewer


import asyncio

async def main():
    print("=" * 60)
    print("Contextual Code Review Assistant - Demo")
    print("=" * 60)
    print()
    
    # Initialize reviewer
    try:
        reviewer = CodeReviewer()
        model_name = os.getenv('MODEL_CHOICE', 'gemma-4-31b')
        print(f"✓ Initialized with model: {model_name}")
        print(f"✓ Using API: {'OpenRouter' if reviewer.client.use_openrouter else 'Hugging Face'}")
        print()
    except Exception as e:
        print(f"✗ Failed to initialize: {e}")
        print("Please set OPENROUTER_API_KEY or HUGGINGFACE_API_KEY in .env")
        return
    
    # Review the project's own code
    files_to_review = [
        'app.py',
        'code_reviewer.py'
    ]
    
    # Add backend prefix if running from root
    existing_files = []
    for f in files_to_review:
        if os.path.exists(f):
            existing_files.append(f)
        elif os.path.exists(os.path.join('backend', f)):
            existing_files.append(os.path.join('backend', f))
    
    if not existing_files:
        print("✗ No files found to review")
        return
    
    print(f"Reviewing files: {', '.join(existing_files)}")
    print("Context: General code review - check for bugs, security issues, and improvements")
    print()
    print("-" * 60)
    print("Calling Gemma 4...")
    print("-" * 60)
    print()
    
    try:
        result = await reviewer.review_files(
            file_paths=existing_files,
            context="General code review - check for bugs, security issues, and improvements"
        )
        
        print("✓ Review complete!")
        print()
        print("=" * 60)
        print("SUMMARY")
        print("=" * 60)
        print(result.get('summary', 'No summary provided'))
        print()
        
        print("=" * 60)
        print("CONFIDENCE LEVEL")
        print("=" * 60)
        print(result.get('confidence', 'Not provided').upper())
        print()

        print("=" * 60)
        print("ROOT CAUSE")
        print("=" * 60)
        print(result.get('root_cause', 'No root cause provided'))
        print()
        
        print("=" * 60)
        print("FIX PLAN")
        print("=" * 60)
        if result.get('fix_plan'):
            for i, step in enumerate(result['fix_plan'], 1):
                print(f"{i}. {step}")
        else:
            print("No steps provided")
        print()

        print("=" * 60)
        print("ASSUMPTIONS")
        print("=" * 60)
        if result.get('assumptions'):
            for i, assumption in enumerate(result['assumptions'], 1):
                print(f"{i}. {assumption}")
        else:
            print("No assumptions")
        print()
        
        if result.get('patch'):
            print("=" * 60)
            print("GENERATED PATCH")
            print("=" * 60)
            print(result['patch'])
            print()
        
        # Save results to file
        with open('demo_results.json', 'w') as f:
            json.dump(result, f, indent=2)
        print("✓ Results saved to demo_results.json")
        
    except Exception as e:
        print(f"✗ Error during review: {e}")
        import traceback
        traceback.print_exc()


if __name__ == '__main__':
    asyncio.run(main())
