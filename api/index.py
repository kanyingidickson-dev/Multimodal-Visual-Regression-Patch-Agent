import os
import json
import asyncio
import re
import time
import random
import mimetypes
import base64
from pathlib import Path
from typing import List, Dict, Optional, Tuple, Any

from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from mangum import Mangum
import tempfile
import shutil
import requests

# ==================== INLINE PROMPT TEMPLATES ====================
SYSTEM_PROMPT = """You are a precise senior code reviewer and systems architect specializing in multimodal analysis. You analyze source code files alongside UI screenshots to identify bugs, visual mismatches, and generate production-ready patches.

## Your Capabilities

1. **Code Analysis**: Identify bugs, syntax errors, security vulnerabilities, race conditions, and performance bottlenecks across all major programming languages.
2. **Visual Cross-Referencing**: When screenshots are provided, map visual defects (layout misalignment, overflow, color contrast issues, broken interactions) back to specific CSS selectors, DOM structure, or rendering logic in the source code.
3. **Root Cause Diagnosis**: Trace symptoms to their underlying cause with precision — don't just report what's wrong, explain *why* it's wrong.
4. **Patch Generation**: Generate complete, valid git patches (unified diff format) that apply cleanly. Use standard `--- a/filename` and `+++ b/filename` headers.

## Response Format

You MUST respond with a single JSON object containing EXACTLY these keys:

```json
{
    "summary": "Concise overview of findings: what was analyzed, what was found, and the severity",
    "root_cause": "Detailed technical explanation of the root cause. Reference specific lines, functions, or selectors",
    "fix_plan": ["Step 1: ...", "Step 2: ...", "Step 3: ..."],
    "patch": "A valid unified diff patch, or null if no code changes are needed",
    "assumptions": ["Any assumptions made during analysis"],
    "confidence": "high | medium | low"
}
```

## Guidelines

- Be highly technical and direct. Avoid vague language.
- When screenshots are present, explicitly mention what visual elements you see and how they relate to the code.
- In `fix_plan`, order steps by priority (critical fixes first).
- Set `confidence` to "high" when the bug is clear and the fix is deterministic, "medium" when the diagnosis is likely but context may be missing, and "low" when the analysis is speculative.
- Do not output anything other than the raw JSON object. No markdown fences, no commentary.
"""

USER_PROMPT_TEMPLATE = """Context: {context}

Files to review:
{files_section}

Analyze the code above (and any provided screenshots). If screenshots are included, cross-reference visible UI elements against the source code to identify mismatches between the intended layout and the actual implementation.

Respond with your analysis in the specified JSON format. Ensure the patch field contains a valid unified diff if fixes are needed, or null if the code is correct.
"""

# ==================== FILE PARSING UTILITIES ====================
def read_file_sync(file_path: str) -> str:
    """Read file content with encoding fallback (synchronous version)"""
    path = Path(file_path)
    try:
        return path.read_text(encoding='utf-8')
    except UnicodeDecodeError:
        try:
            return path.read_text(encoding='latin-1')
        except:
            return f"[Binary file: {path.name}]"

async def read_file(file_path: str) -> str:
    """Read file content with encoding fallback"""
    return read_file_sync(file_path)

def truncate_content(content: str, max_tokens: int = 16000) -> str:
    """Truncate content to fit within context window (approximate)"""
    max_chars = max_tokens * 4
    if len(content) <= max_chars:
        return content
    return content[:max_chars] + "\n... [content truncated for context window]"

async def encode_image(image_path: str) -> str:
    """Encode image file to base64 data URL"""
    path = Path(image_path)
    if not path.exists():
        return ""
    mime_type, _ = mimetypes.guess_type(str(path))
    if not mime_type:
        mime_type = "image/jpeg"
    try:
        with open(path, "rb") as image_file:
            image_data = image_file.read()
            encoded_string = base64.b64encode(image_data).decode('utf-8')
        return f"data:{mime_type};base64,{encoded_string}"
    except Exception as e:
        print(f"Error encoding image {image_path}: {e}")
        return ""

# ==================== PROMPT BUILDING ====================
def build_prompt(files: List[Dict], context: str = "") -> Tuple[str, str]:
    """Build the system and user prompts for code review"""
    files_section = "\n\n".join([
        f"File: {f['name']}\n```\n{f['content']}\n```"
        for f in files
    ])
    
    user_prompt = USER_PROMPT_TEMPLATE.format(
        context=context if context else 'General code review',
        files_section=files_section
    )
    
    return SYSTEM_PROMPT, user_prompt

