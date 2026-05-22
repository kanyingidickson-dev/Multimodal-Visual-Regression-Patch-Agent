import mimetypes
import base64
import aiofiles
from pathlib import Path

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
    path = Path(file_path)
    try:
        async with aiofiles.open(path, 'r', encoding='utf-8') as f:
            return await f.read()
    except UnicodeDecodeError:
        try:
            async with aiofiles.open(path, 'r', encoding='latin-1') as f:
                return await f.read()
        except:
            return f"[Binary file: {path.name}]"

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
        async with aiofiles.open(path, "rb") as image_file:
            image_data = await image_file.read()
            encoded_string = base64.b64encode(image_data).decode('utf-8')
        return f"data:{mime_type};base64,{encoded_string}"
    except Exception as e:
        print(f"Error encoding image {image_path}: {e}")
        return ""
