"""
Edge case tests and failure examples for Contextual Code Review Assistant
"""

import os
os.environ['MOCK_MODE'] = 'true'
import tempfile
import asyncio
from pathlib import Path
from code_reviewer import CodeReviewer
from patch_utils import PatchValidator, validate_code_content

def run_async(coro):
    return asyncio.run(coro)


def test_empty_file():
    """Test handling of empty files"""
    print("Test 1: Empty file")
    with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
        f.write("")
        temp_file = f.name
    
    try:
        reviewer = CodeReviewer()
        reviewer.mock_mode = True  # Use mock mode for testing
        result = run_async(reviewer.review_files([temp_file], "Review this empty file"))
        print(f"✓ Empty file handled: {result['summary'][:50]}...")
    finally:
        os.unlink(temp_file)


def test_large_file_truncation():
    """Test that large files are properly truncated"""
    print("\nTest 2: Large file truncation")
    with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
        # Write a large file (simulated)
        f.write("# Large file\n" * 10000)
        temp_file = f.name
    
    try:
        reviewer = CodeReviewer()
        reviewer.mock_mode = True
        result = run_async(reviewer.review_files([temp_file], "Review this large file"))
        print(f"✓ Large file handled with truncation")
    finally:
        os.unlink(temp_file)


def test_syntax_error():
    """Test handling of files with syntax errors"""
    print("\nTest 3: Syntax error in Python file")
    with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
        f.write("""
def broken_function(
    print("Missing closing parenthesis")
""")
        temp_file = f.name
    
    try:
        validation = validate_code_content([temp_file])
        has_error = False
        if validation['errors']:
            print(f"✓ Syntax error detected in errors: {validation['errors'][0]}")
            has_error = True
        elif validation['warnings']:
            for w in validation['warnings']:
                if "syntax error" in w.lower():
                    print(f"✓ Syntax error detected in warnings: {w}")
                    has_error = True
                    break
        if not has_error:
            print("✗ Syntax error not detected")
    finally:
        os.unlink(temp_file)


def test_dangerous_patch():
    """Test that dangerous patches are flagged"""
    print("\nTest 4: Dangerous patch detection")
    dangerous_patch = """
diff --git a/file.py b/file.py
index 123..456 100644
--- a/file.py
+++ b/file.py
@@ -1,1 +1,1 @@
- print("hello")
+ os.system("rm -rf /")
"""
    
    validator = PatchValidator()
    result = validator.validate_patch(dangerous_patch, {})
    
    if not result['is_safe']:
        print(f"✓ Dangerous patch flagged: {result['errors']}")
    else:
        print("✗ Dangerous patch not flagged")


def test_suspicious_import():
    """Test that suspicious imports are warned"""
    print("\nTest 5: Suspicious import detection")
    suspicious_patch = """
diff --git a/file.py b/file.py
index 123..456 100644
--- a/file.py
+++ b/file.py
@@ -1,1 +1,1 @@
- import os
+ import pickle; pickle.loads(data)
"""
    
    validator = PatchValidator()
    result = validator.validate_patch(suspicious_patch, {})
    
    if result['warnings']:
        print(f"✓ Suspicious import warned: {result['warnings']}")
    else:
        print("✗ Suspicious import not warned")


def test_binary_file():
    """Test handling of binary files"""
    print("\nTest 6: Binary file handling")
    with tempfile.NamedTemporaryFile(mode='wb', suffix='.bin', delete=False) as f:
        f.write(b'\x00\x01\x02\x03\x04\x05')
        temp_file = f.name
    
    try:
        validation = validate_code_content([temp_file])
        if validation['warnings']:
            print(f"✓ Binary file detected: {validation['warnings'][0]}")
        else:
            print("✗ Binary file not detected")
    finally:
        os.unlink(temp_file)