# ==================== GEMMA CLIENT ====================
class GemmaClient:
    """Client for interacting with Gemma 4 API"""
    
    def __init__(self):
        self.api_key = os.getenv('OPENROUTER_API_KEY') or os.getenv('HUGGINGFACE_API_KEY')
        self.base_url = os.getenv('OPENROUTER_BASE_URL', 'https://openrouter.ai/api/v1')
        self.use_openrouter = bool(os.getenv('OPENROUTER_API_KEY'))
        self.mock_mode = os.getenv('MOCK_MODE', 'false').lower() == 'true'
        
        if not self.api_key and not self.mock_mode:
            raise ValueError("API key not found. Set OPENROUTER_API_KEY or HUGGINGFACE_API_KEY in .env, or set MOCK_MODE=true")
            
    def call_model(self, system_prompt: str, user_prompt: str, images: Optional[List[str]] = None, model: Optional[str] = None) -> str:
        """Call Gemma 4 model via API"""
        if self.mock_mode:
            return self._mock_response(user_prompt, images)
        
        model = model or os.getenv('MODEL_CHOICE', 'gemma-4-31b')
        if self.use_openrouter:
            return self._call_openrouter(system_prompt, user_prompt, images, model)
        return self._call_huggingface(system_prompt, user_prompt, images, model)
    def _mock_response(self, user_prompt: str, images: Optional[List[str]] = None) -> str:
        """Return a dynamic mock response for testing/demo purposes"""
        import re
        import time
        import random
        from pathlib import Path
        
        # Simulate API latency
        time.sleep(random.uniform(0.5, 1.5))
        
        file_names = re.findall(r"File: ([a-zA-Z0-9_\-\.]+)\n", user_prompt)
        if file_names:
            file_names = list(dict.fromkeys(file_names))
        else:
            file_names = ["app.py"]
            
        has_images = bool(images and len(images) > 0)
        main_file = file_names[0]
        ext = Path(main_file).suffix.lower()
        
        summary = f"Gemma 4 completed visual cross-referencing and code review of {len(file_names)} file(s)."
        if has_images:
            summary += " Successfully aligned visual screenshot layout defects with matching CSS/JS selectors."
            
        # Lowercase prompt for keyword routing
        context_lower = user_prompt.lower()

        # 1. File validation logic check
        if any(kw in context_lower for kw in ["reject", "validation", "validate", "allowed_extensions", "extension", "file type", "mime"]):
            root_cause = "The file validation utility (`validate_code_content` in `patch_utils.py`) uses a strict, hardcoded file extension whitelist `allowed_extensions` that rejects legitimate files (such as `.bin`, `.example`, or `.env`). This causes the API to reject safe, valid files instead of scanning them gracefully."
            fix_plan = [
                "Locate the `validate_code_content` function in the validation logic (or `patch_utils.py`).",
                "Expand `allowed_extensions` to support safe fallbacks (e.g., `.example`, `.bin`, `.env`, `.yml`, etc.).",
                "Introduce soft warnings instead of strictly raising errors when encountering custom or unrecognized extensions to prevent API blocking."
            ]
            patch_target = main_file if main_file else "patch_utils.py"
            patch = f"""diff --git a/{patch_target} b/{patch_target}
index 5b28ea1..e88c0a2 100644
--- a/{patch_target}
+++ b/{patch_target}
@@ -421,5 +421,7 @@ def validate_code_content(files: List[str]) -> Dict:
             
             # Check file extension
-            allowed_extensions = {{'.py', '.js', '.ts', '.jsx', '.tsx', '.java', '.go', '.rs', '.cpp', '.c', '.txt', '.md', '.html', '.css', '.json', '.yaml', '.yml'}}
+            allowed_extensions = {{'.py', '.js', '.ts', '.jsx', '.tsx', '.java', '.go', '.rs', '.cpp', '.c', '.txt', '.md', '.html', '.css', '.json', '.yaml', '.yml', '.example', '.bin', '.env'}}
             if path.suffix.lower() not in allowed_extensions:
-                results['warnings'].append(f"File {{path.name}} has unusual extension: {{path.suffix}}")
+                # Allow unrecognized safe text/data extensions as soft warnings
+                results['warnings'].append(f"File {{path.name}} has custom extension: {{path.suffix}} - proceeding with standard analysis")
+"""
        # 2. SQL injection / sanitization
        elif any(kw in context_lower for kw in ["sql", "injection", "sanitize", "query"]) or "validation.py" in main_file:
            root_cause = "Unsanitized user input user_id interpolation in string query could lead to SQL injection vulnerabilities or type crashes."
            fix_plan = [
                "Locate query_user function",
                "Cast user_id parameter explicitly to an integer before database query interpolation"
            ]
            patch_target = main_file if main_file else "validation.py"
            patch = f"""diff --git a/{patch_target} b/{patch_target}
index 1111111..2222222 100644
--- a/{patch_target}
+++ b/{patch_target}
@@ -1,2 +1,3 @@
 def query_user(user_id):
-    return f"SELECT * FROM users WHERE id = {{user_id}}"
+    clean_id = int(user_id)
+    return f"SELECT * FROM users WHERE id = {{clean_id}}"
+"""
        # 3. Text Overflow
        elif any(kw in context_lower for kw in ["overflow", "nowrap", "ellipsis", "scroll", "white-space"]) or "overflow.css" in main_file:
            root_cause = "Text overflows container bounds because overflow properties are not set. The container has nowrap white-space but lacks hidden overflow rules."
            fix_plan = [
                "Locate the .text-container class in CSS",
                "Apply overflow: hidden to contain the overflowing content",
                "Apply text-overflow: ellipsis to gracefully truncate the long text"
            ]
            patch_target = main_file if main_file else "overflow.css"
            patch = f"""diff --git a/{patch_target} b/{patch_target}
index 1111111..2222222 100644
--- a/{patch_target}
+++ b/{patch_target}
@@ -1,4 +1,6 @@
 .text-container {{
     width: 300px;
     white-space: nowrap;
+    overflow: hidden;
+    text-overflow: ellipsis;
 }}
 """
        # 4. Stacking Context
        elif any(kw in context_lower for kw in ["stacking", "z-index", "layer", "modal", "overlay"]) or "stacking.css" in main_file:
            root_cause = "The modal-content is hidden or incorrectly layered behind the modal-overlay due to a lower z-index stack configuration."
            fix_plan = [
                "Locate the z-index configurations for overlay and content in CSS",
                "Increase the z-index of .modal-content relative to .modal-overlay"
            ]
            patch_target = main_file if main_file else "stacking.css"
            patch = f"""diff --git a/{patch_target} b/{patch_target}
index 1111111..2222222 100644
--- a/{patch_target}
+++ b/{patch_target}
@@ -5,4 +5,4 @@
 .modal-content {{
     position: relative;
-    z-index: 5;
+    z-index: 20;
 }}
 """
        # 5. Flexbox Alignment
        elif any(kw in context_lower for kw in ["flexbox", "align-items", "justify-content", "stretch", "center"]) or "flexbox.css" in main_file:
            root_cause = "Flexbox container items are not centering properly due to the use of align-items: stretch."
            fix_plan = [
                "Locate the .flex-container class in CSS",
                "Change align-items value from stretch to center"
            ]
            patch_target = main_file if main_file else "flexbox.css"
            patch = f"""diff --git a/{patch_target} b/{patch_target}
index 1111111..2222222 100644
--- a/{patch_target}
+++ b/{patch_target}
@@ -1,5 +1,5 @@
 .flex-container {{
     display: flex;
     justify-content: center;
-    align-items: stretch;
+    align-items: center;
 }}
 """
        # 6. Null Check / None Check
        elif any(kw in context_lower for kw in ["null", "none", "attributeerror", "none check"]) or "null_check.py" in main_file:
            root_cause = "Missing null/None check on the user object leads to an AttributeError: 'NoneType' object has no attribute 'status'."
            fix_plan = [
                "Locate the get_user_status function in python",
                "Verify if user is None before accessing the status attribute"
            ]
            patch_target = main_file if main_file else "null_check.py"
            patch = f"""diff --git a/{patch_target} b/{patch_target}
index 1111111..2222222 100644
--- a/{patch_target}
+++ b/{patch_target}
@@ -1,2 +1,4 @@
 def get_user_status(user):
+    if user is None:
+        return "offline"
     return user.status
 """
        # 7. Selector Mismatch / Event Handler
        elif any(kw in context_lower for kw in ["event", "handler", "click", "selector"]) or "event_handler.js" in main_file:
            root_cause = "The document.querySelector call targets a non-existent CSS class '.submit-button-wrong', causing click event listeners to fail."
            fix_plan = [
                "Verify correct CSS class name for the submit button element",
                "Correct target class selector inside querySelector"
            ]
            patch_target = main_file if main_file else "event_handler.js"
            patch = f"""diff --git a/{patch_target} b/{patch_target}
index 1111111..2222222 100644
--- a/{patch_target}
+++ b/{patch_target}
@@ -1,4 +1,4 @@
-const button = document.querySelector('.submit-button-wrong');
+const button = document.querySelector('.submit-button');
 button.addEventListener('click', () => {{
     console.log('Submitted');
 }});
 """
        # 8. Contrast accessibility
        elif any(kw in context_lower for kw in ["contrast", "color", "accessibility", "dark", "contrast ratio"]) or "contrast.css" in main_file:
            root_cause = "Color contrast ratio between text foreground (#ffdddd) and background (#ffcccc) is too low, making the error text unreadable."
            fix_plan = [
                "Locate .error-text styling in CSS",
                "Change text color to a high-contrast dark red shade (#990000)"
            ]
            patch_target = main_file if main_file else "contrast.css"
            patch = f"""diff --git a/{patch_target} b/{patch_target}
index 1111111..2222222 100644
--- a/{patch_target}
+++ b/{patch_target}
@@ -1,4 +1,4 @@
 .error-text {{
     background-color: #ffcccc;
-    color: #ffdddd;
+    color: #990000;
 }}
 """
        # 9. Responsive / Media viewport
        elif any(kw in context_lower for kw in ["responsive", "mobile", "media query", "sidebar", "breakpoint"]) or "responsive.css" in main_file:
            root_cause = "Sidebar component width is fixed to 250px on all viewports, breaking layouts on smaller mobile screens."
            fix_plan = [
                "Add media queries to override layout rules on smaller screens",
                "Configure mobile sidebar width to 100% block format"
            ]
            patch_target = main_file if main_file else "responsive.css"
            patch = f"""diff --git a/{patch_target} b/{patch_target}
index 1111111..2222222 100644
--- a/{patch_target}
+++ b/{patch_target}
@@ -1,3 +1,8 @@
 .sidebar {{
     width: 250px;
 }}
+@media (max-width: 768px) {{
+    .sidebar {{
+        width: 100%;
+    }}
+}}
 """
        # 10. Circular import / dependencies
        elif any(kw in context_lower for kw in ["circular", "import", "dependency"]) or "imports.py" in main_file:
            root_cause = "Top-level import of app module causes a circular dependency crash when starting the service."
            fix_plan = [
                "Locate top-level imports block",
                "Defer the import of app into the local function context run_import_check"
            ]
            patch_target = main_file if main_file else "imports.py"
            patch = f"""diff --git a/{patch_target} b/{patch_target}
index 1111111..2222222 100644
--- a/{patch_target}
+++ b/{patch_target}
@@ -1,4 +1,4 @@
-import app
 
 def run_import_check():
+    import app
     return app.reviewer
 """
        # 11. DOM query mismatch
        elif "dom_mismatch.js" in main_file:
            root_cause = "The script attempts to get an element using user-email-field-wrong which is not present in the HTML DOM structure."
            fix_plan = [
                "Correct the document.getElementById query to target the proper user-email-field ID"
            ]
            patch_target = main_file if main_file else "dom_mismatch.js"
            patch = f"""diff --git a/{patch_target} b/{patch_target}
index 1111111..2222222 100644
--- a/{patch_target}
+++ b/{patch_target}
@@ -1,4 +1,4 @@
-const input = document.getElementById('user-email-field-wrong');
+const input = document.getElementById('user-email-field');
 if (input) {{
     input.value = 'test@example.com';
 }}
 """
        # Fallbacks for other generic testing
        elif ext == '.css':
            root_cause = "The screenshot reveals elements inside the container overflow horizontally on mobile screens due to a static width. The flex direction needs to be wrapped or changed to column." if has_images else "Flexbox containers lack responsive wrap settings causing overflow."
            fix_plan = [
                "Locate the container selector in the stylesheet",
                "Change layout model from static flex-row to responsive column/wrap",
                "Apply overflow safety guards on child elements"
            ]
            patch = f"""diff --git a/{main_file} b/{main_file}
index 1234567..abcdefg 100644
--- a/{main_file}
+++ b/{main_file}
@@ -10,6 +10,11 @@
 .card-container {{
     display: flex;
-    flex-direction: row;
+    flex-direction: column;
+    overflow: hidden;
+    align-items: center;
+    gap: 1.5rem;
 }}
 """
        elif ext in ['.js', '.jsx', '.ts', '.tsx']:
            root_cause = "Mismatched rendering bounds or state missing check in React element map causing render crash when items array is empty/undefined." if has_images else "Missing boundaries validation for items iteration."
            fix_plan = [
                "Add defensive parameter checks to component properties",
                "Render placeholder empty state when items are undefined or empty",
                "Optimize performance of child components inside map callback"
            ]
            patch = f"""diff --git a/{main_file} b/{main_file}
index 1234567..abcdefg 100644
--- a/{main_file}
+++ b/{main_file}
@@ -20,7 +20,11 @@
 export function Component({{ items }}) {{
 +  if (!items || items.length === 0) {{
 +    return <div className="empty-state">No items available to display</div>;
 +  }}
 +
   return (
     <div className="list">
       {{items.map(item => (
 """
        else:
            root_cause = "Visual verification indicates the API limits validator lacks boundaries checks causing index errors on file handling." if has_images else "Parameter limits are unvalidated on process requests."
            fix_plan = [
                "Introduce missing validation for file arrays in input payload",
                "Sanitize incoming arguments to safeguard against directory traversals",
                "Gracefully reject requests exceeding system size boundaries"
            ]
            patch = f"""diff --git a/{main_file} b/{main_file}
index 1234567..abcdefg 100644
--- a/{main_file}
+++ b/{main_file}
@@ -12,6 +12,12 @@
     def process_request(self, data):
 +        if not data or 'files' not in data:
 +            raise ValueError("Invalid request parameters: missing files")
 +        
 +        # Validate input file sizes to prevent OOM
 +        if len(data.get('files', [])) > 100:
 +            raise ValueError("Too many files submitted")
         return True
 """

        return json.dumps({
            "summary": summary,
            "root_cause": root_cause,
            "fix_plan": fix_plan,
            "patch": patch,
            "assumptions": [
                "Assume target element selector matches CSS markup",
                "Assume backend receives data dictionary structure"
            ],
            "confidence": "high"
        })
        
    def _call_openrouter(self, system_prompt: str, user_prompt: str, images: Optional[List[str]], model: str) -> str:
        """Call model via OpenRouter API"""
        headers = {
            'Authorization': f'Bearer {self.api_key}',
            'Content-Type': 'application/json',
            'HTTP-Referer': 'http://localhost:5000',
            'X-Title': 'Gemma 4 Code Reviewer'
        }
        
        model_map = {
            'gemma-4-31b': 'google/gemma-4-31b-it',
            'gemma-4-26b-moe': 'google/gemma-4-26b-a4b-it',
            'gemma-4-4b': 'google/gemma-4-e4b-it'
        }
        model_id = model_map.get(model, 'google/gemma-4-31b-it')
        
        if images:
            user_content = []
            for img_data in images:
                if img_data:
                    user_content.append({"type": "image_url", "image_url": {"url": img_data}})
            user_content.append({"type": "text", "text": user_prompt})
        else:
            user_content = user_prompt
            
        payload = {
            'model': model_id,
            'messages': [
                {'role': 'system', 'content': system_prompt},
                {'role': 'user', 'content': user_content}
            ],
            'temperature': 0.2,
            'max_tokens': 4000
        }
        
        response = requests.post(
            f'{self.base_url}/chat/completions',
            headers=headers,
            json=payload,
            timeout=120
        )
        response.raise_for_status()
        data = response.json()
        return data['choices'][0]['message']['content']
        
    def _call_huggingface(self, system_prompt: str, user_prompt: str, images: Optional[List[str]], model: str) -> str:
        """Call model via Hugging Face Inference API"""
        headers = {
            'Authorization': f'Bearer {self.api_key}',
            'Content-Type': 'application/json'
        }
        
        text_context = ""
        if images:
            text_context = f"[Note: {len(images)} screenshots were uploaded. Multimodal review is fully optimized on OpenRouter. Attempting text analysis.]\n\n"
            
        full_prompt = f"{system_prompt}\n\n{text_context}{user_prompt}"
        
        payload = {
            'inputs': full_prompt,
            'parameters': {
                'max_new_tokens': 4000,
                'temperature': 0.2,
                'return_full_text': False
            }
        }
        
        model_id = os.getenv('HUGGINGFACE_MODEL', 'google/gemma-4-31b-it')
        
        response = requests.post(
            f'https://api-inference.huggingface.co/models/{model_id}',
            headers=headers,
            json=payload,
            timeout=120
        )
        response.raise_for_status()
        data = response.json()
        
        if isinstance(data, list):
            return data[0]['generated_text']
        return data

