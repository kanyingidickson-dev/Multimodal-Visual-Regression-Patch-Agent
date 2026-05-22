"""
Validation and safety checks for code review patches
"""

import subprocess
import tempfile
import os
import ast
from pathlib import Path
from typing import Dict, List, Optional, Any


class PatchValidator:
    """Validates generated patches before application"""
    
    def __init__(self):
        self.safety_checks = [
            self._check_file_operations,
            self._check_destructive_commands,
            self._check_suspicious_imports
        ]
    
    def validate_patch(self, patch: str, file_context: Dict[str, str]) -> Dict:
        """
        Validate a patch for safety before recommending application
        
        Args:
            patch: Git diff format patch
            file_context: Dictionary mapping filenames to original content
            
        Returns:
            Dict with validation results and warnings
        """
        results = {
            'is_safe': True,
            'warnings': [],
            'errors': [],
            'checks_passed': 0,
            'checks_total': len(self.safety_checks)
        }
        
        for check in self.safety_checks:
            try:
                check_result = check(patch, file_context)
                if check_result.get('error'):
                    results['errors'].append(check_result['error'])
                    results['is_safe'] = False
                elif check_result.get('warning'):
                    results['warnings'].append(check_result['warning'])
                results['checks_passed'] += 1
            except Exception as e:
                results['warnings'].append(f"Check failed: {str(e)}")
        
        return results
    
    def _check_file_operations(self, patch: str, file_context: Dict) -> Dict:
        """Check for dangerous file operations in patch"""
        dangerous_patterns = [
            'rm -rf',
            'delete(',
            'os.remove',
            'shutil.rmtree',
            'unlink(',
            'exec(',
            'eval('
        ]
        
        for pattern in dangerous_patterns:
            if pattern.lower() in patch.lower():
                return {
                    'error': f"Dangerous file operation detected: {pattern}"
                }
        
        return {}
    
    def _check_destructive_commands(self, patch: str, file_context: Dict) -> Dict:
        """Check for destructive shell commands"""
        destructive = [
            '> /dev/',
            'format',
            'mkfs',
            'dd if=',
            ':(){:|:&};:',  # fork bomb
        ]
        
        for cmd in destructive:
            if cmd in patch:
                return {
                    'error': f"Destructive command detected: {cmd}"
                }
        
        return {}
    
    def _check_suspicious_imports(self, patch: str, file_context: Dict) -> Dict:
        """Check for suspicious or potentially malicious imports"""
        suspicious_imports = [
            'import os.system',
            'import subprocess.call',
            'import pickle',
            'import marshal',
            'import ctypes',
            '__import__'
        ]
        
        for imp in suspicious_imports:
            if imp in patch:
                return {
                    'warning': f"Suspicious import detected: {imp} - review manually"
                }
        
        return {}