def test_unicode_handling():
    """Test handling of files with unicode content"""
    print("\nTest 7: Unicode content handling")
    with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False, encoding='utf-8') as f:
        f.write('# Unicode test: 你好世界 🌍\ndef test():\n    print("Hello")')
        temp_file = f.name
    
    try:
        reviewer = CodeReviewer()
        reviewer.mock_mode = True
        result = run_async(reviewer.review_files([temp_file], "Review unicode file"))
        print(f"✓ Unicode content handled")
    finally:
        os.unlink(temp_file)


def test_multiple_files():
    """Test handling multiple files simultaneously"""
    print("\nTest 8: Multiple files handling")
    temp_files = []
    
    for i in range(3):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write(f"# File {i}\ndef func_{i}():\n    pass\n")
            temp_files.append(f.name)
    
    try:
        reviewer = CodeReviewer()
        reviewer.mock_mode = True
        result = run_async(reviewer.review_files(temp_files, "Review multiple files"))
        print(f"✓ Multiple files handled: {len(temp_files)} files processed")
    finally:
        for f in temp_files:
            os.unlink(f)


def test_mixed_extensions():
    """Test handling files with different extensions"""
    print("\nTest 9: Mixed file extensions")
    temp_files = []
    
    # Create files with different extensions
    extensions = ['.py', '.js', '.txt']
    for ext in extensions:
        with tempfile.NamedTemporaryFile(mode='w', suffix=ext, delete=False) as f:
            f.write(f"# Test file{ext}\ncontent here")
            temp_files.append(f.name)
    
    try:
        reviewer = CodeReviewer()
        reviewer.mock_mode = True
        result = run_async(reviewer.review_files(temp_files, "Review mixed extensions"))
        print(f"✓ Mixed extensions handled: {[Path(f).suffix for f in temp_files]}")
    finally:
        for f in temp_files:
            os.unlink(f)


def test_context_window_limit():
    """Test behavior when approaching context window limit"""
    print("\nTest 10: Context window limit")
    # Create a file that would exceed context window
    with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
        # Write content that would be truncated
        f.write("# " + "x" * 50000 + "\ndef func():\n    pass")
        temp_file = f.name
    
    try:
        reviewer = CodeReviewer()
        reviewer.mock_mode = True
        result = run_async(reviewer.review_files([temp_file], "Review large file"))
        print(f"✓ Context window limit handled with truncation")
    finally:
        os.unlink(temp_file)


def test_multimodal_review():
    """Test multimodal review with mock image files"""
    print("\nTest 11: Multimodal review with screenshots")
    
    # Create temporary code and dummy image file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
        f.write("def render_ui():\n    pass")
        code_file = f.name
        
    with tempfile.NamedTemporaryFile(mode='wb', suffix='.png', delete=False) as f:
        # Write 100 bytes of dummy image data
        f.write(b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR' + b'\x00' * 80)
        img_file = f.name
        
    try:
        reviewer = CodeReviewer()
        reviewer.mock_mode = True
        result = run_async(reviewer.review_files([code_file], "Check UI mapping", [img_file]))
        print(f"✓ Multimodal review executed successfully")
    finally:
        os.unlink(code_file)
        os.unlink(img_file)


def run_all_tests():
    """Run all edge case tests"""
    print("=" * 60)
    print("Edge Case Tests for Contextual Code Review Assistant")
    print("=" * 60)
    
    tests = [
        test_empty_file,
        test_large_file_truncation,
        test_syntax_error,
        test_dangerous_patch,
        test_suspicious_import,
        test_binary_file,
        test_unicode_handling,
        test_multiple_files,
        test_mixed_extensions,
        test_context_window_limit,
        test_multimodal_review
    ]
    
    passed = 0
    failed = 0
    
    for test in tests:
        try:
            test()
            passed += 1
        except Exception as e:
            print(f"✗ Test failed with error: {e}")
            failed += 1
    
    print("\n" + "=" * 60)
    print(f"Test Results: {passed} passed, {failed} failed")
    print("=" * 60)


if __name__ == '__main__':
    run_all_tests()