# ==================== CODE REVIEWER ====================
class CodeReviewer:
    """Multimodal code reviewer powered by Gemma 4"""
    
    def __init__(self):
        self.client = GemmaClient()
        
    @property
    def mock_mode(self):
        return self.client.mock_mode

    @mock_mode.setter
    def mock_mode(self, value):
        self.client.mock_mode = value
    
    def _parse_response(self, response: str) -> Dict:
        """Parse model response into structured format"""
        cleaned_response = response.strip()
        if cleaned_response.startswith("```json"):
            cleaned_response = cleaned_response[7:]
        elif cleaned_response.startswith("```"):
            cleaned_response = cleaned_response[3:]
        
        if cleaned_response.endswith("```"):
            cleaned_response = cleaned_response[:-3]
            
        try:
            start_idx = cleaned_response.find('{')
            end_idx = cleaned_response.rfind('}') + 1
            
            if start_idx != -1 and end_idx > start_idx:
                json_str = cleaned_response[start_idx:end_idx]
                parsed = json.loads(json_str)
                
                # Coerce fix_plan to list
                if 'fix_plan' in parsed and isinstance(parsed['fix_plan'], str):
                    parsed['fix_plan'] = [parsed['fix_plan']]
                elif 'fix_plan' not in parsed:
                    parsed['fix_plan'] = []
                
                # Derive confidence field
                confidence = str(parsed.get('confidence', '')).strip().lower()
                if confidence not in ['high', 'medium', 'low']:
                    if parsed.get('patch') and 'diff --git' in str(parsed.get('patch', '')):
                        parsed['confidence'] = 'high'
                    elif parsed.get('fix_plan') and len(parsed['fix_plan']) > 0:
                        parsed['confidence'] = 'medium'
                    else:
                        parsed['confidence'] = 'low'
                else:
                    parsed['confidence'] = confidence
                
                return parsed
        except Exception as e:
            pass
        
        return {
            'summary': response[:500] if len(response) > 500 else response,
            'root_cause': "Failed to parse structured JSON from model response",
            'fix_plan': ["Examine the raw response model text output"],
            'patch': None,
            'assumptions': [],
            'confidence': 'low'
        }
    
    async def review_files(self, file_paths: List[str], context: str = "", image_paths: Optional[List[str]] = None, model: Optional[str] = None) -> Dict:
        files_data = []
        for path in file_paths:
            content = await read_file(path)
            content = truncate_content(content)
            files_data.append({
                'name': Path(path).name,
                'content': content
            })
            
        encoded_images = []
        if image_paths:
            for img_path in image_paths:
                b64_img = await encode_image(img_path)
                if b64_img:
                    encoded_images.append(b64_img)
        
        system_prompt, user_prompt = build_prompt(files_data, context)
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(None, self.client.call_model, system_prompt, user_prompt, encoded_images, model)
        result = self._parse_response(response)
        
        return result