class PatchApplicabilityChecker:
    """Verifies patch application using git apply --check"""

    @staticmethod
    def check_applicability(patch: str, file_context: Dict[str, str]) -> Dict[str, Any]:
        if not patch or not patch.strip():
            return {"applicable": False, "message": "Empty patch"}
            
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            
            try:
                subprocess.run(["git", "init"], cwd=temp_dir, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
                subprocess.run(["git", "config", "user.name", "Reviewer"], cwd=temp_dir, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
                subprocess.run(["git", "config", "user.email", "reviewer@example.com"], cwd=temp_dir, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
            except Exception as e:
                return {"applicable": False, "message": f"Failed to initialize validation repository: {e}"}
                
            # Extract target files from patch
            target_files = []
            for line in patch.splitlines():
                if line.startswith("--- a/") or line.startswith("--- "):
                    p = line[6:] if line.startswith("--- a/") else line[4:]
                    p = p.strip().split('\t')[0]
                    if p != "/dev/null" and p not in target_files:
                        target_files.append(p)
                elif line.startswith("+++ b/") or line.startswith("+++ "):
                    p = line[6:] if line.startswith("+++ b/") else line[4:]
                    p = p.strip().split('\t')[0]
                    if p != "/dev/null" and p not in target_files:
                        target_files.append(p)
            
            for path_in_patch in target_files:
                basename = Path(path_in_patch).name
                content = None
                if path_in_patch in file_context:
                    content = file_context[path_in_patch]
                elif basename in file_context:
                    content = file_context[basename]
                else:
                    for k, v in file_context.items():
                        if k.endswith(path_in_patch) or path_in_patch.endswith(k):
                            content = v
                            break
                            
                if content is not None:
                    file_dest = temp_path / path_in_patch
                    file_dest.parent.mkdir(parents=True, exist_ok=True)
                    file_dest.write_text(content, encoding='utf-8')
            
            try:
                subprocess.run(["git", "add", "."], cwd=temp_dir, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
                subprocess.run(["git", "commit", "-m", "initial state"], cwd=temp_dir, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
            except Exception:
                pass
                
            patch_file = temp_path / "patch.diff"
            patch_file.write_text(patch, encoding='utf-8')
            
            try:
                result = subprocess.run(
                    ["git", "apply", "--check", "patch.diff"],
                    cwd=temp_dir,
                    capture_output=True,
                    text=True
                )
                if result.returncode == 0:
                    return {"applicable": True, "message": "Patch applies cleanly"}
                else:
                    return {"applicable": False, "message": result.stderr.strip() or "Patch does not apply cleanly"}
            except Exception as e:
                return {"applicable": False, "message": f"Failed to run git apply check: {e}"}


class ASTValidator:
    """Validates code syntax after applying a patch"""

    @staticmethod
    def strip_comments_and_strings(code: str) -> str:
        clean = []
        state = "normal"
        i = 0
        n = len(code)
        while i < n:
            char = code[i]
            next_char = code[i+1] if i + 1 < n else ""
            
            if state == "normal":
                if char == "/" and next_char == "/":
                    state = "single_comment"
                    i += 1
                elif char == "/" and next_char == "*":
                    state = "multi_comment"
                    i += 1
                elif char == '"':
                    state = "double_string"
                elif char == "'":
                    state = "single_string"
                elif char == "`":
                    state = "template_string"
                else:
                    clean.append(char)
            elif state == "single_comment":
                if char == "\n":
                    state = "normal"
                    clean.append(char)
            elif state == "multi_comment":
                if char == "*" and next_char == "/":
                    state = "normal"
                    i += 1
            elif state == "double_string":
                if char == '"' and code[i-1] != "\\":
                    state = "normal"
            elif state == "single_string":
                if char == "'" and code[i-1] != "\\":
                    state = "normal"
            elif state == "template_string":
                if char == "`" and code[i-1] != "\\":
                    state = "normal"
            i += 1
        return "".join(clean)

    @classmethod
    def check_syntax(cls, file_content: str, filename: str) -> Dict[str, Any]:
        ext = Path(filename).suffix.lower()
        if ext == '.py':
            try:
                ast.parse(file_content)
                return {"valid": True, "error": None}
            except SyntaxError as e:
                return {"valid": False, "error": f"Python syntax error at line {e.lineno}: {e.msg}"}
        elif ext in ['.js', '.ts', '.jsx', '.tsx']:
            cleaned = cls.strip_comments_and_strings(file_content)
            stack = []
            brackets = {')': '(', '}': '{', ']': '['}
            for idx, char in enumerate(cleaned):
                if char in brackets.values():
                    stack.append((char, idx))
                elif char in brackets.keys():
                    if not stack:
                        if char == '}':
                            return {"valid": False, "error": f"Mismatched closing brace '}}' at character {idx}"}
                    else:
                        top_char, top_idx = stack[-1]
                        if top_char == brackets[char]:
                            stack.pop()
                        elif char == '}':
                            return {"valid": False, "error": f"Mismatched braces: expected '{brackets[char]}' for '{char}'"}
            unclosed_braces = [item for item in stack if item[0] == '{']
            if unclosed_braces:
                return {"valid": False, "error": f"Unclosed '{{' starting at character {unclosed_braces[0][1]}"}
            return {"valid": True, "error": None}
        return {"valid": True, "error": None}

    @classmethod
    def validate_patched_files(cls, patch: str, file_context: Dict[str, str]) -> Dict[str, Any]:
        if not patch or not patch.strip():
            return {"valid": True, "errors": []}
            
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            
            try:
                subprocess.run(["git", "init"], cwd=temp_dir, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
                subprocess.run(["git", "config", "user.name", "Reviewer"], cwd=temp_dir, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
                subprocess.run(["git", "config", "user.email", "reviewer@example.com"], cwd=temp_dir, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
            except Exception as e:
                return {"valid": False, "errors": [f"Failed to initialize validation repository: {e}"]}
                
            target_files = []
            for line in patch.splitlines():
                if line.startswith("--- a/") or line.startswith("--- "):
                    p = line[6:] if line.startswith("--- a/") else line[4:]
                    p = p.strip().split('\t')[0]
                    if p != "/dev/null" and p not in target_files:
                        target_files.append(p)
                elif line.startswith("+++ b/") or line.startswith("+++ "):
                    p = line[6:] if line.startswith("+++ b/") else line[4:]
                    p = p.strip().split('\t')[0]
                    if p != "/dev/null" and p not in target_files:
                        target_files.append(p)
            
            for path_in_patch in target_files:
                basename = Path(path_in_patch).name
                content = None
                if path_in_patch in file_context:
                    content = file_context[path_in_patch]
                elif basename in file_context:
                    content = file_context[basename]
                else:
                    for k, v in file_context.items():
                        if k.endswith(path_in_patch) or path_in_patch.endswith(k):
                            content = v
                            break
                            
                if content is not None:
                    file_dest = temp_path / path_in_patch
                    file_dest.parent.mkdir(parents=True, exist_ok=True)
                    file_dest.write_text(content, encoding='utf-8')
            
            try:
                subprocess.run(["git", "add", "."], cwd=temp_dir, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
                subprocess.run(["git", "commit", "-m", "initial state"], cwd=temp_dir, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
            except Exception:
                pass
                
            patch_file = temp_path / "patch.diff"
            patch_file.write_text(patch, encoding='utf-8')
            
            try:
                subprocess.run(["git", "apply", "patch.diff"], cwd=temp_dir, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
            except Exception as e:
                return {"valid": False, "errors": [f"Could not apply patch to files: {e}"]}
                
            errors = []
            for path_in_patch in target_files:
                file_dest = temp_path / path_in_patch
                if file_dest.exists() and file_dest.is_file():
                    try:
                        content = file_dest.read_text(encoding='utf-8')
                        syntax_res = cls.check_syntax(content, path_in_patch)
                        if not syntax_res["valid"]:
                            errors.append(f"{path_in_patch}: {syntax_res['error']}")
                    except Exception as e:
                        errors.append(f"Failed to check syntax of {path_in_patch}: {e}")
                        
            return {"valid": len(errors) == 0, "errors": errors}


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
                p = line[6:] if line.startswith("+++ b/") else line[4:]
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


class SyntaxChecker:
    """Basic syntax checking for common languages"""
    
    @staticmethod
    def check_python(code: str) -> Dict:
        """Check Python syntax"""
        try:
            compile(code, '<string>', 'exec')
            return {'valid': True, 'error': None}
        except SyntaxError as e:
            return {'valid': False, 'error': f"Syntax error at line {e.lineno}: {e.msg}"}
    
    @staticmethod
    def check_javascript(code: str) -> Dict:
        """Basic JavaScript syntax check"""
        res = ASTValidator.check_syntax(code, "temp.js")
        return {'valid': res["valid"], 'error': res["error"]}



def validate_code_content(files: List[str]) -> Dict:
    """
    Validate uploaded code files for basic safety
    
    Args:
        files: List of file paths
        
    Returns:
        Dict with validation results
    """
    results = {
        'valid_files': 0,
        'invalid_files': 0,
        'warnings': [],
        'errors': []
    }
    
    for file_path in files:
        path = Path(file_path)
        
        # Check file size (limit to 1MB for safety)
        if path.stat().st_size > 1024 * 1024:
            results['warnings'].append(f"File {path.name} exceeds 1MB limit")
            continue
        
        # Check file extension
        allowed_extensions = {'.py', '.js', '.ts', '.jsx', '.tsx', '.java', '.go', '.rs', '.cpp', '.c', '.txt', '.md', '.html', '.css', '.json', '.yaml', '.yml', '.example', '.bin', '.env'}
        if path.suffix.lower() not in allowed_extensions:
            # Allow unrecognized safe text/data extensions as soft warnings
            results['warnings'].append(f"File {path.name} has custom extension: {path.suffix} - proceeding with standard analysis")
        
        # Try to read the file
        try:
            content = path.read_text(encoding='utf-8')
            
            # Basic syntax check for Python
            if path.suffix == '.py':
                syntax_check = SyntaxChecker.check_python(content)
                if not syntax_check['valid']:
                    results['warnings'].append(f"{path.name} has syntax error: {syntax_check['error']}")
                
            results['valid_files'] += 1
                
        except UnicodeDecodeError:
            results['warnings'].append(f"File {path.name} appears to be binary")
        except Exception as e:
            results['errors'].append(f"Error reading {path.name}: {str(e)}")
            results['invalid_files'] += 1
    
    return results
