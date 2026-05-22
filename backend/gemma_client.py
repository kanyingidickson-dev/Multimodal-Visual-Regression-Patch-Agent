import os
import json
from typing import List, Dict, Optional
import requests

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
"""
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
"""
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