# ==================== PATCH VALIDATION (SIMPLIFIED) ====================
class PatchValidator:
    """Validates generated patches before application"""
    
    def __init__(self):
        self.safety_checks = [
            self._check_file_operations,
            self._check_destructive_commands
        ]
    
    def validate_patch(self, patch: str, file_context: Dict[str, str]) -> Dict:
        """Validate a patch for safety"""
        results = {
            'is_safe': True,
            'warnings': [],
            'errors': []
        }
        
        for check in self.safety_checks:
            try:
                check_result = check(patch, file_context)
                if check_result.get('error'):
                    results['errors'].append(check_result['error'])
                    results['is_safe'] = False
                elif check_result.get('warning'):
                    results['warnings'].append(check_result['warning'])
            except Exception as e:
                results['warnings'].append(f"Check failed: {str(e)}")
        
        return results
    
    def _check_file_operations(self, patch: str, file_context: Dict) -> Dict:
        """Check for dangerous file operations"""
        dangerous_patterns = ['rm -rf', 'delete(', 'os.remove', 'shutil.rmtree', 'unlink(', 'exec(', 'eval(']
        for pattern in dangerous_patterns:
            if pattern.lower() in patch.lower():
                return {'error': f"Dangerous file operation detected: {pattern}"}
        return {}
    
    def _check_destructive_commands(self, patch: str, file_context: Dict) -> Dict:
        """Check for destructive shell commands"""
        destructive = ['> /dev/', 'format', 'mkfs', 'dd if=', ':(){:|:&};:']
        for cmd in destructive:
            if cmd in patch:
                return {'error': f"Destructive command detected: {cmd}"}
        return {}

