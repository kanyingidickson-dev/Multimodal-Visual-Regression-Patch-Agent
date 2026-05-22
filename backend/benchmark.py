import os
import sys
import time
import json
import asyncio
import tempfile
import subprocess
from pathlib import Path
from typing import List, Dict, Any

# Add workspace and backend directories to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from code_reviewer import CodeReviewer
from patch_utils import PatchValidator, PatchApplicabilityChecker, ASTValidator, FileGroundingValidator

# 1x1 transparent PNG bytes for mock screenshots
TINY_PNG = b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4\x00\x00\x00\rIDATx\x9cc\xfc\xcf\xf0\x1f\x00\x04\x06\x02\x00\xa7\xbf/\x10\x00\x00\x00\x00IEND\xaeB`\x82'

BENCHMARK_CASES = [
    {
        "id": 1,
        "name": "CSS Overflow Bug",
        "filename": "overflow.css",
        "description": "Text overflows container bounds due to missing overflow control on single-line text.",
        "keywords": ["overflow", "ellipsis", "wrap", "nowrap"],
        "buggy_code": ".text-container {\n    width: 300px;\n    white-space: nowrap;\n}\n",
        "expected_code": ".text-container {\n    width: 300px;\n    white-space: nowrap;\n    overflow: hidden;\n    text-overflow: ellipsis;\n}\n"
    },
    {
        "id": 2,
        "name": "Z-Index Stacking Context",
        "filename": "stacking.css",
        "description": "Modal content is layered behind overlay due to lower relative z-index.",
        "keywords": ["z-index", "stacking", "modal", "overlay", "layer"],
        "buggy_code": ".modal-overlay {\n    position: fixed;\n    z-index: 10;\n}\n.modal-content {\n    position: relative;\n    z-index: 5;\n}\n",
        "expected_code": ".modal-overlay {\n    position: fixed;\n    z-index: 10;\n}\n.modal-content {\n    position: relative;\n    z-index: 20;\n}\n"
    },
    {
        "id": 3,
        "name": "Flexbox Alignment Mismatch",
        "filename": "flexbox.css",
        "description": "Flex items fail to center vertically within container due to align-items: stretch.",
        "keywords": ["flex", "align-items", "center", "stretch", "justify"],
        "buggy_code": ".flex-container {\n    display: flex;\n    justify-content: center;\n    align-items: stretch;\n}\n",
        "expected_code": ".flex-container {\n    display: flex;\n    justify-content: center;\n    align-items: center;\n}\n"
    },
    {
        "id": 4,
        "name": "Python AttributeError (None check)",
        "filename": "null_check.py",
        "description": "AttributeError when accessing status attribute on a None user response.",
        "keywords": ["None", "null", "check", "AttributeError", "get_user_status"],
        "buggy_code": "def get_user_status(user):\n    return user.status\n",
        "expected_code": "def get_user_status(user):\n    if user is None:\n        return \"offline\"\n    return user.status\n"
    },
    {
        "id": 5,
        "name": "JS Click Event Selector Mismatch",
        "filename": "event_handler.js",
        "description": "Click event listener attached to wrong selector submit-button-wrong instead of submit-button.",
        "keywords": ["selector", "querySelector", "submit-button", "event", "click"],
        "buggy_code": "const button = document.querySelector('.submit-button-wrong');\nbutton.addEventListener('click', () => {\n    console.log('Submitted');\n});\n",
        "expected_code": "const button = document.querySelector('.submit-button');\nbutton.addEventListener('click', () => {\n    console.log('Submitted');\n});\n"
    },
    {
        "id": 6,
        "name": "CSS Low Contrast Contrast Bug",
        "filename": "contrast.css",
        "description": "Error text is unreadable due to extremely low contrast foreground and background colors.",
        "keywords": ["contrast", "color", "background-color", "readability", "unreadable"],
        "buggy_code": ".error-text {\n    background-color: #ffcccc;\n    color: #ffdddd;\n}\n",
        "expected_code": ".error-text {\n    background-color: #ffcccc;\n    color: #990000;\n}\n"
    },
    {
        "id": 7,
        "name": "CSS Sidebar Mobile Breakpoint",
        "filename": "responsive.css",
        "description": "Sidebar has a fixed width on mobile resolutions causing responsive breaks.",
        "keywords": ["responsive", "breakpoint", "media", "max-width", "mobile", "sidebar"],
        "buggy_code": ".sidebar {\n    width: 250px;\n}\n",
        "expected_code": ".sidebar {\n    width: 250px;\n}\n@media (max-width: 768px) {\n    .sidebar {\n        width: 100%;\n    }\n}\n"
    },
    {
        "id": 8,
        "name": "Python Circular Dependency Import",
        "filename": "imports.py",
        "description": "Top-level circular import crash between app and circular dependency modules.",
        "keywords": ["circular", "import", "dependency", "local", "defer"],
        "buggy_code": "import app\n\ndef run_import_check():\n    return app.reviewer\n",
        "expected_code": "\ndef run_import_check():\n    import app\n    return app.reviewer\n"
    },
    {
        "id": 9,
        "name": "Python SQL Injection / Validation",
        "filename": "validation.py",
        "description": "SQL query parameter user_id is interpolated directly in string format without validation.",
        "keywords": ["validation", "sanitization", "cast", "int", "injection", "parameter"],
        "buggy_code": "def query_user(user_id):\n    return f\"SELECT * FROM users WHERE id = {user_id}\"\n",
        "expected_code": "def query_user(user_id):\n    clean_id = int(user_id)\n    return f\"SELECT * FROM users WHERE id = {clean_id}\"\n"
    },
    {
        "id": 10,
        "name": "JS DOM Element querySelector Mismatch",
        "filename": "dom_mismatch.js",
        "description": "Element with user-email-field-wrong referenced but actual element is user-email-field.",
        "keywords": ["getElementById", "selector", "email", "dom", "mismatch"],
        "buggy_code": "const input = document.getElementById('user-email-field-wrong');\nif (input) {\n    input.value = 'test@example.com';\n}\n",
        "expected_code": "const input = document.getElementById('user-email-field');\nif (input) {\n    input.value = 'test@example.com';\n}\n"
    }
]

def setup_benchmark_files(base_dir: Path):
    """Write benchmark cases to files if they do not exist"""
    base_dir.mkdir(parents=True, exist_ok=True)
    
    for case in BENCHMARK_CASES:
        case_dir = base_dir / f"case_{case['id']}"
        case_dir.mkdir(parents=True, exist_ok=True)
        
        # Write description
        desc_file = case_dir / "description.txt"
        desc_file.write_text(case["description"], encoding="utf-8")
        
        # Write buggy code file
        buggy_file = case_dir / case["filename"]
        buggy_file.write_text(case["buggy_code"], encoding="utf-8")
        
        # Write expected fix code file
        expected_file = case_dir / f"expected_fix_{case['filename']}"
        expected_file.write_text(case["expected_code"], encoding="utf-8")
        
        # Write screenshot file
        screenshot_file = case_dir / "screenshot.png"
        screenshot_file.write_bytes(TINY_PNG)

async def run_benchmark():
    # Make sure we're in mock mode if API key is not set
    if not os.getenv("OPENROUTER_API_KEY") and not os.getenv("HUGGINGFACE_API_KEY"):
        os.environ["MOCK_MODE"] = "true"
        print("⚠️ No API keys detected. Running benchmark in MOCK MODE.")
    else:
        print(f"🚀 Running benchmark in LIVE MODE using key: {os.getenv('OPENROUTER_API_KEY')[:8] if os.getenv('OPENROUTER_API_KEY') else 'HuggingFace'}")
        
    workspace_root = Path(__file__).parent.parent
    benchmark_dir = workspace_root / "examples" / "benchmark-cases"
    setup_benchmark_files(benchmark_dir)
    
    reviewer = CodeReviewer()
    print(f"Reviewer Mock Mode: {reviewer.mock_mode}")
    
    results = []
    
    print("\n" + "="*80)
    print("STARTING GEMMA 4 VISUAL PATCH AGENT BENCHMARK SUITE")
    print("="*80)
    
    for case in BENCHMARK_CASES:
        case_id = case["id"]
        filename = case["filename"]
        case_dir = benchmark_dir / f"case_{case_id}"
        buggy_file_path = case_dir / filename
        screenshot_path = case_dir / "screenshot.png"
        
        print(f"\n[Case {case_id}/10] Running {case['name']}...")
        
        start_time = time.time()
        
        # Trigger review pipeline
        review_result = await reviewer.review_files(
            file_paths=[str(buggy_file_path)],
            context=case["description"],
            image_paths=[str(screenshot_path)]
        )
        
        latency = time.time() - start_time
        
        # Gather file context for validation
        file_context = {
            filename: case["buggy_code"]
        }
        
        patch = review_result.get("patch", "")
        
        # Run validations
        git_apply_res = PatchApplicabilityChecker.check_applicability(patch, file_context) if patch else {"applicable": False, "message": "No patch generated"}
        ast_res = ASTValidator.validate_patched_files(patch, file_context) if patch else {"valid": False, "errors": ["No patch generated"]}
        ground_res = FileGroundingValidator.validate_grounding(patch, [str(buggy_file_path)]) if patch else {"grounded": False}
        
        # Compute keywords match
        root_cause = review_result.get("root_cause", "").lower()
        keyword_matched = any(kw.lower() in root_cause for kw in case["keywords"])
        
        # Compute patch line accuracy
        patch_accuracy = 0.0
        if patch and git_apply_res.get("applicable"):
            with tempfile.TemporaryDirectory() as temp_dir:
                temp_path = Path(temp_dir)
                temp_file = temp_path / filename
                temp_file.write_text(case["buggy_code"], encoding="utf-8")
                
                subprocess.run(["git", "init"], cwd=temp_dir, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                subprocess.run(["git", "add", "."], cwd=temp_dir, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                
                patch_file = temp_path / "patch.diff"
                patch_file.write_text(patch, encoding="utf-8")
                
                apply_p = subprocess.run(["git", "apply", "patch.diff"], cwd=temp_dir, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                if apply_p.returncode == 0:
                    patched_content = temp_file.read_text(encoding="utf-8")
                    if patched_content.strip() == case["expected_code"].strip():
                        patch_accuracy = 100.0
                    else:
                        import difflib
                        matcher = difflib.SequenceMatcher(None, patched_content.strip(), case["expected_code"].strip())
                        patch_accuracy = round(matcher.ratio() * 100, 1)
                        
        case_result = {
            "id": case_id,
            "name": case["name"],
            "bug_type": "CSS" if filename.endswith(".css") else ("JS" if filename.endswith(".js") else "Python"),
            "latency_sec": round(latency, 2),
            "root_cause_localization": "PASSED" if keyword_matched else "FAILED",
            "git_apply_check": "PASSED" if git_apply_res.get("applicable") else "FAILED",
            "ast_validation": "PASSED" if ast_res.get("valid") else "FAILED",
            "patch_accuracy_percent": patch_accuracy,
            "overall_status": "SUCCESS" if (keyword_matched and git_apply_res.get("applicable") and ast_res.get("valid") and patch_accuracy > 80.0) else "FAILED"
        }
        
        print(f"  Latency: {case_result['latency_sec']}s")
        print(f"  Localization: {case_result['root_cause_localization']}")
        print(f"  Git Apply: {case_result['git_apply_check']} ({git_apply_res.get('message', '')})")
        print(f"  AST Valid: {case_result['ast_validation']} ({', '.join(ast_res.get('errors', [])) if ast_res.get('errors') else ''})")
        print(f"  Patch Accuracy: {case_result['patch_accuracy_percent']}%")
        print(f"  Overall: {case_result['overall_status']}")
        
        results.append(case_result)
        
    # Generate statistics
    total_cases = len(results)
    avg_latency = sum(r["latency_sec"] for r in results) / total_cases
    success_count = sum(1 for r in results if r["overall_status"] == "SUCCESS")
    localization_count = sum(1 for r in results if r["root_cause_localization"] == "PASSED")
    git_apply_count = sum(1 for r in results if r["git_apply_check"] == "PASSED")
    ast_count = sum(1 for r in results if r["ast_validation"] == "PASSED")
    avg_accuracy = sum(r["patch_accuracy_percent"] for r in results) / total_cases
    
    print("\n" + "="*80)
    print("BENCHMARK SUMMARY")
    print("="*80)
    print(f"Total Cases: {total_cases}")
    print(f"Overall Success Rate: {success_count}/{total_cases} ({round(success_count/total_cases*100, 1)}%)")
    print(f"Localization Accuracy: {localization_count}/{total_cases} ({round(localization_count/total_cases*100, 1)}%)")
    print(f"Git Apply Applicability: {git_apply_count}/{total_cases} ({round(git_apply_count/total_cases*100, 1)}%)")
    print(f"AST/Syntax Validity: {ast_count}/{total_cases} ({round(ast_count/total_cases*100, 1)}%)")
    print(f"Average Patch Accuracy: {round(avg_accuracy, 1)}%")
    print(f"Average Latency: {round(avg_latency, 2)}s")
    print("="*80)
    
    # Save to JSON in case frontend wants it
    summary_data = {
        "metrics": {
            "total_cases": total_cases,
            "success_rate_percent": round(success_count/total_cases*100, 1),
            "localization_accuracy_percent": round(localization_count/total_cases*100, 1),
            "git_apply_percent": round(git_apply_count/total_cases*100, 1),
            "ast_percent": round(ast_count/total_cases*100, 1),
            "average_accuracy_percent": round(avg_accuracy, 1),
            "average_latency_sec": round(avg_latency, 2)
        },
        "results": results
    }
    
    with open(workspace_root / "demo_results.json", "w") as f:
        json.dump(summary_data, f, indent=2)
    with open(benchmark_dir / "results.json", "w") as f:
        json.dump(summary_data, f, indent=2)
        
    # Generate Markdown Table
    md_table = "| Case ID | Test Case Name | Language/Type | Latency (s) | Localization | Git Apply | AST Valid | Patch Accuracy | Status |\n"
    md_table += "|---|---|---|---|---|---|---|---|---|\n"
    for r in results:
        status_emoji = "✅" if r["overall_status"] == "SUCCESS" else "❌"
        md_table += f"| {r['id']} | {r['name']} | {r['bug_type']} | {r['latency_sec']}s | {r['root_cause_localization']} | {r['git_apply_check']} | {r['ast_validation']} | {r['patch_accuracy_percent']}% | {status_emoji} {r['overall_status']} |\n"
        
    md_summary = f"""### Benchmark Metrics Summary
- **Overall Agent Success Rate**: {round(success_count/total_cases*100, 1)}% ({success_count}/{total_cases})
- **UI Bug Localization Accuracy**: {round(localization_count/total_cases*100, 1)}%
- **Git Apply applicability**: {round(git_apply_count/total_cases*100, 1)}%
- **AST / Syntax validity**: {round(ast_count/total_cases*100, 1)}%
- **Average latency**: {round(avg_latency, 2)}s
- **Average patch line accuracy**: {round(avg_accuracy, 1)}%
"""
    
    md_output = f"## Gemma 4 Visual Patch Agent Benchmark Report\n\n{md_summary}\n\n{md_table}"
    with open(benchmark_dir / "report.md", "w") as f:
        f.write(md_output)
        
    print(f"\nSaved report to {benchmark_dir / 'report.md'}")
    print(f"Saved results database to {workspace_root / 'demo_results.json'}")

if __name__ == "__main__":
    asyncio.run(run_benchmark())