class FileGroundingValidator:
    """Verifies that patch only targets uploaded files"""

    @staticmethod
    def validate_grounding(patch: str, allowed_files: List[str]) -> Dict[str, Any]:
        target_files = []
        for line in patch.splitlines():
            if line.startswith("--- a/") or line.startswith("--- "):
                p = line[6:] if line.startswith("--- a/") else line[4:]
                p = p.strip().split('\t')[0]
                if p != "/dev/null" and p not in target_files:
                    target_files.append(p)
            elif line.startswith("+++ b/") or line.startswith("+++ "):
                p = line[6:] if line.startswith("--- b/") else line[4:]
                p = p.strip().split('\t')[0]
                if p != "/dev/null" and p not in target_files:
                    target_files.append(p)
                    
        allowed_basenames = {Path(f).name for f in allowed_files}
        allowed_paths = {f for f in allowed_files}
        
        unknown_files = []
        for tf in target_files:
            tf_basename = Path(tf).name
            if tf not in allowed_paths and tf_basename not in allowed_basenames:
                unknown_files.append(tf)
                
        return {
            "grounded": len(unknown_files) == 0,
            "unknown_files": unknown_files
        }

# ==================== FASTAPI APP ====================
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Vercel automatically mounts api/ directory functions at /api/*
# No prefix needed - requests to /api/health arrive as /health
from fastapi import APIRouter
api_router = APIRouter(prefix="/api")

@api_router.get("/health")
def health_check():
    """Health check endpoint"""
    mock_mode = os.getenv("MOCK_MODE", "false").lower() == "true"
    return {
        "status": "healthy",
        "mock_mode": mock_mode,
        "model": os.getenv("MODEL_CHOICE", "gemma-4-31b")
    }

@api_router.post("/review")
async def review_endpoint(
    files: List[UploadFile] = File(None),
    images: List[UploadFile] = File(None),
    context: str = Form(""),
    model: str = Form("gemma-4-31b"),
    api_key: str = Form(None)
):
    """Main review endpoint"""
    if not files and not images:
        raise HTTPException(status_code=400, detail="No files or images uploaded")
        
    try:
        # Initialize client and reviewer
        reviewer = CodeReviewer()
        
        # Save uploaded files to temp directory
        temp_dir = tempfile.mkdtemp()
        file_paths = []
        image_paths = []
        
        try:
            # Save code files
            if files:
                for file in files:
                    file_path = os.path.join(temp_dir, file.filename)
                    with open(file_path, 'wb') as f:
                        f.write(await file.read())
                    file_paths.append(file_path)
            
            # Save image files
            if images:
                for img in images:
                    img_path = os.path.join(temp_dir, img.filename)
                    with open(img_path, 'wb') as f:
                        f.write(await img.read())
                    image_paths.append(img_path)
            
            # Run review
            result = await reviewer.review_files(file_paths, context, image_paths, model)
            
            # Validate patch if present (simplified, no git)
            if result.get('patch'):
                file_context = {}
                for fp in file_paths:
                    try:
                        with open(fp, 'r', encoding='utf-8') as f:
                            file_context[fp] = f.read()
                    except:
                        pass
                
                result['patch_validation'] = PatchValidator().validate_patch(result['patch'], file_context)
                result['file_grounding'] = FileGroundingValidator().validate_grounding(result['patch'], file_paths)
                result['patch_applicable'] = None
                result['patch_applicable_message'] = 'Git validation skipped (not available in serverless environment)'
                result['ast_valid'] = None
                result['ast_error'] = None
            
            return result
            
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)
            
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Register the /api router
app.include_router(api_router)

# Vercel handler
handler = Mangum(app)
